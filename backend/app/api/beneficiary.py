"""Phase 2 - profile, skills, skill graph and skill gap endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..core.enums import (
    EDUCATION_LABEL,
    AuditAction,
    Confidence,
    RecordStatus,
    SkillSource,
    VerificationStatus,
)
from ..deps import CurrentBeneficiary, CurrentUser, DbSession, resolve_beneficiary_for_actor
from ..models import (
    BeneficiarySkill,
    Education,
    Goal,
    Interest,
    Occupation,
    Qualification,
    Skill,
    SkillEvidence,
    utcnow,
)
from ..schemas.beneficiary import (
    ProfileExtractRequest,
    ProfileExtractResponse,
    ProfilePatch,
    SkillGapRequest,
    SkillGapResponse,
    SkillIn,
    SkillNormalizeRequest,
    SkillNormalizeResponse,
)
from ..schemas.common import LocationIn, LocationOut, Message
from ..services import audit, profile_service
from ..services.profile_extraction import get_profile_extractor
from ..services.skill_gap import analyze_gap
from ..services.skill_graph import build_skill_graph, build_target_graph
from ..services.skill_normalization import build_alias_index, normalize_label

router = APIRouter(tags=["beneficiary"])


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------


@router.get("/beneficiary/profile")
def get_profile(beneficiary: CurrentBeneficiary) -> dict:
    return profile_service.profile_to_dict(beneficiary)


@router.get("/beneficiary/{beneficiary_id}/profile")
def get_profile_by_id(beneficiary_id: str, user: CurrentUser, db: DbSession) -> dict:
    """Staff may read any profile; a beneficiary may read only their own."""
    profile = resolve_beneficiary_for_actor(beneficiary_id, user, db)
    return profile_service.profile_to_dict(profile)


@router.patch("/beneficiary/profile")
def patch_profile(
    payload: ProfilePatch,
    user: CurrentUser,
    beneficiary: CurrentBeneficiary,
    request: Request,
    db: DbSession,
) -> dict:
    """Beneficiary-initiated corrections. Verification status is never editable here."""
    before = {
        "mobility": beneficiary.mobility,
        "age": beneficiary.age,
        "max_travel_km": beneficiary.max_travel_km,
        "education": beneficiary.educations[0].level if beneficiary.educations else None,
    }

    if payload.display_name is not None:
        beneficiary.display_name = payload.display_name
    if payload.preferred_language is not None:
        beneficiary.preferred_language = payload.preferred_language
    if payload.age is not None:
        beneficiary.age = payload.age
    if payload.gender is not None:
        beneficiary.gender = payload.gender
    if payload.mobility is not None:
        beneficiary.mobility = str(payload.mobility)
    if payload.max_travel_km is not None:
        beneficiary.max_travel_km = payload.max_travel_km

    if payload.education_level is not None:
        for education in list(beneficiary.educations):
            db.delete(education)
        db.flush()
        db.add(
            Education(
                beneficiary_id=beneficiary.id,
                level=str(payload.education_level),
                source="user_edit",
                confidence=Confidence.HIGH,
                verification_status=VerificationStatus.SELF_DECLARED,
            )
        )

    if payload.occupations is not None:
        for occupation in list(beneficiary.occupations):
            db.delete(occupation)
        db.flush()
        for title in payload.occupations[:10]:
            db.add(
                Occupation(
                    beneficiary_id=beneficiary.id,
                    title=title[:160],
                    source="user_edit",
                    confidence=Confidence.HIGH,
                )
            )

    if payload.interests is not None:
        for interest in list(beneficiary.interests):
            db.delete(interest)
        db.flush()
        for label in payload.interests[:10]:
            db.add(
                Interest(
                    beneficiary_id=beneficiary.id,
                    label=label[:120],
                    tag=label.lower().replace(" ", "_")[:64],
                    source="user_edit",
                )
            )

    if payload.goals is not None:
        for goal in list(beneficiary.goals):
            db.delete(goal)
        db.flush()
        for priority, goal_type in enumerate(payload.goals[:5], start=1):
            db.add(
                Goal(
                    beneficiary_id=beneficiary.id,
                    goal_type=str(goal_type),
                    priority=priority,
                    source="user_edit",
                )
            )

    if payload.location is not None:
        profile_service.upsert_location(
            db, beneficiary, payload.location.model_dump(exclude_none=True)
        )

    after = {
        "mobility": beneficiary.mobility,
        "age": beneficiary.age,
        "max_travel_km": beneficiary.max_travel_km,
        "education": str(payload.education_level) if payload.education_level else before["education"],
    }
    changed_before, changed_after = audit.diff(before, after)
    audit.record(
        db,
        action=AuditAction.PROFILE_UPDATED,
        actor=user,
        entity_type="beneficiary_profile",
        entity_id=beneficiary.id,
        old_value=changed_before or None,
        new_value=changed_after or None,
        summary="Profile updated by the beneficiary",
        request=request,
    )
    db.commit()
    db.refresh(beneficiary)
    return profile_service.profile_to_dict(beneficiary)


@router.put("/beneficiary/location", response_model=LocationOut)
def set_location(
    payload: LocationIn, beneficiary: CurrentBeneficiary, db: DbSession
) -> LocationOut:
    """Record a location. GPS, manual entry and PIN code are all accepted."""
    if payload.latitude is None and not (payload.pincode or payload.district):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide coordinates, a PIN code, or a district.",
        )
    location = profile_service.upsert_location(
        db, beneficiary, payload.model_dump(exclude_none=True)
    )
    db.commit()
    db.refresh(location)
    return LocationOut(
        id=location.id,
        label=location.label,
        village=location.village,
        block=location.block,
        district=location.district,
        state=location.state,
        pincode=location.pincode,
        latitude=location.latitude,
        longitude=location.longitude,
        source=location.source,
        accuracy_m=location.accuracy_m,
        captured_at=location.captured_at.isoformat() if location.captured_at else None,
    )


# ---------------------------------------------------------------------------
# Extraction and normalisation
# ---------------------------------------------------------------------------


@router.post("/profile/extract", response_model=ProfileExtractResponse)
def extract(payload: ProfileExtractRequest, user: CurrentUser, db: DbSession) -> ProfileExtractResponse:
    """Run extraction on a piece of text without committing anything."""
    extractor = get_profile_extractor()
    result = extractor.extract(db, payload.text, payload.language)
    return ProfileExtractResponse(
        language=result.language,
        language_confidence=result.language_confidence,
        is_code_switched=result.is_code_switched,
        extraction=result.to_summary(),
        filled_slots=sorted(result.filled_slots()),
        extractor=extractor.name,
    )


@router.post("/skills/normalize", response_model=SkillNormalizeResponse)
def normalize_skills(
    payload: SkillNormalizeRequest, user: CurrentUser, db: DbSession
) -> SkillNormalizeResponse:
    index = build_alias_index(db)
    items = []
    unresolved = []
    for label in payload.labels:
        match = normalize_label(db, label, index)
        if match is None:
            unresolved.append(label)
            items.append({"input": label, "resolved": False})
        else:
            items.append(
                {
                    "input": label,
                    "code": match.code,
                    "name": match.name,
                    "matched_alias": match.matched_alias,
                    "alias_language": match.alias_language,
                    "is_category": match.is_category,
                    "resolved": True,
                }
            )
    return SkillNormalizeResponse(items=items, unresolved=unresolved)


@router.get("/skills/taxonomy")
def taxonomy(db: DbSession) -> list[dict]:
    """The full canonical skill taxonomy, for admin tooling and the graph view."""
    skills = db.execute(select(Skill).where(Skill.is_active.is_(True))).scalars().all()
    by_id = {s.id: s for s in skills}
    return [
        {
            "id": s.id,
            "code": s.code,
            "name": s.name,
            "description": s.description,
            "sector": s.sector,
            "is_category": s.is_category,
            "parent_code": by_id[s.parent_id].code if s.parent_id in by_id else None,
        }
        for s in sorted(skills, key=lambda s: (s.sector or "", s.name))
    ]


@router.get("/skills/{beneficiary_id}")
def get_skills(beneficiary_id: str, user: CurrentUser, db: DbSession) -> dict:
    """A beneficiary's skills plus their derived skill graph."""
    profile = resolve_beneficiary_for_actor(beneficiary_id, user, db)
    graph = build_skill_graph(db, profile)
    return {
        "beneficiary_id": profile.id,
        "skills": profile_service.profile_to_dict(profile)["skills"],
        "skill_graph": graph.to_dict(),
    }


