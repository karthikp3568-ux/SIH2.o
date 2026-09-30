"""Admin and counsellor endpoints.

The governing principle: an AI recommendation is a proposal, not a fact. A
counsellor can accept, edit or reject any of them, corrections to extracted
profiles are possible, and every one of those actions is written to the audit
log with actor, timestamp and before/after values.
"""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from ..core.enums import AuditAction, RecordStatus, Role, VerificationStatus
from ..deps import AdminUser, DbSession, StaffUser
from ..models import (
    AuditLog,
    BeneficiaryProfile,
    Opportunity,
    Recommendation,
    TrainingProgram,
    User,
    as_aware,
    utcnow,
)
from ..providers.data_sources import CSV_REQUIRED_COLUMNS, CsvOpportunityProvider
from ..rag.ingest import ingest_opportunity, sync_knowledge_base
from ..schemas.auth import CreateUserRequest, UserOut
from ..schemas.common import Message
from ..schemas.opportunity import (
    ImportReport,
    ImportRowError,
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
    VerifyRequest,
)
from ..schemas.recommendation import OverrideRequest
from ..security import hash_password
from ..services import analytics, audit, profile_service
from ..services.serializers import opportunity_out, recommendation_out
from ..services.skill_normalization import normalize_labels

router = APIRouter(prefix="/admin", tags=["admin"])

#: Fields captured in before/after diffs when an opportunity changes.
_TRACKED_FIELDS = [
    "title",
    "provider",
    "opportunity_type",
    "status",
    "education_required",
    "seats_available",
    "valid_until",
    "source",
    "source_trust",
    "verification_status",
    "latitude",
    "longitude",
    "mobility_required",
]


# ---------------------------------------------------------------------------
# Opportunities
# ---------------------------------------------------------------------------


