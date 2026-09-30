"""Phase 4 - measure and learn.

`Outcome` records objective system events (what happened). `Feedback` records
subjective beneficiary opinion (what they thought). They are kept apart on
purpose: conflating them would let sentiment masquerade as evidence.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import OutcomeStatus
from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Outcome(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outcomes"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: The chosen pathway == the opportunity the beneficiary selected.
    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recommendation_id: Mapped[str | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"), index=True
    )
    qualification_id: Mapped[str | None] = mapped_column(
        ForeignKey("qualifications.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(
        String(32), default=OutcomeStatus.SELECTED, index=True, nullable=False
    )
    #: Append-only [{from, to, at, actor, note}] - the full lifecycle trail.
    status_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    employment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: employed | self_employed | none_yet | dropped_out | rejected
    outcome_type: Mapped[str | None] = mapped_column(String(32), index=True)
    monthly_income_inr: Mapped[int | None] = mapped_column(Integer)
    #: Why the pathway ended, when it ended badly.
    exit_reason: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    distance_km_at_selection: Mapped[float | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="outcome", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_outcome_beneficiary_status", "beneficiary_id", "status"),)


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Subjective signal from the beneficiary (or a counsellor on their behalf)."""

    __tablename__ = "feedback"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    outcome_id: Mapped[str | None] = mapped_column(
        ForeignKey("outcomes.id", ondelete="CASCADE"), index=True
    )
    recommendation_id: Mapped[str | None] = mapped_column(
        ForeignKey("recommendations.id", ondelete="SET NULL"), index=True
    )
    opportunity_id: Mapped[str | None] = mapped_column(
        ForeignKey("opportunities.id", ondelete="SET NULL"), index=True
    )

    #: recommendation_quality | pathway_experience | data_accuracy
    feedback_type: Mapped[str] = mapped_column(
        String(32), default="recommendation_quality", nullable=False
    )
    was_useful: Mapped[bool | None] = mapped_column(Boolean)
    rating: Mapped[int | None] = mapped_column(Integer)  # 1..5
    #: Structured rejection reason, one of REJECTION_REASONS below.
    rejection_reason: Mapped[str | None] = mapped_column(String(48), index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    submitted_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    outcome: Mapped[Outcome | None] = relationship(back_populates="feedback")


#: Structured reasons, so rejections aggregate into something actionable
#: instead of a pile of free text.
REJECTION_REASONS: dict[str, str] = {
    "too_far": "The opportunity was too far away",
    "training_unavailable": "Training was not actually available",
    "not_eligible": "I did not meet the eligibility requirements",
    "information_inaccurate": "The information shown was inaccurate",
    "income_too_low": "The income was too low",
    "timing_unsuitable": "The timing did not suit me",
    "not_interested": "I was not interested in this kind of work",
    "family_or_health": "Family or health reasons",
    "cost_too_high": "The cost was too high",
    "other": "Other reason",
}
