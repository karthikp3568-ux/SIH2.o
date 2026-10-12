"""Phase 1 - conversation, speech and channel ingestion."""

from __future__ import annotations

import logging
import secrets
import threading
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.exc import IntegrityError

from ..config import get_settings
from ..core.enums import LANGUAGE_BCP47, Channel
from ..core.rate_limit import conversation_rate_limit
from ..core.slots import SLOTS_BY_NAME, slot_catalogue
from ..deps import CurrentBeneficiary, CurrentUser, DbSession
from ..models import Conversation, utcnow
from ..providers import get_channel_adapter, get_speech_provider
from ..providers.base import ProviderNotConfigured
from ..schemas.conversation import (
    ConfirmRequest,
    ConfirmResponse,
    ConversationOut,
    ConversationStartRequest,
    ConversationStartResponse,
    MessageRequest,
    MessageResponse,
    SlotOut,
    TranscribeResponse,
)
from ..services import conversation_engine as engine
from ..services import profile_service
from ..services.recommendation import generate_recommendations

router = APIRouter(prefix="/conversation", tags=["conversation"])
logger = logging.getLogger(__name__)
settings = get_settings()

#: One turn at a time per conversation within this process, so two requests
#: cannot read the same draft and overwrite each other's facts. Across
#: processes the unique (conversation_id, client_message_id) index and the
#: row lock on PostgreSQL provide the same guarantee.
_turn_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def _slot_out(slot_name: str | None, language: str) -> SlotOut | None:
    if not slot_name:
        return None
    slot = SLOTS_BY_NAME.get(slot_name)
    if slot is None:
        return None
    return SlotOut(
        name=slot.name,
        priority=slot.priority,
        required=slot.required,
        input_type=slot.input_type,
        question=slot.question_for(language),
        help=slot.help_for(language),
        depends_on=slot.depends_on,
        options=[
            {"value": o.value, "label": o.label_for(language), "icon": o.icon}
            for o in slot.options
        ],
    )


def _conversation_out(conversation: Conversation, include_messages: bool = True) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        beneficiary_id=conversation.beneficiary_id,
        state=conversation.state,
        language=conversation.language,
        channel=conversation.channel,
        pending_slot=_slot_out(conversation.pending_slot, conversation.language),
        draft_profile=conversation.draft_profile or {},
        progress=engine.progress_for(conversation.draft_profile),
        messages=[
            {
                "id": m.id,
                "sequence": m.sequence,
                "role": m.role,
                "raw_text": m.raw_text,
                "normalized_text": m.normalized_text,
                "detected_language": m.detected_language,
                "language_confidence": m.language_confidence,
                "asr_confidence": m.asr_confidence,
                "is_code_switched": m.is_code_switched,
                "channel": m.channel,
                "speech_provider": m.speech_provider,
                "needs_confirmation": m.needs_confirmation,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in conversation.messages
        ]
        if include_messages
        else [],
    )


@router.post(
    "/start",
    response_model=ConversationStartResponse,
    dependencies=[Depends(conversation_rate_limit)],
)
def start(
    payload: ConversationStartRequest, beneficiary: CurrentBeneficiary, db: DbSession
) -> ConversationStartResponse:
    language = str(payload.language) if payload.language else beneficiary.preferred_language

    conversation = engine.resume(db, beneficiary.id) if payload.resume else None
    if conversation is not None:
        assistant_message = next(
            (m.raw_text for m in reversed(conversation.messages) if m.role == "assistant"),
            "",
        )
    else:
        conversation, assistant_message = engine.start_conversation(
            db, beneficiary, language=language, channel=str(payload.channel)
        )

    return ConversationStartResponse(
        conversation=_conversation_out(conversation),
        assistant_message=assistant_message,
        slots=[SlotOut(**s) for s in slot_catalogue(conversation.language)],
        speech_language_tag=LANGUAGE_BCP47.get(conversation.language, "en-IN"),
        speech_provider=get_speech_provider().name,
    )


@router.post(
    "/{conversation_id}/message",
    response_model=MessageResponse,
    dependencies=[Depends(conversation_rate_limit)],
)
def send_message(
    conversation_id: str,
    payload: MessageRequest,
    beneficiary: CurrentBeneficiary,
    db: DbSession,
) -> MessageResponse:
    with _turn_locks[conversation_id]:
        conversation = db.get(Conversation, conversation_id, with_for_update=True)
        if conversation is None or conversation.beneficiary_id != beneficiary.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        if conversation.state == "confirmed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This conversation is already confirmed. Start a new one to make changes.",
            )
        try:
            result = engine.handle_message(
                db,
                conversation,
                payload.text,
                channel=str(payload.channel) if payload.channel else None,
                language_hint=str(payload.language) if payload.language else None,
                asr_confidence=payload.asr_confidence,
                speech_provider=payload.speech_provider,
                slot_answer=payload.slot_answer,
                client_message_id=payload.client_message_id,
                confirm_message_id=payload.confirm_message_id,
            )
        except IntegrityError:
            # Another worker stored this client_message_id first: return its result.
            db.rollback()
            existing = (
                engine.find_by_client_id(db, conversation, payload.client_message_id)
                if payload.client_message_id
                else None
            )
            result = engine.replay(conversation, existing) if existing is not None else None
            if result is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This message is already being processed.",
                ) from None

    language = result.language or conversation.language
    return MessageResponse(
        conversation_id=conversation.id,
        message_id=result.message_id,
        client_message_id=payload.client_message_id,
        language=language,
        transcript=payload.text,
        transcript_confidence=payload.asr_confidence,
        assistant_message=result.assistant_message,
        next_question=result.assistant_message,
        next_slot=result.pending_slot.name if result.pending_slot else None,
        current_state="awaiting_confirmation" if result.ready_to_confirm else "active",
        pending_slot=_slot_out(result.pending_slot.name if result.pending_slot else None, language),
        draft_profile=result.draft,
        profile_update=result.understood,
        extraction=result.extraction.to_summary() if result.extraction else None,
        newly_filled=result.newly_filled,
        needs_confirmation=result.needs_confirmation,
        ready_to_confirm=result.ready_to_confirm,
        transcript_for_correction=result.transcript_for_correction,
        clarification=result.clarification,
        replayed=result.replayed,
        progress=result.progress,
    )


