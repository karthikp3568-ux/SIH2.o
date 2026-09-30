"""Recommendation, explanation, outcome and feedback schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..core.enums import Mobility, OutcomeStatus
from .opportunity import QualificationSummary


class GenerateRequest(BaseModel):
    #: Override the beneficiary's stored mobility for this run only. This is
    #: what powers the "change mobility and watch the ranking change" demo.
    mobility: Mobility | None = None
    radius_km: float | None = Field(default=None, ge=1, le=1000)
    top_n: int | None = Field(default=None, ge=1, le=10)
    opportunity_types: list[str] | None = None
    #: Explicit, user-initiated widening of the search. Never applied silently.
    search_wider: bool = False


class ReasonOut(BaseModel):
    category: str
    code: str
    label: str
    detail: str | None = None
    contribution: float | None = None


class FactorOut(BaseModel):
    code: str
    label: str
    score: float
    weight: float
    contribution: float
    detail: str | None = None


class RecommendationOut(BaseModel):
    id: str
    #: The pathway identifier used by /pathways/{id}/select.
    pathway_id: str
    rank: int
    title: str
    provider: str
    opportunity_type: str
    match_score: float
    skill_fit: str
    eligibility: str
    distance_km: float | None = None
    mobility_fit: str
    availability: str
    skill_gap: str
    skill_gaps: list[str] = Field(default_factory=list)
    missing_competencies: list[dict[str, Any]] = Field(default_factory=list)
    skills_you_have: list[dict[str, Any]] = Field(default_factory=list)
    why_it_fits: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    next_step: str
    source: str
    source_url: str | None = None
    verification_status: str
    last_verified_at: datetime | None = None
    valid_until: datetime | None = None
    seats_available: int | None = None
    stipend_or_income_inr: int | None = None
    location_label: str | None = None
    district: str | None = None
    qualification: QualificationSummary | None = None
    is_selected: bool = False
    is_overridden: bool = False
    override_action: str | None = None


class NoMatchOut(BaseModel):
    message: str
    closest_pathway: dict[str, Any] | None = None
    missing_competencies: list[dict[str, Any]] = Field(default_factory=list)
    prerequisite_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    what_to_verify: list[str] = Field(default_factory=list)
    retry_options: list[dict[str, Any]] = Field(default_factory=list)


class RecommendationRunOut(BaseModel):
    beneficiary_id: str
    run_id: str
    generated_at: datetime
    mobility_used: str
    radius_km_used: float | None = None
    candidates_considered: int
    candidates_after_filters: int
    is_no_match: bool = False
    no_match: NoMatchOut | None = None
    recommendations: list[RecommendationOut] = Field(default_factory=list)
    #: Records that were filtered out, with the reason. Shown on request.
    exclusions: list[dict[str, Any]] = Field(default_factory=list)
    ranking_weights: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int | None = None


class ExplanationOut(BaseModel):
    recommendation_id: str
    pathway_id: str
    title: str
    match_score: float
    #: Per-factor scores and their weighted contribution to the total.
    factors: list[FactorOut]
    why_it_fits: list[ReasonOut]
    what_is_missing: list[ReasonOut]
    cautions: list[ReasonOut]
    next_step: ReasonOut | None = None
    skill_gap_detail: dict[str, Any] | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    #: Plain statement of how the score was produced. No hidden reasoning.
    method_note: str = (
        "This score is a weighted average of the factors listed above. Each factor is "
        "computed from your profile and the verified listing; no part of it is generated text."
    )


class SelectPathwayRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class OutcomeOut(BaseModel):
    id: str
    beneficiary_id: str
    opportunity_id: str
    recommendation_id: str | None = None
    qualification_id: str | None = None
    status: OutcomeStatus
    status_history: list[dict[str, Any]] = Field(default_factory=list)
    outcome_type: str | None = None
    monthly_income_inr: int | None = None
    exit_reason: str | None = None
    notes: str | None = None
    is_active: bool
    selected_at: str | None = None
    enrolled_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    employment_at: str | None = None
    allowed_next: list[str] = Field(default_factory=list)
    opportunity: dict[str, Any] | None = None


class OutcomeCreate(BaseModel):
    recommendation_id: str
    note: str | None = Field(default=None, max_length=1000)


class OutcomeUpdate(BaseModel):
    status: OutcomeStatus
    note: str | None = Field(default=None, max_length=1000)
    monthly_income_inr: int | None = Field(default=None, ge=0)
    exit_reason: str | None = Field(default=None, max_length=64)


class FeedbackIn(BaseModel):
    outcome_id: str | None = None
    recommendation_id: str | None = None
    opportunity_id: str | None = None
    feedback_type: str = Field(
        default="recommendation_quality",
        pattern="^(recommendation_quality|pathway_experience|data_accuracy)$",
    )
    was_useful: bool | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    rejection_reason: str | None = Field(default=None, max_length=48)
    comment: str | None = Field(default=None, max_length=2000)
    language: str = Field(default="en", max_length=8)


class FeedbackOut(BaseModel):
    id: str
    feedback_type: str
    was_useful: bool | None = None
    rating: int | None = None
    rejection_reason: str | None = None
    comment: str | None = None
    created_at: datetime


class OverrideRequest(BaseModel):
    """Counsellor/admin decision on an AI recommendation."""

    action: str = Field(pattern="^(accept|edit|reject)$")
    note: str = Field(min_length=3, max_length=2000)
    #: For `edit`: an adjusted next step shown to the beneficiary instead.
    revised_next_step: str | None = Field(default=None, max_length=1000)
