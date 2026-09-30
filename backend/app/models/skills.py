"""Canonical skill taxonomy and the beneficiary's claimed / verified skills.

The taxonomy is a directed graph:
  * `parent_id`  - "is a narrower kind of" (tree backbone, used for roll-up)
  * SkillRelation - typed cross edges ("related_to", "prerequisite_of")

A beneficiary's skill graph is this taxonomy restricted to the nodes they hold,
plus the ancestors those nodes roll up into.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.enums import Confidence, Proficiency, SkillSource, VerificationStatus
from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Skill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "skills"

    code: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sector: Mapped[str | None] = mapped_column(String(80), index=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), index=True
    )
    #: Marks broad category nodes (e.g. "agriculture") vs leaf abilities.
    is_category: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    parent: Mapped["Skill | None"] = relationship(remote_side="Skill.id", back_populates="children")
    children: Mapped[list["Skill"]] = relationship(back_populates="parent")
    aliases: Mapped[list["SkillAlias"]] = relationship(
        back_populates="skill", cascade="all, delete-orphan"
    )


class SkillAlias(UUIDPrimaryKeyMixin, Base):
    """Surface forms - including regional-language and transliterated spellings."""

    __tablename__ = "skill_aliases"

    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)

    skill: Mapped[Skill] = relationship(back_populates="aliases")

    __table_args__ = (Index("ix_skill_alias_lookup", "alias", "language"),)


class SkillRelation(UUIDPrimaryKeyMixin, Base):
    """Typed, weighted cross edge between two skills."""

    __tablename__ = "skill_relations"

    from_skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    to_skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: related_to | prerequisite_of | transfers_to
    relation: Mapped[str] = mapped_column(String(32), default="related_to", nullable=False)
    #: How much competence in `from` transfers to `to` (0..1).
    weight: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    __table_args__ = (
        Index("ix_skill_relation_pair", "from_skill_id", "to_skill_id", "relation", unique=True),
    )


class BeneficiarySkill(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A skill a beneficiary holds.

    `source` / `confidence` / `proficiency` / `verification_status` are all
    required, because "I repair pumps" and "certified pump technician" must
    never collapse into the same fact.
    """

    __tablename__ = "beneficiary_skills"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), index=True
    )
    #: Exactly what the beneficiary said, before normalisation.
    raw_label: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_label: Mapped[str | None] = mapped_column(String(200))
    proficiency: Mapped[str] = mapped_column(String(16), default=Proficiency.BASIC, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default=SkillSource.SELF_REPORTED, nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), default=Confidence.MEDIUM, nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.UNVERIFIED, nullable=False
    )
    years_experience: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    beneficiary: Mapped["BeneficiaryProfile"] = relationship(back_populates="skills")  # noqa: F821
    skill: Mapped[Skill | None] = relationship()
    evidence: Mapped[list["SkillEvidence"]] = relationship(
        back_populates="beneficiary_skill", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_beneficiary_skill_unique", "beneficiary_id", "skill_id", "raw_label"),
    )


class SkillEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Why we believe a skill claim - conversation turn, certificate, assessment."""

    __tablename__ = "skill_evidence"

    beneficiary_skill_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: conversation | certificate | assessment | training_completion | admin_note
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    #: Conversation message id, certificate number, assessment id, etc.
    reference: Mapped[str | None] = mapped_column(String(200))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    beneficiary_skill: Mapped[BeneficiarySkill] = relationship(back_populates="evidence")
