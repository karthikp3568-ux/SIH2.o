"""Admin analytics.

Every number here is computed from rows in this database. Nothing is projected,
extrapolated or presented as real-world impact. When the database only contains
seeded demo records, `is_demo_data` is true and the UI labels the whole
dashboard as sample data.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_ranking_config
from ..core.enums import OutcomeStatus, RecordStatus, VerificationStatus
from ..models import (
    BeneficiaryProfile,
    Feedback,
    Opportunity,
    Outcome,
    Recommendation,
    RecommendationRun,
    User,
    as_aware,
    utcnow,
)
from ..models.outcome import REJECTION_REASONS


def _count(db: Session, statement) -> int:
    return int(db.execute(statement).scalar_one() or 0)


def overview(db: Session) -> dict:
    now = utcnow()
    config = get_ranking_config()
    stale_after = int(config["freshness"]["stale_after_days"])
    hard_stale = int(config["freshness"]["hard_stale_days"])

    total_beneficiaries = _count(db, select(func.count(BeneficiaryProfile.id)))
    confirmed = _count(
        db,
        select(func.count(BeneficiaryProfile.id)).where(
            BeneficiaryProfile.is_confirmed.is_(True)
        ),
    )

    opportunities = db.execute(select(Opportunity)).scalars().all()
    active = [
        o
        for o in opportunities
        if o.status == RecordStatus.ACTIVE
        and (as_aware(o.valid_until) is None or as_aware(o.valid_until) >= now)
    ]
    stale = [
        o
        for o in active
        if as_aware(o.last_verified_at) is None
        or as_aware(o.last_verified_at) < now - timedelta(days=stale_after)
    ]
    hard_stale_records = [
        o
        for o in opportunities
        if as_aware(o.last_verified_at) is None
        or as_aware(o.last_verified_at) < now - timedelta(days=hard_stale)
    ]
    expired = [
        o
        for o in opportunities
        if as_aware(o.valid_until) is not None and as_aware(o.valid_until) < now
    ]

    runs = _count(db, select(func.count(RecommendationRun.id)))
    no_match_runs = _count(
        db, select(func.count(RecommendationRun.id)).where(RecommendationRun.is_no_match.is_(True))
    )
    recommendations = _count(db, select(func.count(Recommendation.id)))
    selected = _count(
        db, select(func.count(Recommendation.id)).where(Recommendation.is_selected.is_(True))
    )
    overridden = _count(
        db, select(func.count(Recommendation.id)).where(Recommendation.is_overridden.is_(True))
    )

    outcome_counts = dict(
        db.execute(select(Outcome.status, func.count(Outcome.id)).group_by(Outcome.status)).all()
    )
    average_distance = db.execute(
        select(func.avg(Recommendation.distance_km)).where(Recommendation.distance_km.is_not(None))
    ).scalar()

    feedback_total = _count(db, select(func.count(Feedback.id)))
    feedback_useful = _count(
        db, select(func.count(Feedback.id)).where(Feedback.was_useful.is_(True))
    )
    average_rating = db.execute(
        select(func.avg(Feedback.rating)).where(Feedback.rating.is_not(None))
    ).scalar()

    return {
        "is_demo_data": _looks_like_demo_data(db),
        "generated_at": now.isoformat(),
        "beneficiaries": {
            "total": total_beneficiaries,
            "profile_confirmed": confirmed,
            "profile_unconfirmed": total_beneficiaries - confirmed,
        },
        "opportunities": {
            "total": len(opportunities),
            "active": len(active),
            "inactive": len([o for o in opportunities if o.status != RecordStatus.ACTIVE]),
            "expired": len(expired),
            "stale_needs_reverification": len(stale),
            "excluded_as_hard_stale": len(hard_stale_records),
            "verified": len(
                [
                    o
                    for o in opportunities
                    if o.verification_status
                    in {VerificationStatus.ADMIN_VERIFIED, VerificationStatus.CERTIFICATION_VERIFIED}
                ]
            ),
            "by_type": _group(opportunities, lambda o: o.opportunity_type),
            "by_sector": _group(opportunities, lambda o: o.sector or "unspecified"),
        },
        "recommendations": {
            "runs": runs,
            "no_match_runs": no_match_runs,
            "generated": recommendations,
            "selected": selected,
            "overridden": overridden,
            "acceptance_rate": round(selected / recommendations, 4) if recommendations else None,
            "average_distance_km": round(float(average_distance), 1) if average_distance else None,
        },
        "outcomes": {
            "total": sum(outcome_counts.values()),
            "by_status": outcome_counts,
            "enrolled": outcome_counts.get(OutcomeStatus.ENROLLED, 0),
            "attending": outcome_counts.get(OutcomeStatus.ATTENDING, 0),
            "completed": outcome_counts.get(OutcomeStatus.COMPLETED, 0),
            "employed": outcome_counts.get(OutcomeStatus.EMPLOYED, 0),
            "self_employed": outcome_counts.get(OutcomeStatus.SELF_EMPLOYED, 0),
            "dropped_out": outcome_counts.get(OutcomeStatus.DROPPED_OUT, 0),
        },
        "feedback": {
            "total": feedback_total,
            "found_useful": feedback_useful,
            "average_rating": round(float(average_rating), 2) if average_rating else None,
            "rejection_reasons": _rejection_breakdown(db),
        },
        "users": {
            "total": _count(db, select(func.count(User.id))),
            "by_role": dict(
                db.execute(select(User.role, func.count(User.id)).group_by(User.role)).all()
            ),
        },
    }


def _group(items, key) -> dict[str, int]:
    tally: dict[str, int] = {}
    for item in items:
        value = key(item)
        tally[value] = tally.get(value, 0) + 1
    return dict(sorted(tally.items(), key=lambda kv: -kv[1]))


def _rejection_breakdown(db: Session) -> list[dict]:
    rows = db.execute(
        select(Feedback.rejection_reason, func.count(Feedback.id))
        .where(Feedback.rejection_reason.is_not(None))
        .group_by(Feedback.rejection_reason)
    ).all()
    return [
        {"code": code, "label": REJECTION_REASONS.get(code, code), "count": int(count)}
        for code, count in sorted(rows, key=lambda r: -r[1])
    ]


def top_skill_gaps(db: Session, limit: int = 10) -> list[dict]:
    """Most frequently missing competencies across generated recommendations."""
    tally: dict[str, int] = {}
    for recommendation in db.execute(select(Recommendation)).scalars().all():
        for code in recommendation.missing_competency_codes or []:
            tally[code] = tally.get(code, 0) + 1
    from ..models import Competency  # noqa: PLC0415 - avoids a module cycle

    names = dict(db.execute(select(Competency.code, Competency.name)).all())
    return [
        {"code": code, "name": names.get(code, code), "count": count}
        for code, count in sorted(tally.items(), key=lambda kv: -kv[1])[:limit]
    ]


def opportunity_freshness(db: Session, limit: int = 20) -> list[dict]:
    """Records most in need of re-verification, oldest first."""
    now = utcnow()
    rows = []
    for opportunity in db.execute(select(Opportunity)).scalars().all():
        last_verified = as_aware(opportunity.last_verified_at)
        age_days = (now - last_verified).days if last_verified else None
        rows.append(
            {
                "id": opportunity.id,
                "title": opportunity.title,
                "provider": opportunity.provider,
                "status": opportunity.status,
                "verification_status": opportunity.verification_status,
                "last_verified_at": last_verified.isoformat() if last_verified else None,
                "days_since_verified": age_days,
                "valid_until": (
                    as_aware(opportunity.valid_until).isoformat()
                    if opportunity.valid_until
                    else None
                ),
            }
        )
    rows.sort(key=lambda r: (-1 if r["days_since_verified"] is None else -r["days_since_verified"]))
    return rows[:limit]


def _looks_like_demo_data(db: Session) -> bool:
    """True while every opportunity still comes from the bundled seed set."""
    non_seed = _count(
        db,
        select(func.count(Opportunity.id)).where(Opportunity.ingestion_channel != "seed"),
    )
    return non_seed == 0
