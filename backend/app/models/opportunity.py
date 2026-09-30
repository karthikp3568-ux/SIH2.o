"""Opportunities: jobs, apprenticeships, training and enterprise pathways.

Freshness is a first-class property. `status`, `valid_until` and
`last_verified_at` gate whether a record may be recommended at all - see
app/services/retrieval.py.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import Mobility, RecordStatus, VerificationStatus
from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Opportunity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    provider: Mapped[str] = mapped_column(String(240), nullable=False)
    provider_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    #: job | apprenticeship | training | enterprise | self_employment
    opportunity_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str | None] = mapped_column(String(80), index=True)

    qualification_id: Mapped[str | None] = mapped_column(
        ForeignKey("qualifications.id", ondelete="SET NULL"), index=True
    )

    #: Free-text skill labels, normalised to taxonomy codes in `skill_codes`.
    skills_required: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    skill_codes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    #: Competency codes required beyond the linked qualification.
    competencies_required: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    education_required: Mapped[str | None] = mapped_column(String(32), index=True)
    min_age: Mapped[int | None] = mapped_column(Integer)
    max_age: Mapped[int | None] = mapped_column(Integer)
    #: Human-readable eligibility notes shown to the beneficiary.
    eligibility_notes: Mapped[str | None] = mapped_column(Text)
    #: Machine-checkable extras, e.g. {"requires_own_vehicle": true}.
    eligibility_rules: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    location_label: Mapped[str | None] = mapped_column(String(200))
    village: Mapped[str | None] = mapped_column(String(120))
    block: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(120), index=True)
    pincode: Mapped[str | None] = mapped_column(String(10), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    #: Minimum mobility band a beneficiary needs to realistically take this up.
    mobility_required: Mapped[str] = mapped_column(
        String(16), default=Mobility.LOW, nullable=False
    )
    is_remote_or_local: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    stipend_or_income_inr: Mapped[int | None] = mapped_column(Integer)
    seats_total: Mapped[int | None] = mapped_column(Integer)
    seats_available: Mapped[int | None] = mapped_column(Integer)

    source: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    #: Who ingested it: seed | csv_import | api:<name> | admin | provider
    ingestion_channel: Mapped[str] = mapped_column(String(64), default="seed", nullable=False)
    #: How much we trust the source (0..1). Drives the `verification` ranking factor.
    source_trust: Mapped[float] = mapped_column(Float, default=0.6, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.UNVERIFIED, index=True, nullable=False
    )
    verified_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    status: Mapped[str] = mapped_column(
        String(16), default=RecordStatus.ACTIVE, index=True, nullable=False
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: Natural key from the upstream source, used to de-duplicate on re-import.
    external_id: Mapped[str | None] = mapped_column(String(160), index=True)

    qualification: Mapped["Qualification | None"] = relationship()  # noqa: F821
    training_program: Mapped["TrainingProgram | None"] = relationship(
        back_populates="opportunity", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_opportunity_geo", "latitude", "longitude"),
        Index("ix_opportunity_type_status", "opportunity_type", "status"),
        Index("ix_opportunity_source_external", "source", "external_id"),
    )


class TrainingProgram(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Training-specific detail hanging off an Opportunity of type `training`."""

    __tablename__ = "training_programs"

    opportunity_id: Mapped[str] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    training_centre: Mapped[str | None] = mapped_column(String(240))
    duration_hours: Mapped[int | None] = mapped_column(Integer)
    duration_weeks: Mapped[int | None] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(32), default="in_person", nullable=False)
    fee_inr: Mapped[int | None] = mapped_column(Integer)
    is_subsidised: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Free text, e.g. "Fee waiver available for SC/ST candidates".
    funding_notes: Mapped[str | None] = mapped_column(Text)
    batch_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    batch_end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    certification_offered: Mapped[str | None] = mapped_column(String(240))
    languages_of_instruction: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    opportunity: Mapped[Opportunity] = relationship(back_populates="training_program")
