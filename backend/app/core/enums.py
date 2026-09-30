"""Domain vocabularies.

Stored as plain strings in the database (portable across SQLite/PostgreSQL) but
validated through these enums at every boundary.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    BENEFICIARY = "beneficiary"
    ADMIN = "admin"
    PROVIDER = "provider"
    COUNSELLOR = "counsellor"


class Channel(StrEnum):
    WEB_VOICE = "web_voice"
    WEB_TEXT = "web_text"
    WHATSAPP = "whatsapp"
    IVR = "ivr"
    ADMIN_ENTRY = "admin_entry"


class SkillSource(StrEnum):
    SELF_REPORTED = "self_reported"
    INFERRED = "inferred"
    TRAINING = "training"
    ASSESSMENT = "assessment"
    CERTIFICATION = "certification"
    ADMIN_VERIFIED = "admin_verified"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    SELF_DECLARED = "self_declared"
    TRAINING_VERIFIED = "training_verified"
    ASSESSMENT_VERIFIED = "assessment_verified"
    CERTIFICATION_VERIFIED = "certification_verified"
    ADMIN_VERIFIED = "admin_verified"
    DISPUTED = "disputed"


#: Ordered weakest -> strongest. Used when scoring evidence strength.
VERIFICATION_STRENGTH: dict[str, float] = {
    VerificationStatus.DISPUTED: 0.0,
    VerificationStatus.UNVERIFIED: 0.35,
    VerificationStatus.SELF_DECLARED: 0.45,
    VerificationStatus.TRAINING_VERIFIED: 0.75,
    VerificationStatus.ASSESSMENT_VERIFIED: 0.9,
    VerificationStatus.CERTIFICATION_VERIFIED: 1.0,
    VerificationStatus.ADMIN_VERIFIED: 0.85,
}


class Proficiency(StrEnum):
    NONE = "none"
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


PROFICIENCY_SCORE: dict[str, float] = {
    Proficiency.NONE: 0.0,
    Proficiency.BASIC: 0.45,
    Proficiency.INTERMEDIATE: 0.75,
    Proficiency.ADVANCED: 1.0,
}


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


CONFIDENCE_SCORE: dict[str, float] = {
    Confidence.LOW: 0.4,
    Confidence.MEDIUM: 0.7,
    Confidence.HIGH: 1.0,
}


class Mobility(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OpportunityType(StrEnum):
    JOB = "job"
    APPRENTICESHIP = "apprenticeship"
    TRAINING = "training"
    ENTERPRISE = "enterprise"
    SELF_EMPLOYMENT = "self_employment"


class GoalType(StrEnum):
    JOB = "job"
    APPRENTICESHIP = "apprenticeship"
    TRAINING = "training"
    SELF_EMPLOYMENT = "self_employment"
    HIGHER_INCOME = "higher_income"
    UNDECIDED = "undecided"


#: Which opportunity types satisfy a stated goal, and how well (0..1).
GOAL_TO_OPPORTUNITY_AFFINITY: dict[str, dict[str, float]] = {
    GoalType.JOB: {
        OpportunityType.JOB: 1.0,
        OpportunityType.APPRENTICESHIP: 0.8,
        OpportunityType.TRAINING: 0.65,
        OpportunityType.ENTERPRISE: 0.3,
        OpportunityType.SELF_EMPLOYMENT: 0.3,
    },
    GoalType.APPRENTICESHIP: {
        OpportunityType.APPRENTICESHIP: 1.0,
        OpportunityType.TRAINING: 0.8,
        OpportunityType.JOB: 0.6,
        OpportunityType.ENTERPRISE: 0.3,
        OpportunityType.SELF_EMPLOYMENT: 0.3,
    },
    GoalType.TRAINING: {
        OpportunityType.TRAINING: 1.0,
        OpportunityType.APPRENTICESHIP: 0.85,
        OpportunityType.JOB: 0.5,
        OpportunityType.ENTERPRISE: 0.45,
        OpportunityType.SELF_EMPLOYMENT: 0.45,
    },
    GoalType.SELF_EMPLOYMENT: {
        OpportunityType.SELF_EMPLOYMENT: 1.0,
        OpportunityType.ENTERPRISE: 1.0,
        OpportunityType.TRAINING: 0.8,
        OpportunityType.APPRENTICESHIP: 0.55,
        OpportunityType.JOB: 0.35,
    },
    GoalType.HIGHER_INCOME: {
        OpportunityType.JOB: 0.85,
        OpportunityType.SELF_EMPLOYMENT: 0.85,
        OpportunityType.ENTERPRISE: 0.85,
        OpportunityType.APPRENTICESHIP: 0.7,
        OpportunityType.TRAINING: 0.7,
    },
    GoalType.UNDECIDED: {t: 0.7 for t in OpportunityType},
}


class RecordStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"
    EXPIRED = "expired"
    RETIRED = "retired"


class OutcomeStatus(StrEnum):
    RECOMMENDED = "recommended"
    SELECTED = "selected"
    ENROLLED = "enrolled"
    ATTENDING = "attending"
    COMPLETED = "completed"
    EMPLOYED = "employed"
    SELF_EMPLOYED = "self_employed"
    DROPPED_OUT = "dropped_out"
    REJECTED = "rejected"
    OPPORTUNITY_INACTIVE = "opportunity_inactive"
    CHANGED_PATHWAY = "changed_pathway"


#: Allowed lifecycle transitions. Enforced server side.
OUTCOME_TRANSITIONS: dict[str, set[str]] = {
    OutcomeStatus.RECOMMENDED: {
        OutcomeStatus.SELECTED,
        OutcomeStatus.REJECTED,
        OutcomeStatus.OPPORTUNITY_INACTIVE,
    },
    OutcomeStatus.SELECTED: {
        OutcomeStatus.ENROLLED,
        OutcomeStatus.REJECTED,
        OutcomeStatus.CHANGED_PATHWAY,
        OutcomeStatus.OPPORTUNITY_INACTIVE,
    },
    OutcomeStatus.ENROLLED: {
        OutcomeStatus.ATTENDING,
        OutcomeStatus.DROPPED_OUT,
        OutcomeStatus.CHANGED_PATHWAY,
        OutcomeStatus.OPPORTUNITY_INACTIVE,
    },
    OutcomeStatus.ATTENDING: {
        OutcomeStatus.COMPLETED,
        OutcomeStatus.DROPPED_OUT,
        OutcomeStatus.CHANGED_PATHWAY,
    },
    OutcomeStatus.COMPLETED: {
        OutcomeStatus.EMPLOYED,
        OutcomeStatus.SELF_EMPLOYED,
        OutcomeStatus.CHANGED_PATHWAY,
    },
    OutcomeStatus.EMPLOYED: {OutcomeStatus.CHANGED_PATHWAY, OutcomeStatus.SELF_EMPLOYED},
    OutcomeStatus.SELF_EMPLOYED: {OutcomeStatus.CHANGED_PATHWAY, OutcomeStatus.EMPLOYED},
    OutcomeStatus.DROPPED_OUT: {OutcomeStatus.CHANGED_PATHWAY, OutcomeStatus.ENROLLED},
    OutcomeStatus.REJECTED: {OutcomeStatus.CHANGED_PATHWAY},
    OutcomeStatus.OPPORTUNITY_INACTIVE: {OutcomeStatus.CHANGED_PATHWAY},
    OutcomeStatus.CHANGED_PATHWAY: set(),
}

#: Terminal-positive outcomes, used by analytics.
POSITIVE_OUTCOMES = {OutcomeStatus.EMPLOYED, OutcomeStatus.SELF_EMPLOYED, OutcomeStatus.COMPLETED}


class EducationLevel(StrEnum):
    NONE = "none"
    PRIMARY = "primary"
    CLASS_8 = "class_8"
    CLASS_10 = "class_10"
    CLASS_12 = "class_12"
    ITI = "iti"
    DIPLOMA = "diploma"
    GRADUATE = "graduate"
    POSTGRADUATE = "postgraduate"


#: Ordinal ranking used for eligibility checks ("at least class 10").
EDUCATION_RANK: dict[str, int] = {
    EducationLevel.NONE: 0,
    EducationLevel.PRIMARY: 1,
    EducationLevel.CLASS_8: 2,
    EducationLevel.CLASS_10: 3,
    EducationLevel.CLASS_12: 4,
    EducationLevel.ITI: 5,
    EducationLevel.DIPLOMA: 6,
    EducationLevel.GRADUATE: 7,
    EducationLevel.POSTGRADUATE: 8,
}

EDUCATION_LABEL: dict[str, str] = {
    EducationLevel.NONE: "No formal schooling",
    EducationLevel.PRIMARY: "Primary school",
    EducationLevel.CLASS_8: "8th standard",
    EducationLevel.CLASS_10: "10th standard",
    EducationLevel.CLASS_12: "12th standard",
    EducationLevel.ITI: "ITI",
    EducationLevel.DIPLOMA: "Diploma",
    EducationLevel.GRADUATE: "Graduate",
    EducationLevel.POSTGRADUATE: "Post graduate",
}


class Language(StrEnum):
    EN = "en"
    HI = "hi"
    TA = "ta"
    TE = "te"
    MR = "mr"
    BN = "bn"
    KN = "kn"
    GU = "gu"
    ML = "ml"
    PA = "pa"
    OR = "or"


LANGUAGE_LABEL: dict[str, str] = {
    Language.EN: "English",
    Language.HI: "हिन्दी",
    Language.TA: "தமிழ்",
    Language.TE: "తెలుగు",
    Language.MR: "मराठी",
    Language.BN: "বাংলা",
    Language.KN: "ಕನ್ನಡ",
    Language.GU: "ગુજરાતી",
    Language.ML: "മലയാളം",
    Language.PA: "ਪੰਜਾਬੀ",
    Language.OR: "ଓଡ଼ିଆ",
}

#: BCP-47 tags handed to the browser Web Speech API / future ASR providers.
LANGUAGE_BCP47: dict[str, str] = {
    Language.EN: "en-IN",
    Language.HI: "hi-IN",
    Language.TA: "ta-IN",
    Language.TE: "te-IN",
    Language.MR: "mr-IN",
    Language.BN: "bn-IN",
    Language.KN: "kn-IN",
    Language.GU: "gu-IN",
    Language.ML: "ml-IN",
    Language.PA: "pa-IN",
    Language.OR: "or-IN",
}


class AuditAction(StrEnum):
    LOGIN_SUCCESS = "auth.login.success"
    LOGIN_FAILURE = "auth.login.failure"
    REGISTER = "auth.register"
    PROFILE_CONFIRMED = "profile.confirmed"
    PROFILE_UPDATED = "profile.updated"
    PROFILE_CORRECTED_BY_ADMIN = "profile.corrected_by_admin"
    RECOMMENDATION_GENERATED = "recommendation.generated"
    RECOMMENDATION_OVERRIDE = "recommendation.override"
    PATHWAY_SELECTED = "pathway.selected"
    OPPORTUNITY_CREATED = "opportunity.created"
    OPPORTUNITY_UPDATED = "opportunity.updated"
    OPPORTUNITY_DELETED = "opportunity.deleted"
    OPPORTUNITY_VERIFIED = "opportunity.verified"
    OUTCOME_CREATED = "outcome.created"
    OUTCOME_UPDATED = "outcome.updated"
    FEEDBACK_SUBMITTED = "feedback.submitted"
    USER_DEACTIVATED = "user.deactivated"
    CONSENT_GRANTED = "consent.granted"
    CONSENT_WITHDRAWN = "consent.withdrawn"
    DATA_DELETED = "data.deleted"
