"""Recognised qualification model (NSQF / QP / NOS shaped).

This is deliberately *not* a course list. A Qualification is a recognised
standard with a level, a status, a source and a dated verification, composed of
Competencies that map onto the skill taxonomy. Retired standards are kept for
audit but excluded from recommendation.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import RecordStatus
from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Competency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single assessable outcome, typically sourced from a NOS."""

    __tablename__ = "competencies"

    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: National Occupational Standard reference, when the competency came from one.
    nos_code: Mapped[str | None] = mapped_column(String(80), index=True)
    sector: Mapped[str | None] = mapped_column(String(80), index=True)
    nsqf_level: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default=RecordStatus.ACTIVE, nullable=False)

    skill_links: Mapped[list["CompetencySkill"]] = relationship(
        back_populates="competency", cascade="all, delete-orphan"
    )


class CompetencySkill(UUIDPrimaryKeyMixin, Base):
    """Maps a competency onto taxonomy skills that evidence it.

    `coverage` is how much of the competency a person demonstrating this skill
    at full proficiency can be said to already cover (0..1).
    """

    __tablename__ = "competency_skills"

    competency_id: Mapped[str] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    coverage: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    competency: Mapped[Competency] = relationship(back_populates="skill_links")
    skill: Mapped["Skill"] = relationship()  # noqa: F821

    __table_args__ = (
        Index("ix_competency_skill_pair", "competency_id", "skill_id", unique=True),
    )


class Qualification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "qualifications"

    #: Qualification Pack code where one exists, e.g. "AGR/Q1101".
    code: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    occupation_role: Mapped[str] = mapped_column(String(200), nullable=False)
    sector: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    sub_sector: Mapped[str | None] = mapped_column(String(120))
    nsqf_level: Mapped[int | None] = mapped_column(Integer, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    minimum_education: Mapped[str | None] = mapped_column(String(32))
    typical_duration_hours: Mapped[int | None] = mapped_column(Integer)

    #: active | retired | draft. Retired qualifications are never recommended.
    status: Mapped[str] = mapped_column(
        String(16), default=RecordStatus.ACTIVE, index=True, nullable=False
    )
    #: Issuing / awarding body, e.g. a Sector Skill Council.
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[str | None] = mapped_column(String(32))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Set when status == retired, so the UI can explain the exclusion.
    superseded_by_code: Mapped[str | None] = mapped_column(String(80))

    competency_links: Mapped[list["QualificationCompetency"]] = relationship(
        back_populates="qualification", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_qualification_sector_status", "sector", "status"),)

    @property
    def competencies(self) -> list[Competency]:
        return [link.competency for link in self.competency_links if link.competency]


class QualificationCompetency(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "qualification_competencies"

    qualification_id: Mapped[str] = mapped_column(
        ForeignKey("qualifications.id", ondelete="CASCADE"), index=True, nullable=False
    )
    competency_id: Mapped[str] = mapped_column(
        ForeignKey("competencies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Core competencies must be covered; electives are optional.
    is_core: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: Relative importance within the qualification (0..1).
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    qualification: Mapped[Qualification] = relationship(back_populates="competency_links")
    competency: Mapped[Competency] = relationship()

    __table_args__ = (
        Index("ix_qual_comp_pair", "qualification_id", "competency_id", unique=True),
    )
