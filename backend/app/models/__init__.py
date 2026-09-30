"""ORM models. Importing this package registers every table on `Base.metadata`."""

from .audit import AuditLog
from .base import Base, as_aware, new_id, utcnow
from .beneficiary import (
    BeneficiaryProfile,
    Constraint,
    Education,
    Experience,
    Goal,
    Interest,
    Location,
    Occupation,
)
from .conversation import Conversation, ConversationMessage
from .knowledge import KnowledgeChunk, KnowledgeDocument
from .opportunity import Opportunity, TrainingProgram
from .outcome import REJECTION_REASONS, Feedback, Outcome
from .qualification import (
    Competency,
    CompetencySkill,
    Qualification,
    QualificationCompetency,
)
from .recommendation import Recommendation, RecommendationReason, RecommendationRun
from .skills import BeneficiarySkill, Skill, SkillAlias, SkillEvidence, SkillRelation
from .user import Consent, User

__all__ = [
    "REJECTION_REASONS",
    "AuditLog",
    "Base",
    "BeneficiaryProfile",
    "BeneficiarySkill",
    "Competency",
    "CompetencySkill",
    "Consent",
    "Constraint",
    "Conversation",
    "ConversationMessage",
    "Education",
    "Experience",
    "Feedback",
    "Goal",
    "Interest",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "Location",
    "Occupation",
    "Opportunity",
    "Outcome",
    "Qualification",
    "QualificationCompetency",
    "Recommendation",
    "RecommendationReason",
    "RecommendationRun",
    "Skill",
    "SkillAlias",
    "SkillEvidence",
    "SkillRelation",
    "TrainingProgram",
    "User",
    "as_aware",
    "new_id",
    "utcnow",
]