@router.post("/beneficiary/skills", status_code=status.HTTP_201_CREATED)
def add_skill(
    payload: SkillIn, user: CurrentUser, beneficiary: CurrentBeneficiary, db: DbSession
) -> dict:
    """Add a skill by hand. Recorded as self-declared and unverified."""
    match = normalize_label(db, payload.label)
    skill = db.execute(select(Skill).where(Skill.code == match.code)).scalar_one() if match else None

    link = BeneficiarySkill(
        beneficiary_id=beneficiary.id,
        skill_id=skill.id if skill else None,
        raw_label=payload.label,
        normalized_label=skill.name if skill else None,
        proficiency=str(payload.proficiency),
        source=SkillSource.SELF_REPORTED,
        confidence=Confidence.HIGH,
        verification_status=VerificationStatus.SELF_DECLARED,
        years_experience=payload.years_experience,
    )
    db.add(link)
    db.flush()
    db.add(
        SkillEvidence(
            beneficiary_skill_id=link.id,
            evidence_type="admin_note" if user.role != "beneficiary" else "conversation",
            description=f"Added manually as '{payload.label}'",
            recorded_at=utcnow(),
        )
    )
    db.commit()
    return {
        "id": link.id,
        "code": skill.code if skill else None,
        "name": skill.name if skill else payload.label,
        "matched_to_taxonomy": skill is not None,
        "verification_status": link.verification_status,
    }


