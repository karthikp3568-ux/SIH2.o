"""Provider protocol definitions.

Every external capability the system could use lives behind one of these
interfaces. The default implementation of each is offline and deterministic, so
the prototype never depends on a network call - and a real provider can be
dropped in later without touching business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class ProviderNotConfigured(RuntimeError):
    """Raised when a provider is selected but its credentials are absent.

    Callers catch this and degrade gracefully rather than pretending the
    integration worked.
    """


@dataclass
class ProviderStatus:
    name: str
    kind: str
    configured: bool
    detail: str
    is_offline_default: bool = False


# ---------------------------------------------------------------------------
# Speech
# ---------------------------------------------------------------------------


@dataclass
class TranscriptionResult:
    text: str
    language: str
    language_confidence: float
    asr_confidence: float
    provider: str
    is_code_switched: bool = False
    alternatives: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class SpeechProvider(Protocol):
    name: str

    def status(self) -> ProviderStatus: ...

    def transcribe(
        self, audio: bytes, language_hint: str | None = None, mime_type: str = "audio/webm"
    ) -> TranscriptionResult: ...


# ---------------------------------------------------------------------------
# Messaging (WhatsApp / IVR)
# ---------------------------------------------------------------------------


@dataclass
class InboundMessage:
    """Normalised inbound message from any channel."""

    channel: str
    sender_ref: str
    text: str | None
    audio: bytes | None = None
    language_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MessagingProvider(Protocol):
    name: str
    channel: str

    def status(self) -> ProviderStatus: ...

    def parse_inbound(self, payload: dict[str, Any]) -> InboundMessage: ...

    def send_text(self, recipient_ref: str, text: str, language: str = "en") -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dim: int

    def status(self) -> ProviderStatus: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]: ...


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    available: bool

    def status(self) -> ProviderStatus: ...

    def complete(self, system: str, user: str, max_tokens: int = 800) -> str: ...


# ---------------------------------------------------------------------------
# Data ingestion
# ---------------------------------------------------------------------------


@runtime_checkable
class OpportunityProvider(Protocol):
    """Supplies opportunity records for ingestion."""

    name: str

    def status(self) -> ProviderStatus: ...

    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]: ...


@runtime_checkable
class QualificationProvider(Protocol):
    """Supplies recognised qualification / competency records."""

    name: str

    def status(self) -> ProviderStatus: ...

    def fetch(self, **kwargs: Any) -> list[dict[str, Any]]: ...
