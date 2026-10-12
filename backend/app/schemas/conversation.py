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
    #: Client-generated id for this utterance. Sending the same id twice (a
    #: double-fired speech event, a network retry) returns the first result.
    client_message_id: str | None = Field(default=None, min_length=8, max_length=64)
    #: Id of a low-confidence message the person has now confirmed, so it is
    #: processed in place instead of being stored a second time.
    confirm_message_id: str | None = Field(default=None, max_length=64)


class UnderstoodFact(BaseModel):
    slot: str
    label: str


class MessageResponse(BaseModel):
    conversation_id: str
    #: Server id of the stored beneficiary message.
    message_id: str | None = None
    client_message_id: str | None = None
    #: Language the assistant answered in.
    language: str = "en"
    transcript: str = ""
    transcript_confidence: float | None = None
    assistant_message: str
    #: Same text as assistant_message; the question to show and speak next.
    next_question: str = ""
    next_slot: str | None = None
    #: active | awaiting_confirmation
    current_state: str = "active"
    pending_slot: SlotOut | None = None
    draft_profile: dict[str, Any]
    #: What this turn added, already worded for display ("+ Pump repair").
    profile_update: list[UnderstoodFact] = Field(default_factory=list)
    extraction: dict[str, Any] | None = None
    newly_filled: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False
    ready_to_confirm: bool = False
    transcript_for_correction: str | None = None
    #: True when the answer was not understood and the question was rephrased.
    clarification: bool = False
    #: True when this is the stored result of an already-processed message id.
    replayed: bool = False
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
