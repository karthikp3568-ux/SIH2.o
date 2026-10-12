"""Conversation state: transcripts, language detection and slot filling."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: These two columns are read-modify-written every turn. Wrapping them in
#: MutableDict makes SQLAlchemy notice in-place changes; without it a mutated
#: dict compares equal to its own pre-image at flush time and the UPDATE is
#: silently skipped.
MutableJSON = MutableDict.as_mutable(JSON)


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    beneficiary_id: Mapped[str] = mapped_column(
        ForeignKey("beneficiary_profiles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    channel: Mapped[str] = mapped_column(String(32), default="web_text", nullable=False)
    language: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    #: active | awaiting_confirmation | confirmed | abandoned
    state: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    #: Slot name -> {value, confidence, source, filled_at}. Survives interruption,
    #: which is what makes the conversation resumable.
    slots: Mapped[dict] = mapped_column(MutableJSON, default=dict, nullable=False)
    #: Slot the assistant is currently asking about.
    pending_slot: Mapped[str | None] = mapped_column(String(48))
    #: Draft profile awaiting explicit beneficiary confirmation.
    draft_profile: Mapped[dict] = mapped_column(MutableJSON, default=dict, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.sequence",
    )


class ConversationMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversation_messages"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    #: beneficiary | assistant | system
    role: Mapped[str] = mapped_column(String(16), nullable=False)

    #: Exactly what came off the wire (ASR output or typed text).
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    #: Lower-cased, de-punctuated, digit/number-word normalised form.
    normalized_text: Mapped[str | None] = mapped_column(Text)
    detected_language: Mapped[str | None] = mapped_column(String(8))
    language_confidence: Mapped[float | None] = mapped_column(Float)
    #: ASR confidence, 0..1. None for typed input.
    asr_confidence: Mapped[float | None] = mapped_column(Float)
    #: True when code-switching (e.g. Hindi + English) was detected.
    is_code_switched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), default="web_text", nullable=False)
    #: browser_web_speech | mock | bhashini | typed
    speech_provider: Mapped[str | None] = mapped_column(String(32))
    #: Entities pulled out of this turn, kept for admin review of AI extraction.
    extracted_entities: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    #: Set when the assistant had to ask the beneficiary to repeat/confirm.
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    audio_reference: Mapped[str | None] = mapped_column(String(300))
    audio_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Client-generated id for one utterance. A retried or duplicated request
    #: carrying the same id returns the stored result instead of re-processing.
    client_message_id: Mapped[str | None] = mapped_column(String(64))
    #: The response this turn produced, replayed for duplicate submissions.
    response_snapshot: Mapped[dict | None] = mapped_column(JSON)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_message_conversation_seq", "conversation_id", "sequence", unique=True),
        Index(
            "ix_message_conversation_client_id", "conversation_id", "client_message_id", unique=True
        ),
    )
