"""Recommendation orchestration - Phase 3 end to end.

    profile -> skill graph -> skill gap -> hybrid retrieval
            -> structured filters -> hybrid ranking -> explanation -> persist

Nothing in this module invents an opportunity, a qualification or a scheme.
Every recommendation is a row in `opportunities` that passed every hard filter,
and every explanation line is derived from a computed factor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_ranking_config
from ..core.enums import AuditAction, EDUCATION_RANK, RecordStatus
from ..models import (
    BeneficiaryProfile,
    Opportunity,
    Qualification,
    Recommendation,
    RecommendationReason,
    RecommendationRun,
    User,
)
from . import audit
from .explanation import build_reasons, next_step_for, polish_reasons
from .ranking import ScoredCandidate, is_credible, rank_candidates, score_candidate
from .retrieval import (
    EXCLUSION_REASONS,
    Exclusion,
    RetrievalContext,
    RetrievalResult,
    context_for,
    retrieve,
)
from .skill_gap import SkillGapReport, analyze_gap
from .skill_graph import build_skill_graph


@dataclass
class NoMatchGuidance:
    """What we show instead of inventing something when nothing qualifies."""

    message: str
    closest_pathway: dict | None = None
    missing_competencies: list[dict] = field(default_factory=list)
    prerequisite_suggestions: list[dict] = field(default_factory=list)
    what_to_verify: list[str] = field(default_factory=list)
    retry_options: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "message": self.message,
            "closest_pathway": self.closest_pathway,
            "missing_competencies": self.missing_competencies,
            "prerequisite_suggestions": self.prerequisite_suggestions,
            "what_to_verify": self.what_to_verify,
            "retry_options": self.retry_options,
        }


@dataclass
class GenerationResult:
    run: RecommendationRun
    scored: list[ScoredCandidate]
    retrieval: RetrievalResult
    no_match: NoMatchGuidance | None = None


def _profile_snapshot(beneficiary: BeneficiaryProfile, ctx: RetrievalContext) -> dict:
    return {
        "education": ctx.education_level,
        "age": beneficiary.age,
        "mobility": beneficiary.mobility,
        "radius_km": ctx.radius_km,
        "goals": [g.goal_type for g in beneficiary.goals if g.is_active],
        "interests": [i.tag or i.label for i in beneficiary.interests],
        "skills": [
            {
                "raw_label": s.raw_label,
                "skill_id": s.skill_id,
                "proficiency": s.proficiency,
                "verification_status": s.verification_status,
            }
            for s in beneficiary.skills
            if s.is_active
        ],
        "location": (
            {
                "latitude": ctx.latitude,
                "longitude": ctx.longitude,
                "district": beneficiary.primary_location.district
                if beneficiary.primary_location
                else None,
            }
            if ctx.latitude is not None
            else None
        ),
        "query_text": ctx.query_text,
    }


def generate_recommendations(
    db: Session,
    beneficiary: BeneficiaryProfile,
    *,
    actor: User | None = None,
    radius_km: float | None = None,
    top_n: int | None = None,
    relax_filters: bool = False,
    opportunity_types: list[str] | None = None,
    polish: bool = True,
) -> GenerationResult:
    started = time.perf_counter()
    config = get_ranking_config()

    graph = build_skill_graph(db, beneficiary)
    ctx = context_for(
        db, beneficiary, radius_km=radius_km, graph=graph, relax_filters=relax_filters
    )
    if opportunity_types:
        ctx.opportunity_types = opportunity_types

    retrieval = retrieve(db, ctx)

    gap_cache: dict[str, SkillGapReport] = {}
    scored: list[ScoredCandidate] = []
    for candidate in retrieval.candidates:
        qualification = candidate.opportunity.qualification
        gap_report = None
        if qualification is not None:
            if qualification.id not in gap_cache:
                gap_cache[qualification.id] = analyze_gap(db, beneficiary, qualification, graph)
            gap_report = gap_cache[qualification.id]
        scored.append(score_candidate(candidate, beneficiary, graph, gap_report, ctx, config))

    # Relevance gate. Recorded as an exclusion with its reason, so "why did I
    # not see the tailoring unit in my village" has an answer.
    credible: list[ScoredCandidate] = []
    for item in scored:
        ok, reason = is_credible(item)
        if ok:
            credible.append(item)
        else:
            retrieval.exclusions.append(
                Exclusion(
                    opportunity_id=item.opportunity.id,
                    title=item.opportunity.title,
                    reason_code="NO_PROFILE_OVERLAP",
                    reason=EXCLUSION_REASONS["NO_PROFILE_OVERLAP"],
                    detail=reason,
                )
            )

    selected = rank_candidates(credible, top_n=top_n)

    run = RecommendationRun(
        beneficiary_id=beneficiary.id,
        profile_snapshot=_profile_snapshot(beneficiary, ctx),
        ranking_config={
            "weights": config["weights"],
            "top_n": top_n or config["top_n"],
            "min_score": config["min_score"],
            "retrieval": config["retrieval"],
            "freshness": config["freshness"],
            "relax_filters": relax_filters,
            "vector_retrieval_used": retrieval.used_vector,
        },
        mobility_used=beneficiary.mobility,
        radius_km_used=ctx.radius_km,
        candidates_retrieved=retrieval.considered,
        candidates_after_filters=retrieval.passed_filters,
        exclusions=[e.as_dict() for e in retrieval.exclusions],
        generated_by=actor.role if actor else "system",
    )
    db.add(run)
    db.flush()

    no_match: NoMatchGuidance | None = None
    if not selected:
        run.is_no_match = True
        no_match = build_no_match_guidance(db, beneficiary, ctx, retrieval, scored)
        run.no_match_reason = no_match.message
    else:
        for rank, item in enumerate(selected, start=1):
            _persist_recommendation(db, run, beneficiary, item, rank, polish=polish)

    run.duration_ms = int((time.perf_counter() - started) * 1000)
    audit.record(
        db,
        action=AuditAction.RECOMMENDATION_GENERATED,
        actor=actor,
        entity_type="recommendation_run",
        entity_id=run.id,
        new_value={
            "count": len(selected),
            "is_no_match": run.is_no_match,
            "radius_km": ctx.radius_km,
            "mobility": beneficiary.mobility,
            "considered": retrieval.considered,
            "passed_filters": retrieval.passed_filters,
        },
        summary=f"Generated {len(selected)} recommendation(s) for {beneficiary.display_name}",
    )
    db.commit()
    db.refresh(run)
    return GenerationResult(run=run, scored=selected, retrieval=retrieval, no_match=no_match)


def _persist_recommendation(
    db: Session,
    run: RecommendationRun,
    beneficiary: BeneficiaryProfile,
    item: ScoredCandidate,
    rank: int,
    polish: bool = True,
) -> Recommendation:
    opportunity = item.opportunity
    recommendation = Recommendation(
        run_id=run.id,
        beneficiary_id=beneficiary.id,
        opportunity_id=opportunity.id,
        qualification_id=opportunity.qualification_id,
        rank=rank,
        match_score=item.match_score,
        factor_scores=item.factor_scores(),
        factor_contributions=item.factor_contributions(),
        skill_fit_band=item.skill_fit_band,
        eligibility=item.eligibility,
        distance_km=item.candidate.distance_km,
        mobility_fit_band=item.mobility_fit_band,
        availability=item.availability,
        skill_gap_band=item.skill_gap_band,
        matched_skill_codes=item.matched_skill_codes,
        missing_competency_codes=item.missing_competency_codes,
        next_step=next_step_for(item),
    )
    db.add(recommendation)
    db.flush()

    lines = build_reasons(item)
    if polish:
        lines = polish_reasons(lines, beneficiary.preferred_language)
    for sequence, line in enumerate(lines):
        db.add(
            RecommendationReason(
                recommendation_id=recommendation.id,
                sequence=sequence,
                category=line.category,
                code=line.code,
                label=line.label,
                detail=line.detail,
                contribution=line.contribution,
            )
        )
    return recommendation


# ---------------------------------------------------------------------------
# No-match path
# ---------------------------------------------------------------------------


def build_no_match_guidance(
    db: Session,
    beneficiary: BeneficiaryProfile,
    ctx: RetrievalContext,
    retrieval: RetrievalResult,
    scored: list[ScoredCandidate],
) -> NoMatchGuidance:
    """First-class no-match response.

    We say plainly that nothing verified qualified, then give the person
    something actionable: the nearest relevant recognised pathway, what they
    would need for it, and concrete ways to widen the search. We never
    substitute an unverified or excluded listing for a real recommendation.
    """
    reason_counts: dict[str, int] = {}
    for exclusion in retrieval.exclusions:
        reason_counts[exclusion.reason_code] = reason_counts.get(exclusion.reason_code, 0) + 1

    if not retrieval.candidates and reason_counts:
        dominant = max(reason_counts.items(), key=lambda kv: kv[1])[0]
        cause = {
            "BEYOND_TRAVEL_RANGE": "every nearby listing is further than the distance you said you can travel",
            "EDUCATION_NOT_MET": "the listings we hold ask for a higher education level than your profile shows",
            "EXPIRED": "the listings we hold for your area have passed their validity date",
            "STALE_UNVERIFIED": "the listings we hold for your area have not been re-verified recently enough to show",
            "INACTIVE_STATUS": "the listings we hold for your area are not currently open",
            "RETIRED_QUALIFICATION": "the listings we hold are based on qualification standards that have been retired",
            "NO_SEATS": "the listings we hold for your area have no places left",
            "AGE_OUT_OF_RANGE": "the listings we hold have age limits outside your age",
        }.get(dominant, "no listing cleared the eligibility and availability checks")
        message = f"No verified suitable opportunity was found: {cause}."
    elif scored:
        message = (
            "No verified suitable opportunity was found. Listings were available, but none "
            "scored highly enough against your skills, goal and travel limit to recommend."
        )
    else:
        message = (
            "No verified suitable opportunity was found for your profile in the data we hold."
        )

    # Closest relevant recognised pathway, from the qualification catalogue.
    closest_pathway = None
    missing: list[dict] = []
    prerequisites: list[dict] = []

    qualifications = (
        db.execute(
            select(Qualification)
            .options(selectinload(Qualification.competency_links))
            .where(Qualification.status == RecordStatus.ACTIVE)
        )
        .scalars()
        .unique()
        .all()
    )
    graph = build_skill_graph(db, beneficiary)
    education_rank = EDUCATION_RANK.get(ctx.education_level or "", 0)

    best_report: SkillGapReport | None = None
    best_qualification: Qualification | None = None
    for qualification in qualifications:
        required_rank = EDUCATION_RANK.get(qualification.minimum_education or "", 0)
        if required_rank > education_rank:
            continue
        report = analyze_gap(db, beneficiary, qualification, graph)
        if best_report is None or report.coverage_ratio > best_report.coverage_ratio:
            best_report, best_qualification = report, qualification

    if best_report and best_qualification and best_report.coverage_ratio > 0:
        closest_pathway = {
            "qualification_id": best_qualification.id,
            "qualification_code": best_qualification.code,
            "title": best_qualification.title,
            "occupation_role": best_qualification.occupation_role,
            "nsqf_level": best_qualification.nsqf_level,
            "sector": best_qualification.sector,
            "coverage_ratio": best_report.coverage_ratio,
            "gap_band": best_report.gap_band,
            "source": best_qualification.source,
            "last_verified_at": (
                best_qualification.last_verified_at.isoformat()
                if best_qualification.last_verified_at
                else None
            ),
        }
        missing = [
            {"code": c.code, "name": c.name, "nos_code": c.nos_code, "explanation": c.explanation}
            for c in best_report.missing
            if c.is_core
        ][:6]
        prerequisites = [
            {
                "competency_code": c.code,
                "competency_name": c.name,
                "suggestion": (
                    f"Look for a short module covering '{c.name.lower()}'. "
                    "Ask the nearest training centre whether they run it as a standalone unit."
                ),
            }
            for c in best_report.missing[:3]
        ]

    retry_options = []
    if reason_counts.get("BEYOND_TRAVEL_RANGE"):
        retry_options.append(
            {
                "action": "widen_radius",
                "label": "Search a wider area",
                "detail": f"Currently limited to {ctx.radius_km:.0f} km from your location.",
            }
        )
    if reason_counts.get("EDUCATION_NOT_MET"):
        retry_options.append(
            {
                "action": "review_education",
                "label": "Check your education details",
                "detail": "If you have a higher qualification we did not record, add it and try again.",
            }
        )
    retry_options.append(
        {
            "action": "change_goal",
            "label": "Try a different goal",
            "detail": "Switching between job, apprenticeship, training and self-employment changes what is shown.",
        }
    )

    return NoMatchGuidance(
        message=message,
        closest_pathway=closest_pathway,
        missing_competencies=missing,
        prerequisite_suggestions=prerequisites,
        what_to_verify=[
            "Confirm your location and how far you are willing to travel.",
            "Confirm your highest completed education.",
            "Tell us about any other work you have done - more skills widen the search.",
        ],
        retry_options=retry_options,
    )


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


def latest_run(db: Session, beneficiary_id: str) -> RecommendationRun | None:
    return db.execute(
        select(RecommendationRun)
        .options(
            selectinload(RecommendationRun.recommendations)
            .selectinload(Recommendation.opportunity)
            .selectinload(Opportunity.training_program),
            selectinload(RecommendationRun.recommendations).selectinload(Recommendation.reasons),
            selectinload(RecommendationRun.recommendations).selectinload(
                Recommendation.qualification
            ),
        )
        .where(RecommendationRun.beneficiary_id == beneficiary_id)
        .order_by(RecommendationRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def get_recommendation(db: Session, recommendation_id: str) -> Recommendation | None:
    return db.execute(
        select(Recommendation)
        .options(
            selectinload(Recommendation.opportunity),
            selectinload(Recommendation.qualification).selectinload(
                Qualification.competency_links
            ),
            selectinload(Recommendation.reasons),
            selectinload(Recommendation.run),
        )
        .where(Recommendation.id == recommendation_id)
    ).scalar_one_or_none()
