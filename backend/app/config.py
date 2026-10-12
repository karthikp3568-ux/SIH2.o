"""Application configuration.

Everything tunable lives here and is sourced from the environment so that no
secret is ever committed or shipped to the browser.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent

DEV_SECRET = "dev-only-insecure-change-me-0123456789abcdef"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "AI-Driven Multilingual Livelihood Navigator"
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = True
    api_prefix: str = "/api"

    # --- security ---
    secret_key: str = DEV_SECRET
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 14
    password_min_length: int = 8
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- database ---
    database_url: str = "sqlite:///./livelihood_navigator.db"
    sql_echo: bool = False

    # --- providers ---
    #: semantic   -> LLM when configured, else the multilingual embedding model,
    #:               with the lexicon only as a last resort (default)
    #: llm / rule_based -> force one layer, for debugging and tests
    profile_extractor: Literal["semantic", "rule_based", "llm"] = "semantic"
    #: Multilingual sentence encoder used for offline semantic understanding.
    #: LaBSE covers Kannada, Hindi, Tamil, Telugu, Marathi, Bengali and English.
    semantic_model: str = "sentence-transformers/LaBSE"
    embedding_provider: Literal["local_hashing", "sentence_transformers"] = "local_hashing"
    embedding_dim: int = 512
    llm_provider: Literal["none", "anthropic", "openai_compatible"] = "none"
    llm_model: str = "claude-opus-5-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    speech_provider: Literal["browser", "mock", "bhashini"] = "browser"
    bhashini_user_id: str = ""
    bhashini_api_key: str = ""
    bhashini_pipeline_id: str = ""
    bhashini_endpoint: str = ""

    messaging_provider: Literal["none", "whatsapp_cloud", "ivr_webhook"] = "none"
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_verify_token: str = ""
    ivr_webhook_secret: str = ""

    # --- privacy / retention ---
    store_raw_audio: bool = False
    audio_retention_hours: int = 24
    transcript_retention_days: int = 180
    audio_storage_dir: str = "./var/audio"
    max_audio_bytes: int = 5 * 1024 * 1024

    # --- conversation ---
    asr_confidence_threshold: float = 0.65
    #: Between the threshold and this value a transcript is used, but the facts
    #: it yields carry reduced confidence for the confirmation screen.
    asr_moderate_confidence: float = 0.8
    #: Misunderstood answers to one question before moving on rather than looping.
    max_clarifications_per_slot: int = 1

    # --- rate limiting ---
    rate_limit_enabled: bool = True
    #: Sign-in attempts per minute (brute-force protection).
    rate_limit_auth_per_minute: int = 10
    #: Account creations per minute. Separate from sign-in, so a few rejected
    #: sign-up attempts cannot lock a shared device out of signing in, or vice versa.
    rate_limit_register_per_minute: int = 20
    rate_limit_conversation_per_minute: int = 40
    rate_limit_default_per_minute: int = 120

    # --- demo ---
    demo_mode: bool = True
    seed_on_startup: bool = True
    demo_admin_email: str = "admin@navigator.example.com"
    demo_admin_password: str = "Admin@12345"
    demo_beneficiary_email: str = "ravi@navigator.example.com"
    demo_beneficiary_password: str = "Ravi@12345"

    ranking_weights_path: str = Field(default=str(BACKEND_ROOT / "config" / "ranking_weights.json"))

    @field_validator("secret_key")
    @classmethod
    def _reject_dev_secret_in_prod(cls, v: str, info):  # noqa: ANN001
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def audio_dir(self) -> Path:
        p = Path(self.audio_storage_dir)
        return p if p.is_absolute() else (BACKEND_ROOT / p).resolve()

    def assert_production_safe(self) -> None:
        """Fail loudly rather than run production on the development secret."""
        if self.environment == "production":
            problems = []
            if self.secret_key == DEV_SECRET or len(self.secret_key) < 32:
                problems.append("SECRET_KEY must be overridden with >=32 random characters")
            if self.debug:
                problems.append("DEBUG must be false")
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS must not contain a wildcard")
            if problems:
                raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Ranking weights
# ---------------------------------------------------------------------------

DEFAULT_RANKING_WEIGHTS: dict[str, float] = {
    "skill_fit": 0.26,
    "qualification_fit": 0.16,
    "aspiration_fit": 0.14,
    "gap_compatibility": 0.10,
    "location_fit": 0.14,
    "mobility_fit": 0.08,
    "availability": 0.06,
    "freshness": 0.04,
    "verification": 0.02,
}

# Maximum travel a beneficiary in each mobility band is assumed to accept.
# These are product defaults, not measured values - see docs/ASSUMPTIONS.md.
DEFAULT_MOBILITY_RADIUS_KM: dict[str, float] = {
    "low": 25.0,
    "medium": 60.0,
    "high": 200.0,
}

DEFAULT_RANKING_CONFIG: dict = {
    "weights": DEFAULT_RANKING_WEIGHTS,
    "mobility_radius_km": DEFAULT_MOBILITY_RADIUS_KM,
    # Retrieval blend between vector similarity and keyword (BM25) score.
    "retrieval": {"vector_weight": 0.6, "keyword_weight": 0.4, "candidate_pool": 60},
    # An opportunity not re-verified within this many days is flagged stale and
    # loses freshness points; beyond hard_stale_days it is excluded entirely.
    "freshness": {"stale_after_days": 90, "hard_stale_days": 365},
    "top_n": 3,
    # Minimum blended score for a candidate to be presented as a recommendation.
    "min_score": 0.28,
}


@lru_cache
def get_ranking_config() -> dict:
    """Load ranking configuration, falling back to documented defaults."""
    settings = get_settings()
    path = Path(settings.ranking_weights_path)
    config = json.loads(json.dumps(DEFAULT_RANKING_CONFIG))  # deep copy
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return config
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key].update(value)
            else:
                config[key] = value
    return config
