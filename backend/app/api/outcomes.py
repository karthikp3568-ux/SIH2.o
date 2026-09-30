"""Phase 4 - outcome lifecycle and feedback."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..deps import CurrentBeneficiary, CurrentUser, DbSession, resolve_beneficiary_for_actor
from ..models import Opportunity, Outcome, Recommendation
from ..models.outcome import REJECTION_REASONS
from ..schemas.recommendation import (
    FeedbackIn,
    FeedbackOut,
    OutcomeCreate,
    OutcomeOut,
    OutcomeUpdate,
)
from ..services import outcomes as service

router = APIRouter(tags=["outcomes"])


@router.post("/outcomes", response_model=OutcomeOut, status_code=status.HTTP_201_CREATED)
def create_outcome(
    payload: OutcomeCreate, user: CurrentUser, beneficiary: CurrentBeneficiary, db: DbSession
) -> OutcomeOut:
    recommendation = db.get(Recommendation, payload.recommendation_id)
    if recommendation is None or recommendation.beneficiary_id != beneficiary.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    outcome = service.select_pathway(
        db, beneficiary, recommendation, actor=user, note=payload.note
    )
    opportunity = db.get(Opportunity, outcome.opportunity_id)
    return OutcomeOut(**service.outcome_to_dict(outcome, opportunity))


@router.get("/outcomes", response_model=list[OutcomeOut])
def my_outcomes(beneficiary: CurrentBeneficiary, db: DbSession) -> list[OutcomeOut]:
    rows = service.list_outcomes(db, beneficiary.id)
    opportunities = {
        o.id: o
        for o in db.execute(
            select(Opportunity).where(
                Opportunity.id.in_([row.opportunity_id for row in rows] or [""])
            )
        )
        .scalars()
        .all()
    }
    return [
        OutcomeOut(**service.outcome_to_dict(row, opportunities.get(row.opportunity_id)))
        for row in rows
    ]


@router.get("/outcomes/beneficiary/{beneficiary_id}", response_model=list[OutcomeOut])
def outcomes_for(beneficiary_id: str, user: CurrentUser, db: DbSession) -> list[OutcomeOut]:
    profile = resolve_beneficiary_for_actor(beneficiary_id, user, db)
    rows = service.list_outcomes(db, profile.id)
    opportunities = {
        o.id: o
        for o in db.execute(
            select(Opportunity).where(
                Opportunity.id.in_([row.opportunity_id for row in rows] or [""])
            )
        )
        .scalars()
        .all()
    }
    return [
        OutcomeOut(**service.outcome_to_dict(row, opportunities.get(row.opportunity_id)))
        for row in rows
    ]


@router.patch("/outcomes/{outcome_id}", response_model=OutcomeOut)
def update_outcome(
    outcome_id: str, payload: OutcomeUpdate, user: CurrentUser, db: DbSession
) -> OutcomeOut:
    """Advance the lifecycle. Invalid transitions are refused with the reason."""
    outcome = db.get(Outcome, outcome_id)
    if outcome is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Outcome not found")
    resolve_beneficiary_for_actor(outcome.beneficiary_id, user, db)

    try:
        outcome = service.update_status(
            db,
            outcome,
            str(payload.status),
            actor=user,
            note=payload.note,
            monthly_income_inr=payload.monthly_income_inr,
            exit_reason=payload.exit_reason,
        )
    except service.InvalidTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc

    opportunity = db.get(Opportunity, outcome.opportunity_id)
    return OutcomeOut(**service.outcome_to_dict(outcome, opportunity))


@router.post("/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def submit_feedback(
    payload: FeedbackIn, user: CurrentUser, beneficiary: CurrentBeneficiary, db: DbSession
) -> FeedbackOut:
    if payload.rejection_reason and payload.rejection_reason not in REJECTION_REASONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown rejection reason. Valid values: {', '.join(REJECTION_REASONS)}",
        )
    feedback = service.submit_feedback(
        db,
        beneficiary,
        actor=user,
        outcome_id=payload.outcome_id,
        recommendation_id=payload.recommendation_id,
        opportunity_id=payload.opportunity_id,
        feedback_type=payload.feedback_type,
        was_useful=payload.was_useful,
        rating=payload.rating,
        rejection_reason=payload.rejection_reason,
        comment=payload.comment,
        language=payload.language,
    )
    return FeedbackOut(
        id=feedback.id,
        feedback_type=feedback.feedback_type,
        was_useful=feedback.was_useful,
        rating=feedback.rating,
        rejection_reason=feedback.rejection_reason,
        comment=feedback.comment,
        created_at=feedback.created_at,
    )


@router.get("/feedback/reasons")
def feedback_reasons() -> list[dict]:
    """The structured rejection reasons, so feedback aggregates usefully."""
    return [{"code": code, "label": label} for code, label in REJECTION_REASONS.items()]
