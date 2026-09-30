"""Public catalogue: qualifications, training programmes and opportunities.

Search here is plain structured browsing. It deliberately does *not* rank or
personalise - that is what /recommendations does. Keeping them apart means a
user can always inspect the raw, unranked data behind a recommendation.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from ..core.enums import EDUCATION_RANK, OpportunityType, RecordStatus
from ..core.geo import distance_between
from ..deps import CurrentUser, DbSession
from ..models import BeneficiaryProfile, Competency, Opportunity, Qualification, as_aware, utcnow
from ..schemas.opportunity import OpportunitySearchResult
from ..services.serializers import opportunity_out, qualification_detail, qualification_summary

router = APIRouter(tags=["catalogue"])


@router.get("/qualifications/search")
def search_qualifications(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    sector: Annotated[str | None, Query(max_length=80)] = None,
    nsqf_level: Annotated[int | None, Query(ge=1, le=10)] = None,
    max_education: Annotated[str | None, Query(max_length=32)] = None,
    include_retired: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Search recognised qualifications.

    Retired standards are excluded unless explicitly requested, and are always
    labelled with what superseded them when they are shown.
    """
    statement = select(Qualification).options(selectinload(Qualification.competency_links))
    if not include_retired:
        statement = statement.where(Qualification.status == RecordStatus.ACTIVE)
    if q:
        pattern = f"%{q.lower()}%"
        statement = statement.where(
            or_(
                func.lower(Qualification.title).like(pattern),
                func.lower(Qualification.occupation_role).like(pattern),
                func.lower(Qualification.code).like(pattern),
            )
        )
    if sector:
        statement = statement.where(func.lower(Qualification.sector) == sector.lower())
    if nsqf_level:
        statement = statement.where(Qualification.nsqf_level == nsqf_level)

    rows = db.execute(statement).scalars().unique().all()
    if max_education:
        ceiling = EDUCATION_RANK.get(max_education, 99)
        rows = [
            r
            for r in rows
            if EDUCATION_RANK.get(r.minimum_education or "", 0) <= ceiling
        ]

    rows.sort(key=lambda r: (r.sector, r.nsqf_level or 0, r.title))
    total = len(rows)
    return {
        "items": [qualification_summary(r) for r in rows[offset : offset + limit]],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def _load_qualification(db: DbSession, identifier: str) -> dict:
    qualification = db.execute(
        select(Qualification)
        .options(selectinload(Qualification.competency_links))
        .where(or_(Qualification.id == identifier, Qualification.code == identifier))
    ).scalar_one_or_none()
    if qualification is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Qualification not found")
    detail = qualification_detail(qualification)
    if qualification.status == RecordStatus.RETIRED:
        detail["warning"] = (
            "This standard is retired and is never used for recommendations."
            + (
                f" It has been superseded by {qualification.superseded_by_code}."
                if qualification.superseded_by_code
                else ""
            )
        )
    return detail


# Qualification Pack codes contain a slash ("AGR/Q1101"), which a normal path
# parameter cannot carry even percent-encoded - ASGI servers decode %2F before
# routing. Hence a dedicated `:path` route for code lookups.
@router.get("/qualifications/by-code/{code:path}")
def get_qualification_by_code(code: str, db: DbSession) -> dict:
    return _load_qualification(db, code)


@router.get("/qualifications/{qualification_id}")
def get_qualification(qualification_id: str, db: DbSession) -> dict:
    return _load_qualification(db, qualification_id)


@router.get("/competencies/search")
def search_competencies(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    sector: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[dict]:
    statement = select(Competency).where(Competency.status == RecordStatus.ACTIVE)
    if q:
        pattern = f"%{q.lower()}%"
        statement = statement.where(
            or_(func.lower(Competency.name).like(pattern), func.lower(Competency.code).like(pattern))
        )
    if sector:
        statement = statement.where(func.lower(Competency.sector) == sector.lower())
    rows = db.execute(statement.limit(limit)).scalars().all()
    return [
        {
            "id": c.id,
            "code": c.code,
            "name": c.name,
            "nos_code": c.nos_code,
            "description": c.description,
            "nsqf_level": c.nsqf_level,
            "sector": c.sector,
            "status": c.status,
        }
        for c in rows
    ]


def _search_opportunities(
    db: DbSession,
    user: CurrentUser,
    *,
    types: list[str] | None,
    q: str | None,
    sector: str | None,
    district: str | None,
    max_distance_km: float | None,
    include_unavailable: bool,
    limit: int,
    offset: int,
) -> OpportunitySearchResult:
    now = utcnow()
    statement = select(Opportunity).options(
        selectinload(Opportunity.qualification), selectinload(Opportunity.training_program)
    )
    if types:
        statement = statement.where(Opportunity.opportunity_type.in_(types))
    if q:
        pattern = f"%{q.lower()}%"
        statement = statement.where(
            or_(
                func.lower(Opportunity.title).like(pattern),
                func.lower(Opportunity.provider).like(pattern),
                func.lower(Opportunity.description).like(pattern),
            )
        )
    if sector:
        statement = statement.where(func.lower(Opportunity.sector) == sector.lower())
    if district:
        statement = statement.where(func.lower(Opportunity.district) == district.lower())

    rows = db.execute(statement).scalars().unique().all()

    if not include_unavailable:
        rows = [
            r
            for r in rows
            if r.status == RecordStatus.ACTIVE
            and (as_aware(r.valid_until) is None or as_aware(r.valid_until) >= now)
        ]

    distances: dict[str, float] = {}
    profile = db.execute(
        select(BeneficiaryProfile).where(BeneficiaryProfile.user_id == user.id)
    ).scalar_one_or_none()
    origin = profile.primary_location if profile else None
    if origin and origin.latitude is not None:
        for row in rows:
            distance = distance_between(
                origin.latitude, origin.longitude, row.latitude, row.longitude
            )
            if distance is not None:
                distances[row.id] = distance
        if max_distance_km is not None:
            rows = [r for r in rows if distances.get(r.id, 1e9) <= max_distance_km]
        rows.sort(key=lambda r: distances.get(r.id, 1e9))
    else:
        rows.sort(key=lambda r: r.title)

    total = len(rows)
    page = rows[offset : offset + limit]
    return OpportunitySearchResult(
        items=[opportunity_out(r) for r in page],
        total=total,
        limit=limit,
        offset=offset,
        distances_km={r.id: distances[r.id] for r in page if r.id in distances},
    )


@router.get("/opportunities/search", response_model=OpportunitySearchResult)
def search_opportunities(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    opportunity_type: Annotated[list[OpportunityType] | None, Query()] = None,
    sector: Annotated[str | None, Query(max_length=80)] = None,
    district: Annotated[str | None, Query(max_length=120)] = None,
    max_distance_km: Annotated[float | None, Query(ge=0, le=2000)] = None,
    include_unavailable: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OpportunitySearchResult:
    return _search_opportunities(
        db,
        user,
        types=[str(t) for t in opportunity_type] if opportunity_type else None,
        q=q,
        sector=sector,
        district=district,
        max_distance_km=max_distance_km,
        include_unavailable=include_unavailable,
        limit=limit,
        offset=offset,
    )


@router.get("/training/search", response_model=OpportunitySearchResult)
def search_training(
    user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=120)] = None,
    sector: Annotated[str | None, Query(max_length=80)] = None,
    district: Annotated[str | None, Query(max_length=120)] = None,
    max_distance_km: Annotated[float | None, Query(ge=0, le=2000)] = None,
    include_unavailable: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OpportunitySearchResult:
    """Training and apprenticeships only - a convenience view of the same data."""
    return _search_opportunities(
        db,
        user,
        types=[OpportunityType.TRAINING, OpportunityType.APPRENTICESHIP],
        q=q,
        sector=sector,
        district=district,
        max_distance_km=max_distance_km,
        include_unavailable=include_unavailable,
        limit=limit,
        offset=offset,
    )


@router.get("/opportunities/{opportunity_id}")
def get_opportunity(opportunity_id: str, db: DbSession) -> dict:
    opportunity = db.execute(
        select(Opportunity)
        .options(selectinload(Opportunity.qualification), selectinload(Opportunity.training_program))
        .where(Opportunity.id == opportunity_id)
    ).scalar_one_or_none()
    if opportunity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity not found")
    payload = opportunity_out(opportunity)
    now = utcnow()
    valid_until = as_aware(opportunity.valid_until)
    payload["availability_note"] = (
        "This listing has passed its validity date and is not recommended."
        if valid_until is not None and valid_until < now
        else None
        if opportunity.status == RecordStatus.ACTIVE
        else f"This listing is marked '{opportunity.status}' and is not recommended."
    )
    return payload
