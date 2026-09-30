"""Pluggable providers for every external capability."""

from .base import (
    EmbeddingProvider,
    InboundMessage,
    LLMProvider,
    MessagingProvider,
    OpportunityProvider,
    ProviderNotConfigured,
    ProviderStatus,
    QualificationProvider,
    SpeechProvider,
    TranscriptionResult,
)
from .data_sources import (
    CsvOpportunityProvider,
    HttpOpportunityProvider,
    SeedOpportunityProvider,
    SeedQualificationProvider,
    all_data_source_statuses,
    load_seed_file,
)
from .embeddings import cosine_similarity, get_embedding_provider
from .llm import complete_json, get_llm_provider
from .messaging import all_messaging_statuses, get_channel_adapter, get_messaging_provider
from .speech import all_speech_statuses, get_speech_provider

__all__ = [
    "CsvOpportunityProvider",
    "EmbeddingProvider",
    "HttpOpportunityProvider",
    "InboundMessage",
    "LLMProvider",
    "MessagingProvider",
    "OpportunityProvider",
    "ProviderNotConfigured",
    "ProviderStatus",
    "QualificationProvider",
    "SeedOpportunityProvider",
    "SeedQualificationProvider",
    "SpeechProvider",
    "TranscriptionResult",
    "all_data_source_statuses",
    "all_messaging_statuses",
    "all_speech_statuses",
    "complete_json",
    "cosine_similarity",
    "get_channel_adapter",
    "get_embedding_provider",
    "get_llm_provider",
    "get_messaging_provider",
    "get_speech_provider",
    "load_seed_file",
]


def provider_health() -> dict[str, list[dict]]:
    """Snapshot of every provider's configured state, for /api/system/providers.

    This is what keeps the demo honest: the UI shows exactly which integrations
    are live and which are interface-only.
    """
    from dataclasses import asdict  # noqa: PLC0415

    return {
        "speech": [asdict(s) for s in all_speech_statuses()],
        "messaging": [asdict(s) for s in all_messaging_statuses()],
        "embedding": [asdict(get_embedding_provider().status())],
        "llm": [asdict(get_llm_provider().status())],
        "data": [asdict(s) for s in all_data_source_statuses()],
    }