@router.get("/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str, beneficiary: CurrentBeneficiary, db: DbSession
) -> ConversationOut:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.beneficiary_id != beneficiary.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return _conversation_out(conversation)


@router.post("/{conversation_id}/confirm", response_model=ConfirmResponse)
def confirm(
    conversation_id: str,
    payload: ConfirmRequest,
    user: CurrentUser,
    beneficiary: CurrentBeneficiary,
    db: DbSession,
) -> ConfirmResponse:
    """The beneficiary confirms (and may correct) the extracted profile.

    This is the only path by which conversation output becomes profile data.
    """
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.beneficiary_id != beneficiary.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    draft = payload.draft_profile if payload.draft_profile is not None else conversation.draft_profile
    if payload.location is not None:
        draft = {**(draft or {}), "location": payload.location.model_dump(exclude_none=True)}

    profile_service.apply_draft(
        db, beneficiary, draft or {}, actor=user, conversation_id=conversation.id
    )
    conversation.draft_profile = draft or {}
    engine.mark_confirmed(db, conversation)
    db.commit()

    run_id = None
    generated = False
    if payload.generate_recommendations:
        try:
            result = generate_recommendations(db, beneficiary, actor=user)
            run_id = result.run.id
            generated = True
        except Exception:  # pragma: no cover - degrade rather than lose the profile
            logger.exception("Recommendation generation failed after profile confirmation")

    return ConfirmResponse(
        profile=profile_service.profile_to_dict(beneficiary),
        recommendations_generated=generated,
        recommendation_run_id=run_id,
    )


# ---------------------------------------------------------------------------
# Server-side speech
# ---------------------------------------------------------------------------

speech_router = APIRouter(prefix="/speech", tags=["speech"])


@speech_router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    dependencies=[Depends(conversation_rate_limit)],
)
async def transcribe(
    user: CurrentUser,
    audio: Annotated[UploadFile, File(description="Audio clip to transcribe")],
    language: Annotated[str | None, Form()] = None,
) -> TranscribeResponse:
    """Server-side transcription, when a server-side ASR provider is configured.

    With the default `browser` provider this returns 503 with an explanation
    rather than a fabricated transcript - the browser is expected to have done
    the recognition already.
    """
    raw = await audio.read()
    if len(raw) > settings.max_audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio must be under {settings.max_audio_bytes // 1024 // 1024} MB.",
        )
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty audio upload.")

    provider = get_speech_provider()
    try:
        result = provider.transcribe(
            raw, language_hint=language, mime_type=audio.content_type or "audio/webm"
        )
    except ProviderNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"{exc} Speech recognition is not available on the server right now; "
                "please use text input."
            ),
        ) from exc

    stored = False
    if settings.store_raw_audio:
        # Only written when explicitly enabled; the filename carries no PII.
        directory = settings.audio_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{utcnow():%Y%m%d}-{secrets.token_hex(8)}.bin"
        path.write_bytes(raw)
        stored = True

    return TranscribeResponse(
        text=result.text,
        language=result.language,
        language_confidence=result.language_confidence,
        asr_confidence=result.asr_confidence,
        provider=result.provider,
        is_code_switched=result.is_code_switched,
        stored_audio=stored,
    )


# ---------------------------------------------------------------------------
# Channel adapters (WhatsApp / IVR)
# ---------------------------------------------------------------------------

channels_router = APIRouter(prefix="/channels", tags=["channels"])


@channels_router.get("/status")
def channel_status() -> dict:
    """Which channels can receive and which can send, stated plainly."""
    from dataclasses import asdict  # noqa: PLC0415

    from ..providers.messaging import all_messaging_statuses  # noqa: PLC0415

    return {
        "note": (
            "Inbound webhook parsing is implemented and can be exercised now. "
            "Outbound sending requires provider credentials and is disabled without them."
        ),
        "channels": [asdict(s) for s in all_messaging_statuses()],
    }


@channels_router.post("/{channel}/inbound")
def inbound(channel: str, payload: dict, request: Request, db: DbSession) -> dict:
    """Normalise an inbound webhook payload into the internal message shape.

    This endpoint demonstrates the adapter without pretending to be connected:
    it parses and returns the normalised message. Wiring it to a live
    conversation requires mapping the sender reference to an account, which is
    a deployment decision (phone-number verification) rather than a code gap.
    """
    if channel not in {Channel.WHATSAPP, Channel.IVR}:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown channel '{channel}'."
        )
    adapter = get_channel_adapter(channel)
    try:
        message = adapter.parse_inbound(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {
        "accepted": True,
        "channel": message.channel,
        "sender_ref": message.sender_ref,
        "text": message.text,
        "language_hint": message.language_hint,
        "metadata": message.metadata,
        "outbound_sending_configured": adapter.status().configured,
        "next_step": (
            "Map sender_ref to a verified account, then call "
            "/api/conversation/{id}/message with this text."
        ),
    }
