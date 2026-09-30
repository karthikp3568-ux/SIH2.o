"""Opportunity, training and qualification schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..core.enums import (
    EducationLevel,
    Mobility,
    OpportunityType,
    RecordStatus,
    VerificationStatus,
)


class TrainingProgramIn(BaseModel):
    training_centre: str | None = Field(default=None, max_length=240)
    duration_hours: int | None = Field(default=None, ge=0, le=10000)
    duration_weeks: int | None = Field(default=None, ge=0, le=520)
    mode: str = Field(default="in_person", pattern="^(in_person|online|blended)$")
    fee_inr: int | None = Field(default=None, ge=0)
    is_subsidised: bool = False
    funding_notes: str | None = Field(default=None, max_length=2000)
    batch_start_date: datetime | None = None
    batch_end_date: datetime | None = None
    certification_offered: str | None = Field(default=None, max_length=240)
    languages_of_instruction: list[str] = Field(default_factory=list)


class TrainingProgramOut(TrainingProgramIn):
    model_config = ConfigDict(from_attributes=True)

    id: str


class OpportunityBase(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    provider: str = Field(min_length=2, max_length=240)
    opportunity_type: OpportunityType
    description: str = Field(min_length=10, max_length=8000)
    sector: str | None = Field(default=None, max_length=80)
    qualification_id: str | None = None
    skills_required: list[str] = Field(default_factory=list, max_length=40)
    competencies_required: list[str] = Field(default_factory=list, max_length=40)
    education_required: EducationLevel | None = None
    min_age: int | None = Field(default=None, ge=14, le=90)
    max_age: int | None = Field(default=None, ge=14, le=90)
    eligibility_notes: str | None = Field(default=None, max_length=2000)
    location_label: str | None = Field(default=None, max_length=200)
    village: str | None = Field(default=None, max_length=120)
    block: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, pattern=r"^[1-9]\d{5}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    mobility_required: Mobility = Mobility.LOW
    stipend_or_income_inr: int | None = Field(default=None, ge=0)
    seats_total: int | None = Field(default=None, ge=0)
    seats_available: int | None = Field(default=None, ge=0)
    #: Where the record came from. Required - an opportunity with no provenance
    #: cannot be verified and must not be recommended.
    source: str = Field(min_length=3, max_length=200)
    source_url: str | None = Field(default=None, max_length=500)
    source_trust: float = Field(default=0.6, ge=0, le=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    external_id: str | None = Field(default=None, max_length=160)


class OpportunityCreate(OpportunityBase):
    status: RecordStatus = RecordStatus.DRAFT
    training_program: TrainingProgramIn | None = None


class OpportunityUpdate(BaseModel):
    """Every field optional; only what is sent is changed."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=240)
    provider: str | None = Field(default=None, min_length=2, max_length=240)
    opportunity_type: OpportunityType | None = None
    description: str | None = Field(default=None, min_length=10, max_length=8000)
    sector: str | None = Field(default=None, max_length=80)
    qualification_id: str | None = None
    skills_required: list[str] | None = None
    competencies_required: list[str] | None = None
    education_required: EducationLevel | None = None
    min_age: int | None = None
    max_age: int | None = None
    eligibility_notes: str | None = None
    location_label: str | None = None
    village: str | None = None
    block: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = Field(default=None, pattern=r"^[1-9]\d{5}$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    mobility_required: Mobility | None = None
    stipend_or_income_inr: int | None = None
    seats_total: int | None = None
    seats_available: int | None = None
    source: str | None = None
    source_url: str | None = None
    source_trust: float | None = Field(default=None, ge=0, le=1)
    status: RecordStatus | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    training_program: TrainingProgramIn | None = None


class QualificationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str | None = None
    title: str
    occupation_role: str
    sector: str
    nsqf_level: int | None = None
    status: RecordStatus
    minimum_education: str | None = None
    source: str
    last_verified_at: datetime | None = None
    superseded_by_code: str | None = None


class CompetencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    nos_code: str | None = None
    description: str | None = None
    nsqf_level: int | None = None
    status: str


class QualificationDetail(QualificationSummary):
    description: str | None = None
    sub_sector: str | None = None
    typical_duration_hours: int | None = None
    version: str | None = None
    source_url: str | None = None
    competencies: list[dict] = Field(default_factory=list)


class OpportunityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    provider: str
    opportunity_type: OpportunityType
    description: str
    sector: str | None = None
    qualification_id: str | None = None
    qualification: QualificationSummary | None = None
    skills_required: list[str] = Field(default_factory=list)
    skill_codes: list[str] = Field(default_factory=list)
    competencies_required: list[str] = Field(default_factory=list)
    education_required: str | None = None
    min_age: int | None = None
    max_age: int | None = None
    eligibility_notes: str | None = None
    location_label: str | None = None
    village: str | None = None
    block: str | None = None
    district: str | None = None
    state: str | None = None
    pincode: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    mobility_required: Mobility
    stipend_or_income_inr: int | None = None
    seats_total: int | None = None
    seats_available: int | None = None
    source: str
    source_url: str | None = None
    ingestion_channel: str
    source_trust: float
    verification_status: VerificationStatus
    status: RecordStatus
    last_verified_at: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    external_id: str | None = None
    training_program: TrainingProgramOut | None = None
    created_at: datetime
    updated_at: datetime


class OpportunitySearchResult(BaseModel):
    items: list[OpportunityOut]
    total: int
    limit: int
    offset: int
    #: Distance from the caller's location, when one is known.
    distances_km: dict[str, float] = Field(default_factory=dict)


class VerifyRequest(BaseModel):
    verification_status: VerificationStatus = VerificationStatus.ADMIN_VERIFIED
    source_url: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=1000)
    #: Extend validity while verifying, in days from now.
    extend_valid_days: int | None = Field(default=None, ge=0, le=730)


class ImportRequest(BaseModel):
    """CSV import. The file is uploaded separately as multipart form data."""

    dry_run: bool = True
    default_source: str = Field(default="csv_import", max_length=200)
    mark_status: RecordStatus = RecordStatus.DRAFT


class ImportRowError(BaseModel):
    row: int
    external_id: str | None = None
    errors: list[str]


class ImportReport(BaseModel):
    dry_run: bool
    rows_read: int
    created: int
    updated: int
    skipped: int
    errors: list[ImportRowError] = Field(default_factory=list)
