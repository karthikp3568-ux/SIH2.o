"""Conversation schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..core.enums import Channel, Language
from .common import LocationIn


class ConversationStartRequest(BaseModel):
    language: Language | None = None
    channel: Channel = Channel.WEB_TEXT
    #: Resume the most recent unfinished conversation instead of starting fresh.
    resume: bool = True


class SlotOptionOut(BaseModel):
    value: str
    label: str
    icon: str | None = None


class SlotOut(BaseModel):
    name: str
    priority: int
    required: bool
    input_type: str
    question: str
    help: str | None = None
    depends_on: str | None = None
    options: list[SlotOptionOut] = Field(default_factory=list)


class ConversationMessageOut(BaseModel):
    id: str
    sequence: int
    role: str
    raw_text: str
    normalized_text: str | None = None
    detected_language: str | None = None
    language_confidence: float | None = None
    asr_confidence: float | None = None
    is_code_switched: bool = False
    channel: str
    speech_provider: str | None = None
    needs_confirmation: bool = False
    created_at: str | None = None


class ConversationOut(BaseModel):
    id: str
    beneficiary_id: str
    state: str
    language: str
    channel: str
    pending_slot: SlotOut | None = None
    draft_profile: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    messages: list[ConversationMessageOut] = Field(default_factory=list)


class ConversationStartResponse(BaseModel):
    conversation: ConversationOut
    assistant_message: str
    slots: list[SlotOut]
    #: BCP-47 tag the browser should hand to the Web Speech API.
    speech_language_tag: str
    speech_provider: str


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    language: Language | None = None
    channel: Channel | None = None
    #: 0..1 from the browser's recogniser. Omit for typed input.
    asr_confidence: float | None = Field(default=None, ge=0, le=1)
    speech_provider: str | None = Field(default=None, max_length=32)
    #: Set when the user tapped one of the options for the pending slot.
    slot_answer: str | None = Field(default=None, max_length=64)


class MessageResponse(BaseModel):
    conversation_id: str
    assistant_message: str
    pending_slot: SlotOut | None = None
    draft_profile: dict[str, Any]
    extraction: dict[str, Any] | None = None
    newly_filled: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False
    ready_to_confirm: bool = False
    transcript_for_correction: str | None = None
    progress: dict[str, Any] = Field(default_factory=dict)


class ConfirmRequest(BaseModel):
    """The beneficiary confirms - and may correct - what was understood."""

    #: Full corrected draft. When omitted the stored draft is committed as is.
    draft_profile: dict[str, Any] | None = None
    location: LocationIn | None = None
    generate_recommendations: bool = True


class ConfirmResponse(BaseModel):
    profile: dict[str, Any]
    recommendations_generated: bool
    recommendation_run_id: str | None = None


class TranscribeResponse(BaseModel):
    """Returned by the server-side ASR endpoint when a provider is configured."""

    text: str
    language: str
    language_confidence: float
    asr_confidence: float
    provider: str
    is_code_switched: bool = False
    stored_audio: bool = False