@router.get("/opportunities")
def list_opportunities(
    user: StaffUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    record_status: Annotated[str | None, Query(max_length=16)] = None,
    verification: Annotated[str | None, Query(max_length=32)] = None,
    needs_review: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    statement = select(Opportunity).options(
        selectinload(Opportunity.qualification), selectinload(Opportunity.training_program)
    )
    if q:
        pattern = f"%{q.lower()}%"
        statement = statement.where(
            or_(
                func.lower(Opportunity.title).like(pattern),
                func.lower(Opportunity.provider).like(pattern),
            )
        )
    if record_status:
        statement = statement.where(Opportunity.status == record_status)
    if verification:
        statement = statement.where(Opportunity.verification_status == verification)

    rows = db.execute(statement).scalars().unique().all()
    now = utcnow()
    if needs_review:
        # Anything expired, unverified, or not re-checked in 90 days.
        cutoff = now - timedelta(days=90)

        def wants_review(record: Opportunity) -> bool:
            valid_until = as_aware(record.valid_until)
            last_verified = as_aware(record.last_verified_at)
            return (
                (valid_until is not None and valid_until < now)
                or last_verified is None
                or last_verified < cutoff
                or record.verification_status
                in {VerificationStatus.UNVERIFIED, VerificationStatus.SELF_DECLARED}
            )

        rows = [r for r in rows if wants_review(r)]
    rows.sort(key=lambda r: r.updated_at, reverse=True)
    return {
        "items": [opportunity_out(r) for r in rows[offset : offset + limit]],
        "total": len(rows),
        "limit": limit,
        "offset": offset,
    }


@router.post("/opportunities", response_model=OpportunityOut, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreate, user: AdminUser, request: Request, db: DbSession
) -> OpportunityOut:
    skill_codes, unresolved = normalize_labels(db, payload.skills_required)
    opportunity = Opportunity(
        **payload.model_dump(exclude={"training_program", "skills_required"}),
        skills_required=payload.skills_required,
        skill_codes=skill_codes,
        ingestion_channel="admin",
        verification_status=VerificationStatus.UNVERIFIED,
    )
    db.add(opportunity)
    db.flush()

    if payload.training_program is not None:
        db.add(
            TrainingProgram(opportunity_id=opportunity.id, **payload.training_program.model_dump())
        )

    audit.record(
        db,
        action=AuditAction.OPPORTUNITY_CREATED,
        actor=user,
        entity_type="opportunity",
        entity_id=opportunity.id,
        new_value=audit.model_snapshot(opportunity, _TRACKED_FIELDS),
        summary=f"Created opportunity '{opportunity.title}'",
        request=request,
    )
    db.commit()
    db.refresh(opportunity)
    ingest_opportunity(db, opportunity)
    db.commit()

    result = opportunity_out(opportunity)
    result["unresolved_skill_labels"] = unresolved
    return OpportunityOut(**{k: v for k, v in result.items() if k != "unresolved_skill_labels"})


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def update_opportunity(
    opportunity_id: str,
    payload: OpportunityUpdate,
    user: AdminUser,
    request: Request,
    db: DbSession,
) -> OpportunityOut:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    before = audit.model_snapshot(opportunity, _TRACKED_FIELDS)
    data = payload.model_dump(exclude_unset=True, exclude={"training_program"})
    for field, value in data.items():
        setattr(opportunity, field, value)
    if "skills_required" in data and data["skills_required"] is not None:
        opportunity.skill_codes, _ = normalize_labels(db, data["skills_required"])

    if payload.training_program is not None:
        program = opportunity.training_program
        if program is None:
            program = TrainingProgram(opportunity_id=opportunity.id)
            db.add(program)
        for field, value in payload.training_program.model_dump().items():
            setattr(program, field, value)

    after = audit.model_snapshot(opportunity, _TRACKED_FIELDS)
    changed_before, changed_after = audit.diff(before, after)
    audit.record(
        db,
        action=AuditAction.OPPORTUNITY_UPDATED,
        actor=user,
        entity_type="opportunity",
        entity_id=opportunity.id,
        old_value=changed_before or None,
        new_value=changed_after or None,
        summary=f"Updated opportunity '{opportunity.title}'",
        request=request,
    )
    db.commit()
    db.refresh(opportunity)
    ingest_opportunity(db, opportunity)
    db.commit()
    return OpportunityOut(**opportunity_out(opportunity))


@router.delete("/opportunities/{opportunity_id}", response_model=Message)
def delete_opportunity(
    opportunity_id: str, user: AdminUser, request: Request, db: DbSession
) -> Message:
    """Soft delete by default: the record becomes inactive and stops being recommended.

    Hard deletion is not offered here because outcomes reference opportunities;
    losing the row would orphan a beneficiary's history.
    """
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    before = audit.model_snapshot(opportunity, _TRACKED_FIELDS)
    opportunity.status = RecordStatus.INACTIVE
    audit.record(
        db,
        action=AuditAction.OPPORTUNITY_DELETED,
        actor=user,
        entity_type="opportunity",
        entity_id=opportunity.id,
        old_value=before,
        new_value={"status": RecordStatus.INACTIVE},
        summary=f"Deactivated opportunity '{opportunity.title}'",
        request=request,
    )
    db.commit()
    ingest_opportunity(db, opportunity)
    db.commit()
    return Message(message="Opportunity marked inactive and removed from recommendations.")


@router.post("/opportunities/{opportunity_id}/verify", response_model=OpportunityOut)
def verify_opportunity(
    opportunity_id: str,
    payload: VerifyRequest,
    user: StaffUser,
    request: Request,
    db: DbSession,
) -> OpportunityOut:
    """Record that a human checked this listing against its source."""
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")

    before = audit.model_snapshot(
        opportunity, ["verification_status", "last_verified_at", "valid_until", "source_url"]
    )
    opportunity.verification_status = str(payload.verification_status)
    opportunity.verified_by_user_id = user.id
    opportunity.last_verified_at = utcnow()
    if payload.source_url:
        opportunity.source_url = payload.source_url
    if payload.extend_valid_days:
        opportunity.valid_until = utcnow() + timedelta(days=payload.extend_valid_days)

    audit.record(
        db,
        action=AuditAction.OPPORTUNITY_VERIFIED,
        actor=user,
        entity_type="opportunity",
        entity_id=opportunity.id,
        old_value=before,
        new_value=audit.model_snapshot(
            opportunity, ["verification_status", "last_verified_at", "valid_until", "source_url"]
        ),
        summary=payload.note or "Opportunity verified",
        request=request,
    )
    db.commit()
    db.refresh(opportunity)
    ingest_opportunity(db, opportunity)
    db.commit()
    return OpportunityOut(**opportunity_out(opportunity))


@router.post("/opportunities/import", response_model=ImportReport)
async def import_opportunities(
    user: AdminUser,
    request: Request,
    db: DbSession,
    file: Annotated[UploadFile, File(description="CSV of opportunity records")],
    dry_run: bool = True,
) -> ImportReport:
    """CSV import with validation. `dry_run` reports what would happen, changing nothing."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File must be UTF-8 encoded CSV."
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    missing = CSV_REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"CSV is missing required columns: {', '.join(sorted(missing))}",
        )

    report = ImportReport(dry_run=dry_run, rows_read=0, created=0, updated=0, skipped=0)
    existing = {o.external_id: o for o in db.execute(select(Opportunity)).scalars().all() if o.external_id}

    for index, row in enumerate(reader, start=2):
        report.rows_read += 1
        record = CsvOpportunityProvider.coerce_row(row)
        errors: list[str] = []
        for column in CSV_REQUIRED_COLUMNS:
            if not record.get(column):
                errors.append(f"'{column}' is required")
        if record.get("latitude") is not None and not (-90 <= record["latitude"] <= 90):
            errors.append("latitude out of range")
        if record.get("longitude") is not None and not (-180 <= record["longitude"] <= 180):
            errors.append("longitude out of range")
        if errors:
            report.skipped += 1
            report.errors.append(
                ImportRowError(
                    row=index, external_id=record.get("external_id"), errors=errors
                )
            )
            continue

        external_id = record.get("external_id")
        target = existing.get(external_id) if external_id else None
        if target is None:
            report.created += 1
        else:
            report.updated += 1

        if dry_run:
            continue

        if target is None:
            target = Opportunity(
                external_id=external_id,
                title=record["title"],
                provider=record["provider"],
                opportunity_type=record["opportunity_type"],
                description=record["description"],
                source=record["source"],
            )
            db.add(target)
            if external_id:
                existing[external_id] = target
        for field, value in record.items():
            if field in {"external_id"} or not hasattr(target, field):
                continue
            setattr(target, field, value)
        target.ingestion_channel = "csv_import"
        # Imported records start unverified: an import is not a verification.
        target.verification_status = VerificationStatus.UNVERIFIED
        target.status = record.get("status", RecordStatus.DRAFT)
        target.last_verified_at = target.last_verified_at or utcnow()
        if record.get("skills_required"):
            target.skill_codes, _ = normalize_labels(db, record["skills_required"])

    if not dry_run:
        audit.record(
            db,
            action=AuditAction.OPPORTUNITY_CREATED,
            actor=user,
            entity_type="opportunity_import",
            new_value={
                "rows": report.rows_read,
                "created": report.created,
                "updated": report.updated,
                "skipped": report.skipped,
                "filename": file.filename,
            },
            summary=f"CSV import: {report.created} created, {report.updated} updated",
            request=request,
        )
        db.commit()
        sync_knowledge_base(db)

    return report


@router.post("/knowledge/reindex")
def reindex(user: AdminUser, db: DbSession) -> dict:
    """Rebuild the RAG index from the current structured records."""
    return sync_knowledge_base(db).as_dict()


# ---------------------------------------------------------------------------
# Beneficiaries and AI review
# ---------------------------------------------------------------------------


@router.get("/beneficiaries")
def list_beneficiaries(
    user: StaffUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict]:
    statement = select(BeneficiaryProfile).options(
        selectinload(BeneficiaryProfile.skills),
        selectinload(BeneficiaryProfile.goals),
        selectinload(BeneficiaryProfile.locations),
    )
    if q:
        statement = statement.where(func.lower(BeneficiaryProfile.display_name).like(f"%{q.lower()}%"))
    rows = db.execute(statement.limit(limit)).scalars().unique().all()
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "preferred_language": p.preferred_language,
            "mobility": p.mobility,
            "is_confirmed": p.is_confirmed,
            "skill_count": len([s for s in p.skills if s.is_active]),
            "goals": [g.goal_type for g in p.goals if g.is_active],
            "district": p.primary_location.district if p.primary_location else None,
            "created_at": p.created_at.isoformat(),
        }
        for p in rows
    ]


@router.get("/beneficiaries/{beneficiary_id}/extraction")
def review_extraction(beneficiary_id: str, user: StaffUser, db: DbSession) -> dict:
    """What the AI extracted, turn by turn, for human review."""
    from ..models import Conversation  # noqa: PLC0415

    profile = db.get(BeneficiaryProfile, beneficiary_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiary not found")

    conversations = (
        db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.beneficiary_id == beneficiary_id)
            .order_by(Conversation.created_at.desc())
            .limit(5)
        )
        .scalars()
        .unique()
        .all()
    )
    return {
        "profile": profile_service.profile_to_dict(profile),
        "conversations": [
            {
                "id": c.id,
                "state": c.state,
                "language": c.language,
                "channel": c.channel,
                "created_at": c.created_at.isoformat(),
                "draft_profile": c.draft_profile,
                "messages": [
                    {
                        "sequence": m.sequence,
                        "role": m.role,
                        "raw_text": m.raw_text,
                        "normalized_text": m.normalized_text,
                        "detected_language": m.detected_language,
                        "language_confidence": m.language_confidence,
                        "asr_confidence": m.asr_confidence,
                        "is_code_switched": m.is_code_switched,
                        "needs_confirmation": m.needs_confirmation,
                        "extracted_entities": m.extracted_entities,
                    }
                    for m in c.messages
                ],
            }
            for c in conversations
        ],
    }


@router.patch("/beneficiaries/{beneficiary_id}/profile")
def correct_profile(
    beneficiary_id: str,
    payload: dict,
    user: StaffUser,
    request: Request,
    db: DbSession,
) -> dict:
    """Counsellor correction of an extracted profile.

    Takes the same draft shape the confirmation screen uses, so a correction is
    applied exactly as a beneficiary's own edit would be - and is audited as a
    staff action.
    """
    profile = db.get(BeneficiaryProfile, beneficiary_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Beneficiary not found")

    before = profile_service.profile_to_dict(profile)
    profile_service.apply_draft(db, profile, payload.get("draft_profile") or {}, actor=user)
    after = profile_service.profile_to_dict(profile)

    audit.record(
        db,
        action=AuditAction.PROFILE_CORRECTED_BY_ADMIN,
        actor=user,
        entity_type="beneficiary_profile",
        entity_id=profile.id,
        old_value={"education": before.get("education"), "skills": [s["code"] for s in before["skills"]]},
        new_value={"education": after.get("education"), "skills": [s["code"] for s in after["skills"]]},
        summary=payload.get("note") or "Profile corrected by staff",
        request=request,
        commit=True,
    )
    return after


@router.post("/recommendations/{recommendation_id}/override")
def override_recommendation(
    recommendation_id: str,
    payload: OverrideRequest,
    user: StaffUser,
    request: Request,
    db: DbSession,
) -> dict:
    """Accept, edit or reject an AI recommendation. Always logged."""
    recommendation = db.execute(
        select(Recommendation)
        .options(selectinload(Recommendation.opportunity), selectinload(Recommendation.reasons))
        .where(Recommendation.id == recommendation_id)
    ).scalar_one_or_none()
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    before = {
        "is_overridden": recommendation.is_overridden,
        "override_action": recommendation.override_action,
        "next_step": recommendation.next_step,
    }
    recommendation.is_overridden = True
    recommendation.override_action = payload.action
    recommendation.override_note = payload.note
    recommendation.overridden_by_user_id = user.id
    recommendation.overridden_at = utcnow()
    if payload.action == "edit" and payload.revised_next_step:
        recommendation.next_step = payload.revised_next_step

    audit.record(
        db,
        action=AuditAction.RECOMMENDATION_OVERRIDE,
        actor=user,
        entity_type="recommendation",
        entity_id=recommendation.id,
        old_value=before,
        new_value={
            "is_overridden": True,
            "override_action": payload.action,
            "note": payload.note,
            "next_step": recommendation.next_step,
        },
        summary=f"Recommendation {payload.action}ed by {user.role}",
        request=request,
    )
    db.commit()
    db.refresh(recommendation)
    return recommendation_out(db, recommendation)


# ---------------------------------------------------------------------------
# Analytics, audit and users
# ---------------------------------------------------------------------------


@router.get("/analytics")
def get_analytics(user: StaffUser, db: DbSession) -> dict:
    payload = analytics.overview(db)
    payload["top_skill_gaps"] = analytics.top_skill_gaps(db)
    payload["opportunity_freshness"] = analytics.opportunity_freshness(db)
    if payload["is_demo_data"]:
        payload["disclaimer"] = (
            "All figures are computed from the seeded demonstration data in this "
            "database. They are not real-world impact numbers."
        )
    return payload


@router.get("/audit")
def get_audit_log(
    user: StaffUser,
    db: DbSession,
    action: Annotated[str | None, Query(max_length=64)] = None,
    entity_type: Annotated[str | None, Query(max_length=48)] = None,
    entity_id: Annotated[str | None, Query(max_length=36)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[dict]:
    statement = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        statement = statement.where(AuditLog.action == action)
    if entity_type:
        statement = statement.where(AuditLog.entity_type == entity_type)
    if entity_id:
        statement = statement.where(AuditLog.entity_id == entity_id)
    rows = db.execute(statement.limit(limit)).scalars().all()

    actors = {
        u.id: u.email
        for u in db.execute(
            select(User).where(User.id.in_([r.actor_user_id for r in rows if r.actor_user_id] or [""]))
        )
        .scalars()
        .all()
    }
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "action": r.action,
            "actor_email": actors.get(r.actor_user_id),
            "actor_role": r.actor_role,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "old_value": r.old_value,
            "new_value": r.new_value,
            "summary": r.summary,
            "ip_address": r.ip_address,
        }
        for r in rows
    ]


@router.get("/users", response_model=list[UserOut])
def list_users(user: AdminUser, db: DbSession) -> list[UserOut]:
    rows = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest, user: AdminUser, request: Request, db: DbSession
) -> UserOut:
    """The only route that can assign a privileged role, and it requires an admin."""
    existing = db.execute(select(User).where(User.email == str(payload.email))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
    created = User(
        email=str(payload.email).lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=str(payload.role),
        preferred_language=str(payload.preferred_language),
    )
    db.add(created)
    db.flush()
    if created.role == Role.BENEFICIARY:
        db.add(
            BeneficiaryProfile(
                user_id=created.id,
                display_name=created.full_name,
                preferred_language=created.preferred_language,
            )
        )
    audit.record(
        db,
        action=AuditAction.REGISTER,
        actor=user,
        entity_type="user",
        entity_id=created.id,
        new_value={"email": created.email, "role": created.role},
        summary=f"Admin created {created.role} account",
        request=request,
    )
    db.commit()
    db.refresh(created)
    return UserOut.model_validate(created)


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: str, user: AdminUser, request: Request, db: DbSession
) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot deactivate your own account."
        )
    target.is_active = False
    target.token_version += 1  # revokes live sessions immediately
    audit.record(
        db,
        action=AuditAction.USER_DEACTIVATED,
        actor=user,
        entity_type="user",
        entity_id=target.id,
        new_value={"is_active": False},
        summary=f"Deactivated account {target.email}",
        request=request,
    )
    db.commit()
    db.refresh(target)
    return UserOut.model_validate(target)