@router.delete("/beneficiary/skills/{skill_link_id}", response_model=Message)
def remove_skill(
    skill_link_id: str, beneficiary: CurrentBeneficiary, db: DbSession
) -> Message:
    link = db.get(BeneficiarySkill, skill_link_id)
    if link is None or link.beneficiary_id != beneficiary.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    db.delete(link)
    db.commit()
    return Message(message="Skill removed")


# ---------------------------------------------------------------------------
# Skill gap
# ---------------------------------------------------------------------------


@router.post("/skill-gap/analyze", response_model=SkillGapResponse)
def analyze_skill_gap(
    payload: SkillGapRequest, user: CurrentUser, beneficiary: CurrentBeneficiary, db: DbSession
) -> SkillGapResponse:
    """Compare the beneficiary against one or more recognised qualifications.

    With no qualification specified, the qualifications they already cover most
    of are analysed - which is the useful default when exploring.
    """
    graph = build_skill_graph(db, beneficiary)

    query = (
        select(Qualification)
        .options(selectinload(Qualification.competency_links))
        .where(Qualification.status == RecordStatus.ACTIVE)
    )
    if payload.qualification_id:
        query = query.where(Qualification.id == payload.qualification_id)
    elif payload.qualification_code:
        query = query.where(Qualification.code == payload.qualification_code)

    qualifications = db.execute(query).scalars().unique().all()
    if not qualifications:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "No active qualification matched. Retired standards are excluded "
                "from analysis on purpose."
            ),
        )

    reports = [analyze_gap(db, beneficiary, q, graph) for q in qualifications]
    reports.sort(key=lambda r: -r.coverage_ratio)
    selected = reports[: payload.limit]
    by_id = {q.id: q for q in qualifications}

    return SkillGapResponse(
        beneficiary_id=beneficiary.id,
        skill_graph=graph.to_dict(),
        reports=[
            {
                **report.to_dict(),
                "target_graph": build_target_graph(db, by_id[report.qualification_id]),
                "minimum_education": by_id[report.qualification_id].minimum_education,
                "minimum_education_label": EDUCATION_LABEL.get(
                    by_id[report.qualification_id].minimum_education or "", None
                ),
                "source": by_id[report.qualification_id].source,
            }
            for report in selected
        ],
    )


@router.get("/skill-graph/{beneficiary_id}")
def get_skill_graph(beneficiary_id: str, user: CurrentUser, db: DbSession) -> dict:
    profile = resolve_beneficiary_for_actor(beneficiary_id, user, db)
    return build_skill_graph(db, profile).to_dict()
