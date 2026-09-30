"""The beneficiary domain model.

Deliberately NOT one flat JSON blob: education, occupation, goals, constraints
and location are first-class rows so they can be verified, corrected, audited
and queried independently.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import Confidence, Mobility, VerificationStatus
from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BeneficiaryProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "beneficiary_profiles"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(24))

    mobility: Mapped[str] = mapped_column(String(16), default=Mobility.MEDIUM, nullable=False)
    #: Optional explicit override of the mobility band's default radius.
    max_travel_km: Mapped[float | None] = mapped_column(Float)

    #: True only once the beneficiary has seen and confirmed the extracted profile.
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Free-text notes captured from the conversation that did not map to a slot.
    notes: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="beneficiary")  # noqa: F821
    educations: Mapped[list["Education"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    occupations: Mapped[list["Occupation"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    experiences: Mapped[list["Experience"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    interests: Mapped[list["Interest"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    goals: Mapped[list["Goal"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    constraints: Mapped[list["Constraint"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    locations: Mapped[list["Location"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    skills: Mapped[list["BeneficiarySkill"]] = relationship(  # noqa: F821
        back_populates="beneficiary", cascade="all, delete-orphan"
    )

    @property
    def primary_location(self) -> "Location | None":
        if not self.locations:
            return None
        return sorted(self.locations, key=lambda loc: (not loc.is_primary, -loc.captured_ts))[0]


class Education(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "educations"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    level: Mapped[str] = mapped_column(String(32), nullable=False)
    institution: Mapped[str | None] = mapped_column(String(200))
    field_of_study: Mapped[str | None] = mapped_column(String(160))
    year_completed: Mapped[int | None] = mapped_column(Integer)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="self_reported", nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), default=Confidence.MEDIUM, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.SELF_DECLARED, nullable=False
    )

    beneficiary: Mapped[BeneficiaryProfile] = relationship(back_populates="educations")


class Occupation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "occupations"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(80), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    monthly_income_inr: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), default="self_reported", nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), default=Confidence.MEDIUM, nullable=False)

    beneficiary: Mapped[BeneficiaryProfile] = relationship(back_populates="occupations")


class Experience(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "experiences"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    years: Mapped[float | None] = mapped_column(Float)
    #: practical | formal_employment | apprenticeship | training | family_business
    nature: Mapped[str] = mapped_column(String(32), default="practical", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="self_reported", nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), default=Confidence.MEDIUM, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.SELF_DECLARED, nullable=False
    )

    beneficiary: Mapped[BeneficiaryProfile] = relationship(back_populates="experiences")


class Interest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "interests"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Canonical tag used by the ranking engine (e.g. "mechanical").
    tag: Mapped[str | None] = mapped_column(String(64), index=True)
    strength: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="self_reported", nullable=False)

    beneficiary: Mapped[BeneficiaryProfile] = relationship(back_populates="interests")


class Goal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "goals"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    goal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    target_monthly_income_inr: Mapped[int | None] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="self_reported", nullable=False)

    beneficiary: Mapped[BeneficiaryProfile] = relationship(back_populates="goals")


class Constraint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Anything that narrows the set of acceptable opportunities."""

    __tablename__ = "constraints"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: travel | time | language | financial | physical | family | digital_access
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="medium", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="self_reported", nullable=False)

    beneficiary: Mapped[BeneficiaryProfile] = relationship(back_populates="constraints")


class Location(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A captured location with provenance.

    On PostgreSQL this table is the natural home for a PostGIS `geography`
    column; on SQLite we keep lat/lon floats and do haversine in Python.
    See app/core/geo.py.
    """

    __tablename__ = "locations"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(160))
    village: Mapped[str | None] = mapped_column(String(120))
    block: Mapped[str | None] = mapped_column(String(120))
    district: Mapped[str | None] = mapped_column(String(120), index=True)
    state: Mapped[str | None] = mapped_column(String(120), index=True)
    pincode: Mapped[str | None] = mapped_column(String(10), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    #: gps | manual | pincode_lookup | district_centroid | admin_entry
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    beneficiary: Mapped[BeneficiaryProfile] = relationship(back_populates="locations")

    __table_args__ = (Index("ix_location_lat_lon", "latitude", "longitude"),)

    @property
    def captured_ts(self) -> float:
        return self.captured_at.timestamp() if self.captured_at else 0.0
