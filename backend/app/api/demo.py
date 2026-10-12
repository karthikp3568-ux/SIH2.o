"""Demo mode.

Gives a judge a one-click path through the whole journey without needing
credentials or any external service.

SECURITY: every route here is disabled unless DEMO_MODE=true, and refuses
outright when ENVIRONMENT=production. The reset endpoint issues a token for a
single fixed, non-privileged demo account - it can never mint an admin session.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import get_settings
from ..core.enums import Mobility, Role
from ..deps import DbSession
from ..models import (
    BeneficiaryProfile,
    Conversation,
    Feedback,
    Outcome,
    Recommendation,
    RecommendationRun,
    User,
)
from ..providers.speech import MockSpeechProvider
from ..seed.seed_data import DEMO_LOCATION
from ..security import create_access_token, create_refresh_token
from ..services import profile_service
from ..services.conversation_engine import start_conversation

router = APIRouter(prefix="/demo", tags=["demo"])
settings = get_settings()


def _guard() -> None:
    if not settings.demo_mode or settings.environment == "production":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo mode is not enabled on this deployment.",
        )


#: The scripted utterances. Kept here rather than in the frontend so the demo
#: and the tests exercise exactly the same input.
#: One answer per question, in the order the engine asks them: work and
#: skill -> how long -> schooling -> what next -> how far. Each later line is a
#: short answer that only makes sense against the question just asked.
RAVI_SCRIPT: list[dict] = [
    {
        "step": 1,
        "language": "en",
        "text": "I work in agriculture and repair pumps. I like mechanical work.",
        "note": "Occupation, a skill and an interest in one sentence.",
    },
    {"step": 2, "language": "en", "text": "For several years.", "note": "Answers how long - no number is invented."},
    {"step": 3, "language": "en", "text": "I completed 10th standard.", "note": "Education."},
    {"step": 4, "language": "en", "text": "I want to start my own business.", "note": "Goal: self-employment."},
    {"step": 5, "language": "en", "text": "No.", "note": "Answers the travel question: low mobility."},
]

RAVI_SCRIPT_HI: list[dict] = [
    {
        "step": 1,
        "language": "hi",
        "text": "मैं खेती करता हूँ और मोटर पंप ठीक कर लेता हूँ। मुझे मशीन का काम पसंद है।",
        "note": "Same content in Hindi, to show the pipeline is language agnostic.",
    },
    {"step": 2, "language": "hi", "text": "कई सालों से।", "note": "How long."},
    {"step": 3, "language": "hi", "text": "मैंने दसवीं पास की है।", "note": "Education."},
    {"step": 4, "language": "hi", "text": "मैं अपना खुद का काम शुरू करना चाहता हूँ।", "note": "Goal."},
    {"step": 5, "language": "hi", "text": "नहीं, मैं दूर नहीं जा सकता।", "note": "Travel."},
]

RAVI_SCRIPT_KN: list[dict] = [
    {
        "step": 1,
        "language": "kn",
        "text": "ನಾನು ಕೃಷಿ ಕೆಲಸ ಮಾಡುತ್ತೇನೆ ಮತ್ತು ಪಂಪ್ ರಿಪೇರಿ ಮಾಡುತ್ತೇನೆ. ನನಗೆ ಯಂತ್ರಗಳ ಕೆಲಸ ಇಷ್ಟ.",
        "note": "Same content in Kannada.",
    },
    {"step": 2, "language": "kn", "text": "ತುಂಬಾ ವರ್ಷಗಳಿಂದ.", "note": "How long."},
    {"step": 3, "language": "kn", "text": "ನಾನು ಹತ್ತನೇ ತರಗತಿ ಓದಿದ್ದೇನೆ.", "note": "Education."},
    {"step": 4, "language": "kn", "text": "ನನಗೆ ನನ್ನದೇ business ಶುರು ಮಾಡಬೇಕು.", "note": "Goal, code-switched."},
    {"step": 5, "language": "kn", "text": "ನಾನು ತುಂಬಾ ದೂರ ಹೋಗಲು ಆಗುವುದಿಲ್ಲ.", "note": "Travel."},
]


@router.get("/script")
def script() -> dict:
    """The demo conversation, so the UI can play it back or the judge can read it."""
    _guard()
    return {
        "beneficiary": "Ravi",
        "profile_summary": {
            "education": "10th standard",
            "occupation": "Agriculture / farm work",
            "skills": ["pump repair"],
            "interests": ["mechanical"],
            "mobility": "low",
            "goal": "self-employment",
        },
        "english": RAVI_SCRIPT,
        "hindi": RAVI_SCRIPT_HI,
        "kannada": RAVI_SCRIPT_KN,
        "mock_transcripts": MockSpeechProvider.SCRIPTS,
        "note": (
            "These are inputs, not outputs. The profile, skill gap and pathways shown "
            "in the demo are computed from this text by the same code paths a real "
            "user's speech goes through."
        ),
    }


@router.post("/ravi/reset")
def reset_ravi(db: DbSession) -> dict:
    """Reset the demo beneficiary to a clean starting state and sign in as them.

    Clears Ravi's extracted profile, conversations, recommendations and
    outcomes, then sets only his location (which speech cannot provide) so the
    distance and mobility factors have something to work with.
    """
    _guard()

    user = db.execute(
        select(User).where(User.email == settings.demo_beneficiary_email)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo data has not been seeded. Run `python -m app.cli seed`.",
        )
    if user.role != Role.BENEFICIARY:
        # Defensive: the demo account must never be privileged.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Demo account is misconfigured.",
        )

    profile = db.execute(
        select(BeneficiaryProfile).where(BeneficiaryProfile.user_id == user.id)
    ).scalar_one_or_none()
    if profile is None:
        profile = BeneficiaryProfile(
            user_id=user.id, display_name="Ravi", preferred_language="en"
        )
        db.add(profile)
        db.flush()

    for model in (Feedback, Outcome, Recommendation, RecommendationRun, Conversation):
        for row in db.execute(
            select(model).where(model.beneficiary_id == profile.id)
        ).scalars().all():
            db.delete(row)
    db.flush()

    for collection in (
        profile.educations,
        profile.occupations,
        profile.experiences,
        profile.interests,
        profile.goals,
        profile.constraints,
        profile.skills,
        profile.locations,
    ):
        for row in list(collection):
            db.delete(row)
    db.flush()

    profile.display_name = "Ravi"
    profile.age = 29
    profile.mobility = Mobility.MEDIUM
    profile.max_travel_km = None
    profile.is_confirmed = False
    profile.confirmed_at = None
    profile_service.upsert_location(db, profile, DEMO_LOCATION)
    db.commit()
    db.refresh(profile)

    conversation, greeting = start_conversation(
        db, profile, language=profile.preferred_language, channel="web_text"
    )

    return {
        "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "role": user.role},
        "beneficiary_id": profile.id,
        "conversation_id": conversation.id,
        "assistant_message": greeting,
        "tokens": {
            "access_token": create_access_token(user.id, user.role, user.token_version),
            "refresh_token": create_refresh_token(user.id, user.token_version),
            "token_type": "bearer",
            "expires_in_minutes": settings.access_token_ttl_minutes,
        },
        "location": DEMO_LOCATION,
        "script": RAVI_SCRIPT,
        "note": (
            "Ravi's location is pre-set because speech cannot supply coordinates. "
            "Everything else - education, skills, interests, mobility and goal - is "
            "extracted live from what he says."
        ),
    }


@router.get("/status")
def demo_status(db: DbSession) -> dict:
    """Whether the demo is ready, and what it will and will not do."""
    _guard()
    from ..models import Opportunity, Qualification, Skill  # noqa: PLC0415

    return {
        "demo_mode": settings.demo_mode,
        "seeded": {
            "skills": len(db.execute(select(Skill.id)).scalars().all()),
            "qualifications": len(db.execute(select(Qualification.id)).scalars().all()),
            "opportunities": len(db.execute(select(Opportunity.id)).scalars().all()),
        },
        "works_offline": True,
        "external_services_required": [],
        "honest_limitations": [
            "Qualification records are representative samples modelled on the NSQF/QP/NOS "
            "structure, not an authoritative extract.",
            "Opportunity records are curated demo listings, not live listings.",
            "Voice recognition runs in the browser (Chrome/Edge); other browsers use text input.",
            "With no LLM configured, understanding runs offline on a multilingual sentence "
            "encoder (LaBSE); explanations are produced from templates.",
        ],
    }
