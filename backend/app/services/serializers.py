"""ORM -> API shape conversion.

Kept out of the route handlers so the response contract lives in one place and
can be tested directly.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Competency, Opportunity, Recommendation, RecommendationRun, Skill
from .ranking import explain_weights

FACTOR_LABELS = {
    "skill_fit": "Skills you already have",
    "qualification_fit": "Eligibility and level step",
    "aspiration_fit": "What you said you want",
    "gap_compatibility": "How reachable the skill gap is",
    "location_fit": "Distance from you",
    "mobility_fit": "Travel the opportunity needs",
    "availability": "Places currently available",
    "freshness": "How recently the listing was confirmed",
    "verification": "Source trust and verification status",
}


def qualification_summary(qualification) -> dict | None:
    if qualification is None:
        return None
    return {
        "id": qualification.id,
        "code": qualification.code,
        "title": qualification.title,
        "occupation_role": qualification.occupation_role,
        "sector": qualification.sector,
        "nsqf_level": qualification.nsqf_level,
        "status": qualification.status,
        "minimum_education": qualification.minimum_education,
        "source": qualification.source,
        "last_verified_at": qualification.last_verified_at,
        "superseded_by_code": qualification.superseded_by_code,
    }


def qualification_detail(qualification) -> dict:
    summary = qualification_summary(qualification) or {}
    return {
        **summary,
        "description": qualification.description,
        "sub_sector": qualification.sub_sector,
        "typical_duration_hours": qualification.typical_duration_hours,
        "version": qualification.version,
        "source_url": qualification.source_url,
        "competencies": [
            {
                "code": link.competency.code,
                "name": link.competency.name,
                "nos_code": link.competency.nos_code,
                "description": link.competency.description,
                "nsqf_level": link.competency.nsqf_level,
                "is_core": link.is_core,
                "sequence": link.sequence,
                "weight": link.weight,
                "status": link.competency.status,
            }
            for link in sorted(qualification.competency_links, key=lambda l: l.sequence)
            if link.competency is not None
        ],
    }


def opportunity_out(opportunity: Opportunity) -> dict:
    return {
        "id": opportunity.id,
        "title": opportunity.title,
        "provider": opportunity.provider,
        "opportunity_type": opportunity.opportunity_type,
        "description": opportunity.description,
        "sector": opportunity.sector,
        "qualification_id": opportunity.qualification_id,
        "qualification": qualification_summary(opportunity.qualification),
        "skills_required": opportunity.skills_required or [],
        "skill_codes": opportunity.skill_codes or [],
        "competencies_required": opportunity.competencies_required or [],
        "education_required": opportunity.education_required,
        "min_age": opportunity.min_age,
        "max_age": opportunity.max_age,
        "eligibility_notes": opportunity.eligibility_notes,
        "location_label": opportunity.location_label,
        "village": opportunity.village,
        "block": opportunity.block,
        "district": opportunity.district,
        "state": opportunity.state,
        "pincode": opportunity.pincode,
        "latitude": opportunity.latitude,
        "longitude": opportunity.longitude,
        "mobility_required": opportunity.mobility_required,
        "stipend_or_income_inr": opportunity.stipend_or_income_inr,
        "seats_total": opportunity.seats_total,
        "seats_available": opportunity.seats_available,
        "source": opportunity.source,
        "source_url": opportunity.source_url,
        "ingestion_channel": opportunity.ingestion_channel,
        "source_trust": opportunity.source_trust,
        "verification_status": opportunity.verification_status,
        "status": opportunity.status,
        "last_verified_at": opportunity.last_verified_at,
        "valid_from": opportunity.valid_from,
        "valid_until": opportunity.valid_until,
        "external_id": opportunity.external_id,
        "training_program": (
            {
                "id": opportunity.training_program.id,
                "training_centre": opportunity.training_program.training_centre,
                "duration_hours": opportunity.training_program.duration_hours,
                "duration_weeks": opportunity.training_program.duration_weeks,
                "mode": opportunity.training_program.mode,
                "fee_inr": opportunity.training_program.fee_inr,
                "is_subsidised": opportunity.training_program.is_subsidised,
                "funding_notes": opportunity.training_program.funding_notes,
                "batch_start_date": opportunity.training_program.batch_start_date,
                "batch_end_date": opportunity.training_program.batch_end_date,
                "certification_offered": opportunity.training_program.certification_offered,
                "languages_of_instruction": opportunity.training_program.languages_of_instruction,
            }
            if opportunity.training_program
            else None
        ),
        "created_at": opportunity.created_at,
        "updated_at": opportunity.updated_at,
    }


def _competency_names(db: Session, codes: list[str]) -> list[dict]:
    if not codes:
        return []
    rows = db.execute(
        select(Competency.code, Competency.name, Competency.nos_code).where(
            Competency.code.in_(codes)
        )
    ).all()
    lookup = {code: (name, nos) for code, name, nos in rows}
    return [
        {
            "code": code,
            "name": lookup.get(code, (code, None))[0],
            "nos_code": lookup.get(code, (code, None))[1],
        }
        for code in codes
    ]


def _skill_names(db: Session, codes: list[str]) -> list[dict]:
    if not codes:
        return []
    rows = dict(db.execute(select(Skill.code, Skill.name).where(Skill.code.in_(codes))).all())
    return [{"code": code, "name": rows.get(code, code)} for code in codes]


def recommendation_out(db: Session, recommendation: Recommendation) -> dict:
    opportunity = recommendation.opportunity
    reasons = sorted(recommendation.reasons, key=lambda r: r.sequence)
    missing = _competency_names(db, recommendation.missing_competency_codes or [])
    return {
        "id": recommendation.id,
        "pathway_id": recommendation.opportunity_id,
        "rank": recommendation.rank,
        "title": opportunity.title,
        "provider": opportunity.provider,
        "opportunity_type": opportunity.opportunity_type,
        "match_score": recommendation.match_score,
        "skill_fit": recommendation.skill_fit_band,
        "eligibility": recommendation.eligibility,
        "distance_km": recommendation.distance_km,
        "mobility_fit": recommendation.mobility_fit_band,
        "availability": recommendation.availability,
        "skill_gap": recommendation.skill_gap_band,
        "skill_gaps": [m["name"] for m in missing],
        "missing_competencies": missing,
        "skills_you_have": _skill_names(db, recommendation.matched_skill_codes or []),
        "why_it_fits": [r.label for r in reasons if r.category == "why_fits"],
        "cautions": [r.label for r in reasons if r.category == "caution"],
        "next_step": recommendation.next_step,
        "source": opportunity.source,
        "source_url": opportunity.source_url,
        "verification_status": opportunity.verification_status,
        "last_verified_at": opportunity.last_verified_at,
        "valid_until": opportunity.valid_until,
        "seats_available": opportunity.seats_available,
        "stipend_or_income_inr": opportunity.stipend_or_income_inr,
        "location_label": opportunity.location_label,
        "district": opportunity.district,
        "qualification": qualification_summary(recommendation.qualification),
        "is_selected": recommendation.is_selected,
        "is_overridden": recommendation.is_overridden,
        "override_action": recommendation.override_action,
    }


def run_out(
    db: Session,
    run: RecommendationRun,
    *,
    no_match: dict | None = None,
    include_exclusions: bool = True,
) -> dict:
    return {
        "beneficiary_id": run.beneficiary_id,
        "run_id": run.id,
        "generated_at": run.created_at,
        "mobility_used": run.mobility_used,
        "radius_km_used": run.radius_km_used,
        "candidates_considered": run.candidates_retrieved,
        "candidates_after_filters": run.candidates_after_filters,
        "is_no_match": run.is_no_match,
        "no_match": no_match,
        "recommendations": [
            recommendation_out(db, r) for r in sorted(run.recommendations, key=lambda r: r.rank)
        ],
        "exclusions": (run.exclusions or []) if include_exclusions else [],
        "ranking_weights": explain_weights(),
        "duration_ms": run.duration_ms,
    }


def explanation_out(
    db: Session, recommendation: Recommendation, skill_gap: dict[str, Any] | None = None
) -> dict:
    reasons = sorted(recommendation.reasons, key=lambda r: r.sequence)

    def serialise(category: str) -> list[dict]:
        return [
            {
                "category": r.category,
                "code": r.code,
                "label": r.label,
                "detail": r.detail,
                "contribution": r.contribution,
            }
            for r in reasons
            if r.category == category
        ]

    next_steps = serialise("next_step")
    factor_scores = recommendation.factor_scores or {}
    contributions = recommendation.factor_contributions or {}
    weights = {w["code"]: w["weight"] for w in explain_weights()}

    return {
        "recommendation_id": recommendation.id,
        "pathway_id": recommendation.opportunity_id,
        "title": recommendation.opportunity.title,
        "match_score": recommendation.match_score,
        "factors": [
            {
                "code": code,
                "label": FACTOR_LABELS.get(code, code),
                "score": score,
                "weight": weights.get(code, 0.0),
                "contribution": contributions.get(code, 0.0),
                "detail": None,
            }
            for code, score in sorted(factor_scores.items(), key=lambda kv: -contributions.get(kv[0], 0))
        ],
        "why_it_fits": serialise("why_fits"),
        "what_is_missing": serialise("what_missing"),
        "cautions": serialise("caution"),
        "next_step": next_steps[0] if next_steps else None,
        "skill_gap_detail": skill_gap,
        "evidence": {
            "source": recommendation.opportunity.source,
            "source_url": recommendation.opportunity.source_url,
            "verification_status": recommendation.opportunity.verification_status,
            "last_verified_at": (
                recommendation.opportunity.last_verified_at.isoformat()
                if recommendation.opportunity.last_verified_at
                else None
            ),
            "qualification": qualification_summary(recommendation.qualification),
            "ranking_config": recommendation.run.ranking_config if recommendation.run else {},
        },
    }
