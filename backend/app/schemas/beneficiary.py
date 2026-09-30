"""Beneficiary profile, skill graph and skill-gap schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.enums import EducationLevel, GoalType, Mobility, Proficiency, VerificationStatus
from .common import LocationIn, LocationOut


class SkillEvidenceOut(BaseModel):
    type: str
    description: str


class BeneficiarySkillOut(BaseModel):
    id: str
    skill_id: str | None = None
    code: str | None = None
    name: str
    raw_label: str
    proficiency: Proficiency
    source: str
    confidence: str
    #: Self-reported and certified are deliberately different values here.
    verification_status: VerificationStatus
    years_experience: float | None = None
    evidence: list[SkillEvidenceOut] = Field(default_factory=list)


class EducationOut(BaseModel):
    level: EducationLevel
    label: str
    source: str
    confidence: str
    verification_status: str


class OccupationOut(BaseModel):
    id: str
    title: str
    sector: str | None = None
    is_current: bool
    source: str
    confidence: str


class ExperienceOut(BaseModel):
    id: str
    title: str
    years: float | None = None
    nature: str
    verification_status: str


class InterestOut(BaseModel):
    id: str
    label: str
    tag: str | None = None
    strength: float


class GoalOut(BaseModel):
    id: str
    goal_type: GoalType
    description: str | None = None
    target_monthly_income_inr: int | None = None
    priority: int


class ConstraintOut(BaseModel):
    id: str
    kind: str
    label: str
    severity: str


class BeneficiaryProfileOut(BaseModel):
    id: str
    user_id: str
    display_name: str
    preferred_language: str
    age: int | None = None
    gender: str | None = None
    mobility: Mobility
    max_travel_km: float | None = None
    is_confirmed: bool
    confirmed_at: str | None = None
    education: EducationOut | None = None
    occupations: list[OccupationOut] = Field(default_factory=list)
    experiences: list[ExperienceOut] = Field(default_factory=list)
    skills: list[BeneficiarySkillOut] = Field(default_factory=list)
    interests: list[InterestOut] = Field(default_factory=list)
    goals: list[GoalOut] = Field(default_factory=list)
    constraints: list[ConstraintOut] = Field(default_factory=list)
    location: LocationOut | None = None


class ProfilePatch(BaseModel):
    """Beneficiary-editable fields. Verification status is NOT among them."""

    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    preferred_language: str | None = Field(default=None, max_length=8)
    age: int | None = Field(default=None, ge=14, le=90)
    gender: str | None = Field(default=None, max_length=24)
    mobility: Mobility | None = None
    max_travel_km: float | None = Field(default=None, ge=0, le=1000)
    education_level: EducationLevel | None = None
    occupations: list[str] | None = None
    interests: list[str] | None = None
    goals: list[GoalType] | None = None
    location: LocationIn | None = None


class SkillIn(BaseModel):
    """Adding a skill by hand. It is recorded as self-declared, never verified."""

    label: str = Field(min_length=1, max_length=200)
    proficiency: Proficiency = Proficiency.BASIC
    years_experience: float | None = Field(default=None, ge=0, le=60)


class SkillNormalizeRequest(BaseModel):
    labels: list[str] = Field(min_length=1, max_length=50)


class SkillNormalizeItem(BaseModel):
    input: str
    code: str | None = None
    name: str | None = None
    matched_alias: str | None = None
    alias_language: str | None = None
    is_category: bool = False
    resolved: bool


class SkillNormalizeResponse(BaseModel):
    items: list[SkillNormalizeItem]
    unresolved: list[str] = Field(default_factory=list)


class ProfileExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: str | None = Field(default=None, max_length=8)


class ExtractedFactOut(BaseModel):
    value: Any = None
    confidence: float
    evidence: str
    extractor: str = "rule_based"


class ProfileExtractResponse(BaseModel):
    language: str
    language_confidence: float
    is_code_switched: bool
    extraction: dict[str, Any]
    filled_slots: list[str]
    extractor: str


class SkillGraphOut(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class SkillGapRequest(BaseModel):
    qualification_id: str | None = None
    qualification_code: str | None = None
    #: When neither id nor code is given, the most relevant active
    #: qualifications for this beneficiary are analysed.
    limit: int = Field(default=3, ge=1, le=10)


class SkillGapResponse(BaseModel):
    beneficiary_id: str
    skill_graph: SkillGraphOut
    reports: list[dict[str, Any]]
