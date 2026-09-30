"""Recommendation runs, ranked results and their explanation rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RecommendationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One generation pass. Keeping runs lets us replay how advice changed."""

    __tablename__ = "recommendation_runs"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Snapshot of profile inputs used, so an old run stays interpretable.
    profile_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    #: Weights / radii actually applied for this run.
    ranking_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    mobility_used: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    radius_km_used: Mapped[float | None] = mapped_column(Float)
    candidates_retrieved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_after_filters: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: True when nothing cleared the eligibility/availability bar.
    is_no_match: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    no_match_reason: Mapped[str | None] = mapped_column(Text)
    #: Records excluded by hard filters, with the reason. Powers "why not" views.
    exclusions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(32), default="system", nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="Recommendation.rank"
    )


class Recommendation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("recommendation_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    qualification_id: Mapped[str | None] = mapped_column(
        ForeignKey("qualifications.id", ondelete="SET NULL")
    )

    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    #: Per-factor sub-scores, 0..1, keyed by factor name.
    factor_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    #: Each factor's weighted contribution to `match_score`.
    factor_contributions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    skill_fit_band: Mapped[str] = mapped_column(String(16), default="moderate", nullable=False)
    eligibility: Mapped[str] = mapped_column(String(32), default="eligible", nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float)
    mobility_fit_band: Mapped[str] = mapped_column(String(16), default="moderate", nullable=False)
    availability: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    skill_gap_band: Mapped[str] = mapped_column(String(16), default="moderate", nullable=False)

    matched_skill_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    missing_competency_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    next_step: Mapped[str] = mapped_column(Text, nullable=False)

    #: Admin/counsellor override state.
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_action: Mapped[str | None] = mapped_column(String(16))  # accept|edit|reject
    override_note: Mapped[str | None] = mapped_column(Text)
    overridden_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    run: Mapped[RecommendationRun] = relationship(back_populates="recommendations")
    opportunity: Mapped["Opportunity"] = relationship()  # noqa: F821
    qualification: Mapped["Qualification | None"] = relationship()  # noqa: F821
    reasons: Mapped[list["RecommendationReason"]] = relationship(
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="RecommendationReason.sequence",
    )

    __table_args__ = (Index("ix_recommendation_run_rank", "run_id", "rank"),)


class RecommendationReason(UUIDPrimaryKeyMixin, Base):
    """A single human-readable explanation line, tied to a machine reason code.

    These are generated from computed factors - never free-form model output -
    so the explanation cannot drift from the score that produced it.
    """

    __tablename__ = "recommendation_reasons"

    recommendation_id: Mapped[str] = mapped_column(
        ForeignKey("recommendations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: why_fits | what_missing | next_step | caution
    category: Mapped[str] = mapped_column(String(24), default="why_fits", nullable=False)
    #: Stable machine code, e.g. SKILL_OVERLAP, NEARBY, INTEREST_MATCH.
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text)
    contribution: Mapped[float | None] = mapped_column(Float)

    recommendation: Mapped[Recommendation] = relationship(back_populates="reasons")
