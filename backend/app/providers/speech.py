"""Speech / ASR providers.

Honest summary of what is and is not implemented:

* `browser`  - DEFAULT. Transcription happens in the browser using the Web
  Speech API, which ships real multilingual recognition in Chrome/Edge. The
  backend receives text plus the confidence and language the browser reported.
  This is genuinely working multilingual ASR with no server dependency.
* `mock`     - fixed transcripts for tests and the offline demo. Clearly labelled.
* `bhashini` - a real HTTP client against the BHASHINI inference API. It is NOT
  active unless BHASHINI_USER_ID / BHASHINI_API_KEY / BHASHINI_PIPELINE_ID are
  configured; without them it raises ProviderNotConfigured and the caller falls
  back to text input. It has not been tested against live credentials.
"""

from __future__ import annotations

import base64
from functools import lru_cache

import httpx

from ..config import get_settings
from ..core.enums import Language
from .base import ProviderNotConfigured, ProviderStatus, SpeechProvider, TranscriptionResult


class BrowserSpeechProvider:
    """Server-side counterpart of client-side Web Speech recognition.

    The browser does the recognition; this class exists so the rest of the
    system has a uniform provider to talk to, and so server-side audio upload
    returns an explicit, non-fabricated error.
    """

    name = "browser_web_speech"

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="speech",
            configured=True,
            detail=(
                "Recognition runs in the browser (Web Speech API). Supported in "
                "Chrome and Edge; other browsers fall back to text input."
            ),
            is_offline_default=True,
        )

    def transcribe(
        self, audio: bytes, language_hint: str | None = None, mime_type: str = "audio/webm"
    ) -> TranscriptionResult:
        raise ProviderNotConfigured(
            "The browser provider transcribes on the client. Send the transcript "
            "to /conversation/message, or configure a server-side ASR provider."
        )


class MockSpeechProvider:
    """Deterministic transcripts for tests and the offline judge demo."""

    name = "mock"

    #: Keyed by language; the demo script for Ravi.
    SCRIPTS: dict[str, str] = {
        Language.EN: (
            "I work in agriculture and I repair pumps sometimes. I want to earn "
            "more. I like mechanical work but I cannot travel very far."
        ),
        Language.HI: (
            "मैं खेती का काम करता हूँ और कभी कभी पंप ठीक करता हूँ। मुझे ज्यादा कमाना है। "
            "मुझे मशीन का काम पसंद है लेकिन मैं दूर नहीं जा सकता।"
        ),
        Language.TA: (
            "நான் விவசாயம் செய்கிறேன், சில நேரம் பம்ப் ரிப்பேர் செய்கிறேன். "
            "எனக்கு அதிக வருமானம் வேண்டும். மெக்கானிக் வேலை பிடிக்கும் ஆனால் தூரம் போக முடியாது."
        ),
    }

    def __init__(self, confidence: float = 0.88) -> None:
        self.confidence = confidence

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="speech",
            configured=True,
            detail="Fixed demo transcripts. Used by tests and offline demo mode only.",
            is_offline_default=True,
        )

    def transcribe(
        self, audio: bytes, language_hint: str | None = None, mime_type: str = "audio/webm"
    ) -> TranscriptionResult:
        language = language_hint if language_hint in self.SCRIPTS else Language.EN
        return TranscriptionResult(
            text=self.SCRIPTS[language],
            language=language,
            language_confidence=0.95,
            asr_confidence=self.confidence,
            provider=self.name,
            raw={"mock": True, "audio_bytes": len(audio)},
        )


class BhashiniSpeechProvider:
    """BHASHINI ASR client. Inert until credentials are configured."""

    name = "bhashini"

    def __init__(self) -> None:
        settings = get_settings()
        self.user_id = settings.bhashini_user_id
        self.api_key = settings.bhashini_api_key
        self.pipeline_id = settings.bhashini_pipeline_id
        self.endpoint = settings.bhashini_endpoint

    @property
    def configured(self) -> bool:
        return bool(self.user_id and self.api_key and self.pipeline_id and self.endpoint)

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="speech",
            configured=self.configured,
            detail=(
                "Configured and enabled."
                if self.configured
                else "Not configured. Set BHASHINI_* environment variables to enable. "
                "Until then the system uses browser-side recognition."
            ),
        )

    def transcribe(
        self, audio: bytes, language_hint: str | None = None, mime_type: str = "audio/webm"
    ) -> TranscriptionResult:
        if not self.configured:
            raise ProviderNotConfigured(
                "BHASHINI credentials are not configured. Falling back to text input."
            )
        payload = {
            "pipelineTasks": [
                {
                    "taskType": "asr",
                    "config": {
                        "language": {"sourceLanguage": language_hint or "hi"},
                        "audioFormat": mime_type.split("/")[-1],
                    },
                }
            ],
            "inputData": {"audio": [{"audioContent": base64.b64encode(audio).decode("ascii")}]},
        }
        headers = {
            "Authorization": self.api_key,
            "userID": self.user_id,
            "ulcaApiKey": self.api_key,
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(self.endpoint, json=payload, headers=headers, timeout=30.0)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderNotConfigured(f"BHASHINI request failed: {exc}") from exc

        try:
            output = body["pipelineResponse"][0]["output"][0]
            text = output["source"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderNotConfigured("Unexpected BHASHINI response shape") from exc

        return TranscriptionResult(
            text=text,
            language=language_hint or "hi",
            language_confidence=0.8,
            # BHASHINI does not currently return a per-utterance confidence;
            # we record a conservative default rather than invent a number.
            asr_confidence=float(output.get("confidence", 0.7)),
            provider=self.name,
            raw=body,
        )


@lru_cache
def get_speech_provider() -> SpeechProvider:
    settings = get_settings()
    match settings.speech_provider:
        case "mock":
            return MockSpeechProvider()
        case "bhashini":
            return BhashiniSpeechProvider()
        case _:
            return BrowserSpeechProvider()


def all_speech_statuses() -> list[ProviderStatus]:
    return [
        BrowserSpeechProvider().status(),
        MockSpeechProvider().status(),
        BhashiniSpeechProvider().status(),
    ]
