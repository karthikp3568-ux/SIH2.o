"""Phase 3 - generate, read, explain and select recommendations."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..config import get_ranking_config
from ..deps import CurrentBeneficiary, CurrentUser, DbSession, resolve_beneficiary_for_actor
from ..models import Opportunity, Qualification, Recommendation, RecommendationRun
from ..schemas.recommendation import (
    ExplanationOut,
    GenerateRequest,
    OutcomeOut,
    RecommendationRunOut,
    SelectPathwayRequest,
)
from ..services import outcomes as outcome_service
from ..services.recommendation import (
    generate_recommendations,
    get_recommendation,
    latest_run,
)
from ..services.serializers import explanation_out, run_out
from ..services.skill_gap import analyze_gap
from ..services.skill_graph import build_skill_graph

router = APIRouter(tags=["recommendations"])


@router.post("/recommendations/generate", response_model=RecommendationRunOut)
def generate(
    payload: GenerateRequest,
    user: CurrentUser,
    beneficiary: CurrentBeneficiary,
    db: DbSession,
) -> RecommendationRunOut:
    """Run the full pipeline.

    `mobility` overrides the stored value for this run only - it does not
    silently rewrite the beneficiary's profile. That is what lets the demo show
    the same person's ranking change when their travel limit changes.
    """
    original_mobility = beneficiary.mobility
    if payload.mobility is not None:
        beneficiary.mobility = str(payload.mobility)

    try:
        result = generate_recommendations(
            db,
            beneficiary,
            actor=user,
            radius_km=payload.radius_km,
            top_n=payload.top_n,
            relax_filters=payload.search_wider,
            opportunity_types=payload.opportunity_types,
        )
    finally:
        if payload.mobility is not None:
            beneficiary.mobility = original_mobility
            db.commit()

    return RecommendationRunOut(
        **run_out(
            db,
            result.run,
            no_match=result.no_match.as_dict() if result.no_match else None,
        )
    )


@router.get("/recommendations/{beneficiary_id}", response_model=RecommendationRunOut)
def get_latest(
    beneficiary_id: str,
    user: CurrentUser,
    db: DbSession,
    include_exclusions: bool = Query(default=True),
) -> RecommendationRunOut:
    """Most recent run for a beneficiary."""
    profile = resolve_beneficiary_for_actor(beneficiary_id, user, db)
    run = latest_run(db, profile.id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No recommendations have been generated yet.",
        )
    return RecommendationRunOut(
        **run_out(db, run, include_exclusions=include_exclusions)
    )


@router.get("/recommendations/{beneficiary_id}/history")
def get_history(beneficiary_id: str, user: CurrentUser, db: DbSession) -> list[dict]:
    """Every run, newest first. Shows how advice changed as the profile changed."""
    profile = resolve_beneficiary_for_actor(beneficiary_id, user, db)
    runs = (
        db.execute(
            select(RecommendationRun)
            .options(selectinload(RecommendationRun.recommendations))
            .where(RecommendationRun.beneficiary_id == profile.id)
            .order_by(RecommendationRun.created_at.desc())
            .limit(25)
        )
        .scalars()
        .unique()
        .all()
    )
    return [
        {
            "run_id": run.id,
            "generated_at": run.created_at.isoformat(),
            "mobility_used": run.mobility_used,
            "radius_km_used": run.radius_km_used,
            "is_no_match": run.is_no_match,
            "count": len(run.recommendations),
            "duration_ms": run.duration_ms,
            "top_titles": [
                r.opportunity.title
                for r in sorted(run.recommendations, key=lambda r: r.rank)[:3]
                if r.opportunity
            ],
        }
        for run in runs
    ]


@router.get("/recommendations/detail/{recommendation_id}/explanation", response_model=ExplanationOut)
def explanation(recommendation_id: str, user: CurrentUser, db: DbSession) -> ExplanationOut:
    """Per-recommendation explainability: factors, reasons, gap and provenance."""
    recommendation = get_recommendation(db, recommendation_id)
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    profile = resolve_beneficiary_for_actor(recommendation.beneficiary_id, user, db)

    skill_gap = None
    if recommendation.qualification is not None:
        graph = build_skill_graph(db, profile)
        skill_gap = analyze_gap(db, profile, recommendation.qualification, graph).to_dict()

    return ExplanationOut(**explanation_out(db, recommendation, skill_gap))


@router.post("/pathways/{pathway_id}/select", response_model=OutcomeOut)
def select_pathway(
    pathway_id: str,
    payload: SelectPathwayRequest,
    user: CurrentUser,
    beneficiary: CurrentBeneficiary,
    db: DbSession,
) -> OutcomeOut:
    """The beneficiary chooses a pathway.

    `pathway_id` is the opportunity id carried on each recommendation. We
    resolve it back to the most recent recommendation for this beneficiary so
    the choice is linked to the advice that produced it.
    """
    recommendation = db.execute(
        select(Recommendation)
        .options(selectinload(Recommendation.opportunity))
        .where(
            Recommendation.beneficiary_id == beneficiary.id,
            Recommendation.opportunity_id == pathway_id,
        )
        .order_by(Recommendation.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if recommendation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "That pathway was not among your recommendations. Generate "
                "recommendations first, then choose from them."
            ),
        )
    if recommendation.override_action == "reject":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A counsellor has flagged this pathway as unsuitable. "
                "Please review their note before proceeding."
            ),
        )

    outcome = outcome_service.select_pathway(
        db, beneficiary, recommendation, actor=user, note=payload.note
    )
    opportunity = db.get(Opportunity, outcome.opportunity_id)
    return OutcomeOut(**outcome_service.outcome_to_dict(outcome, opportunity))


@router.get("/recommendations/{beneficiary_id}/exclusions")
def exclusions(beneficiary_id: str, user: CurrentUser, db: DbSession) -> dict:
    """Why listings were filtered out. Answers "why did I not see X?"."""
    profile = resolve_beneficiary_for_actor(beneficiary_id, user, db)
    run = latest_run(db, profile.id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No recommendation run found."
        )
    grouped: dict[str, list[dict]] = {}
    for exclusion in run.exclusions or []:
        grouped.setdefault(exclusion["reason_code"], []).append(exclusion)
    return {
        "run_id": run.id,
        "considered": run.candidates_retrieved,
        "passed_filters": run.candidates_after_filters,
        "by_reason": [
            {
                "reason_code": code,
                "reason": items[0]["reason"],
                "count": len(items),
                "items": items,
            }
            for code, items in sorted(grouped.items(), key=lambda kv: -len(kv[1]))
        ],
    }


@router.get("/pathways/preview")
def preview_pathways(
    user: CurrentUser, beneficiary: CurrentBeneficiary, db: DbSession
) -> list[dict]:
    """Qualification-level pathways with the beneficiary's coverage of each.

    Useful before any opportunity exists nearby - it shows where they stand
    against recognised standards independently of current listings.
    """
    graph = build_skill_graph(db, beneficiary)
    qualifications = (
        db.execute(
            select(Qualification)
            .options(selectinload(Qualification.competency_links))
            .where(Qualification.status == "active")
        )
        .scalars()
        .unique()
        .all()
    )
    reports = [analyze_gap(db, beneficiary, q, graph) for q in qualifications]
    reports.sort(key=lambda r: -r.coverage_ratio)
    top_n = int(get_ranking_config()["top_n"]) * 2
    return [r.to_dict() for r in reports[:top_n]]
