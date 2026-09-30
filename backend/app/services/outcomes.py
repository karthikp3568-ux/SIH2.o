"""Phase 4 - pathway selection, lifecycle tracking and feedback.

Transitions are validated server side against OUTCOME_TRANSITIONS, and every
change appends to `status_history`. The trail is what later lets us ask honest
questions of the data: which recommendations turned into enrolments, which
enrolments turned into work, and where people dropped out.

Note on wording: outcome data *informs* future matching (it is surfaced in
analytics and intended as the input for re-tuning ranking weights). There is no
automatic online learning in this prototype, and the code does not claim any.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..core.enums import (
    OUTCOME_TRANSITIONS,
    AuditAction,
    OutcomeStatus,
)
from ..models import (
    BeneficiaryProfile,
    Feedback,
    Opportunity,
    Outcome,
    Recommendation,
    User,
    utcnow,
)
from . import audit


class InvalidTransition(ValueError):
    """Raised when a caller asks for a lifecycle step that is not allowed."""


def _history_entry(from_status: str | None, to_status: str, actor: User | None, note: str | None) -> dict:
    return {
        "from": from_status,
        "to": to_status,
        "at": utcnow().isoformat(),
        "actor": actor.email if actor else "system",
        "actor_role": actor.role if actor else "system",
        "note": note,
    }


def select_pathway(
    db: Session,
    beneficiary: BeneficiaryProfile,
    recommendation: Recommendation,
    *,
    actor: User | None = None,
    note: str | None = None,
) -> Outcome:
    """The beneficiary chooses a pathway. This is their decision, not the AI's."""
    existing = db.execute(
        select(Outcome).where(
            Outcome.beneficiary_id == beneficiary.id,
            Outcome.opportunity_id == recommendation.opportunity_id,
            Outcome.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    # A person may pursue more than one pathway, but only one is "current";
    # earlier active ones are marked as changed rather than deleted.
    for other in db.execute(
        select(Outcome).where(
            Outcome.beneficiary_id == beneficiary.id, Outcome.is_active.is_(True)
        )
    ).scalars().all():
        other.is_active = False
        other.status_history = [
            *other.status_history,
            _history_entry(other.status, OutcomeStatus.CHANGED_PATHWAY, actor, "Another pathway was selected"),
        ]
        other.status = OutcomeStatus.CHANGED_PATHWAY
        other.closed_at = utcnow()

    now = utcnow()
    outcome = Outcome(
        beneficiary_id=beneficiary.id,
        opportunity_id=recommendation.opportunity_id,
        recommendation_id=recommendation.id,
        qualification_id=recommendation.qualification_id,
        status=OutcomeStatus.SELECTED,
        status_history=[_history_entry(OutcomeStatus.RECOMMENDED, OutcomeStatus.SELECTED, actor, note)],
        selected_at=now,
        outcome_type="none_yet",
        distance_km_at_selection=int(recommendation.distance_km) if recommendation.distance_km else None,
        notes=note,
    )
    db.add(outcome)
    recommendation.is_selected = True

    audit.record(
        db,
        action=AuditAction.PATHWAY_SELECTED,
        actor=actor,
        entity_type="outcome",
        entity_id=outcome.id,
        new_value={
            "opportunity_id": recommendation.opportunity_id,
            "recommendation_id": recommendation.id,
            "rank": recommendation.rank,
            "match_score": recommendation.match_score,
        },
        summary=f"{beneficiary.display_name} selected a pathway",
    )
    db.commit()
    db.refresh(outcome)
    return outcome


_TIMESTAMP_FIELDS = {
    OutcomeStatus.ENROLLED: "enrolled_at",
    OutcomeStatus.ATTENDING: "started_at",
    OutcomeStatus.COMPLETED: "completed_at",
    OutcomeStatus.EMPLOYED: "employment_at",
    OutcomeStatus.SELF_EMPLOYED: "employment_at",
}

_OUTCOME_TYPES = {
    OutcomeStatus.EMPLOYED: "employed",
    OutcomeStatus.SELF_EMPLOYED: "self_employed",
    OutcomeStatus.DROPPED_OUT: "dropped_out",
    OutcomeStatus.REJECTED: "rejected",
}


def update_status(
    db: Session,
    outcome: Outcome,
    new_status: str,
    *,
    actor: User | None = None,
    note: str | None = None,
    monthly_income_inr: int | None = None,
    exit_reason: str | None = None,
) -> Outcome:
    allowed = OUTCOME_TRANSITIONS.get(outcome.status, set())
    if new_status not in allowed:
        raise InvalidTransition(
            f"Cannot move from '{outcome.status}' to '{new_status}'. "
            f"Allowed next steps: {', '.join(sorted(allowed)) or 'none'}."
        )

    previous = outcome.status
    outcome.status = new_status
    outcome.status_history = [
        *outcome.status_history,
        _history_entry(previous, new_status, actor, note),
    ]
    timestamp_field = _TIMESTAMP_FIELDS.get(new_status)
    if timestamp_field:
        setattr(outcome, timestamp_field, utcnow())
    if new_status in _OUTCOME_TYPES:
        outcome.outcome_type = _OUTCOME_TYPES[new_status]
    if monthly_income_inr is not None:
        outcome.monthly_income_inr = monthly_income_inr
    if exit_reason:
        outcome.exit_reason = exit_reason
    if note:
        outcome.notes = note
    if new_status in {
        OutcomeStatus.DROPPED_OUT,
        OutcomeStatus.REJECTED,
        OutcomeStatus.CHANGED_PATHWAY,
        OutcomeStatus.OPPORTUNITY_INACTIVE,
    }:
        outcome.closed_at = utcnow()
        outcome.is_active = False

    audit.record(
        db,
        action=AuditAction.OUTCOME_UPDATED,
        actor=actor,
        entity_type="outcome",
        entity_id=outcome.id,
        old_value={"status": previous},
        new_value={"status": new_status, "note": note},
        summary=f"Outcome moved from {previous} to {new_status}",
    )
    db.commit()
    db.refresh(outcome)
    return outcome


def submit_feedback(
    db: Session,
    beneficiary: BeneficiaryProfile,
    *,
    actor: User | None = None,
    outcome_id: str | None = None,
    recommendation_id: str | None = None,
    opportunity_id: str | None = None,
    feedback_type: str = "recommendation_quality",
    was_useful: bool | None = None,
    rating: int | None = None,
    rejection_reason: str | None = None,
    comment: str | None = None,
    language: str = "en",
) -> Feedback:
    feedback = Feedback(
        beneficiary_id=beneficiary.id,
        outcome_id=outcome_id,
        recommendation_id=recommendation_id,
        opportunity_id=opportunity_id,
        feedback_type=feedback_type,
        was_useful=was_useful,
        rating=rating,
        rejection_reason=rejection_reason,
        comment=comment,
        language=language,
        submitted_by_user_id=actor.id if actor else None,
    )
    db.add(feedback)
    audit.record(
        db,
        action=AuditAction.FEEDBACK_SUBMITTED,
        actor=actor,
        entity_type="feedback",
        entity_id=feedback.id,
        new_value={
            "type": feedback_type,
            "was_useful": was_useful,
            "rating": rating,
            "rejection_reason": rejection_reason,
        },
        summary="Feedback submitted",
    )
    db.commit()
    db.refresh(feedback)
    return feedback


def outcome_to_dict(outcome: Outcome, opportunity: Opportunity | None = None) -> dict:
    return {
        "id": outcome.id,
        "beneficiary_id": outcome.beneficiary_id,
        "opportunity_id": outcome.opportunity_id,
        "recommendation_id": outcome.recommendation_id,
        "qualification_id": outcome.qualification_id,
        "status": outcome.status,
        "status_history": outcome.status_history,
        "outcome_type": outcome.outcome_type,
        "monthly_income_inr": outcome.monthly_income_inr,
        "exit_reason": outcome.exit_reason,
        "notes": outcome.notes,
        "is_active": outcome.is_active,
        "selected_at": outcome.selected_at.isoformat() if outcome.selected_at else None,
        "enrolled_at": outcome.enrolled_at.isoformat() if outcome.enrolled_at else None,
        "started_at": outcome.started_at.isoformat() if outcome.started_at else None,
        "completed_at": outcome.completed_at.isoformat() if outcome.completed_at else None,
        "employment_at": outcome.employment_at.isoformat() if outcome.employment_at else None,
        "allowed_next": sorted(OUTCOME_TRANSITIONS.get(outcome.status, set())),
        "opportunity": (
            {
                "id": opportunity.id,
                "title": opportunity.title,
                "provider": opportunity.provider,
                "type": opportunity.opportunity_type,
            }
            if opportunity
            else None
        ),
    }


def list_outcomes(db: Session, beneficiary_id: str) -> list[Outcome]:
    return list(
        db.execute(
            select(Outcome)
            .options(selectinload(Outcome.feedback))
            .where(Outcome.beneficiary_id == beneficiary_id)
            .order_by(Outcome.created_at.desc())
        )
        .scalars()
        .all()
    )
