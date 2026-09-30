"""System status, capability disclosure and configuration endpoints.

`/system/providers` is deliberately public-facing inside the app: it is how the
UI shows a judge exactly which integrations are live and which are
interface-only, rather than leaving them to assume.
"""

from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..config import get_ranking_config, get_settings
from ..core.enums import LANGUAGE_BCP47, LANGUAGE_LABEL, Language
from ..core.slots import slot_catalogue
from ..deps import DbSession
from ..models import REJECTION_REASONS
from ..providers import provider_health
from ..schemas.common import SystemStatus
from ..services.ranking import explain_weights
from ..services.retrieval import EXCLUSION_REASONS

router = APIRouter(prefix="/system", tags=["system"])
settings = get_settings()


@router.get("/health")
def health(db: DbSession) -> dict:
    """Liveness plus a real database round-trip."""
    from sqlalchemy import text  # noqa: PLC0415

    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": __version__}


@router.get("/status", response_model=SystemStatus)
def status() -> SystemStatus:
    providers = provider_health()
    return SystemStatus(
        app_name=settings.app_name,
        version=__version__,
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        database="postgresql" if not settings.is_sqlite else "sqlite",
        providers=providers,
        capabilities={
            "browser_voice_input": True,
            "text_input": True,
            "server_side_asr": settings.speech_provider in {"bhashini", "mock"},
            "llm_assisted_extraction": settings.profile_extractor == "llm",
            "llm_explanation_polishing": settings.llm_provider != "none",
            "neural_embeddings": settings.embedding_provider == "sentence_transformers",
            "whatsapp_inbound_adapter": True,
            "whatsapp_outbound_sending": bool(settings.whatsapp_access_token),
            "ivr_inbound_adapter": True,
            "geospatial_ranking": True,
            "postgis": False,
            "audio_retention": settings.store_raw_audio,
        },
    )


@router.get("/languages")
def languages() -> list[dict]:
    """Languages the interface offers, with the tag for browser recognition."""
    return [
        {
            "code": str(code),
            "label": LANGUAGE_LABEL[code],
            "speech_tag": LANGUAGE_BCP47[code],
        }
        for code in Language
    ]


@router.get("/slots")
def slots(language: str = "en") -> list[dict]:
    """Conversation slot configuration. The client renders whatever this returns."""
    return slot_catalogue(language)


@router.get("/ranking-config")
def ranking_config() -> dict:
    """Full transparency on how recommendations are ordered."""
    config = get_ranking_config()
    return {
        "weights": explain_weights(config),
        "mobility_radius_km": config["mobility_radius_km"],
        "retrieval": config["retrieval"],
        "freshness": config["freshness"],
        "top_n": config["top_n"],
        "min_score": config["min_score"],
        "note": (
            "These weights are product defaults chosen for legibility, not empirically "
            "validated values. They are intended to be re-tuned against the outcome data "
            "collected in Phase 4."
        ),
    }


@router.get("/reason-codes")
def reason_codes() -> dict:
    """Stable codes the frontend maps to translated text."""
    return {
        "exclusions": EXCLUSION_REASONS,
        "rejection_reasons": REJECTION_REASONS,
    }
