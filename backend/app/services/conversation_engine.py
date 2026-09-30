"""Adaptive conversation engine.

No fixed questionnaire. Each turn the engine extracts what it can, folds it
into a draft profile, then asks about the single highest-value fact still
missing. The conversation is:

* short        - only unanswered slots are asked about
* confirmable  - nothing reaches the real profile until the beneficiary confirms
* interruptible / resumable - all state lives in `conversations.slots`
* low-confidence aware - a poor ASR result triggers a repeat/correct turn
  instead of silently committing a misheard fact
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.enums import Channel, Language
from ..core.slots import SLOTS_BY_NAME, SlotDefinition, ordered_slots
from ..models import (
    BeneficiaryProfile,
    Conversation,
    ConversationMessage,
    utcnow,
)
from .language_id import detect_language, normalize_text
from .profile_extraction import ExtractionResult, get_profile_extractor
from .profile_service import filled_slots_from_draft, merge_extraction, new_draft

settings = get_settings()


GREETINGS: dict[str, str] = {
    "en": "Tell me about the work you do and what you would like to do next. Speak normally - I will listen.",
    "hi": "मुझे बताइए कि आप क्या काम करते हैं और आगे क्या करना चाहते हैं। आराम से बोलिए, मैं सुन रहा हूँ।",
    "mr": "तुम्ही कोणते काम करता आणि पुढे काय करू इच्छिता ते सांगा. सहज बोला, मी ऐकतो आहे.",
    "ta": "நீங்கள் என்ன வேலை செய்கிறீர்கள், அடுத்து என்ன செய்ய விரும்புகிறீர்கள் என்று சொல்லுங்கள். சாதாரணமாகப் பேசுங்கள்.",
    "te": "మీరు ఏ పని చేస్తారో, తర్వాత ఏమి చేయాలనుకుంటున్నారో చెప్పండి. మామూలుగా మాట్లాడండి.",
    "bn": "আপনি কী কাজ করেন এবং এরপর কী করতে চান বলুন। স্বাভাবিকভাবে বলুন, আমি শুনছি।",
}

LOW_CONFIDENCE_PROMPTS: dict[str, str] = {
    "en": "I did not catch that clearly. Could you say it again, or type it instead?",
    "hi": "मुझे ठीक से सुनाई नहीं दिया। कृपया दोबारा बोलिए, या लिख दीजिए।",
    "mr": "मला नीट ऐकू आले नाही. पुन्हा सांगाल का, किंवा लिहून द्याल का?",
    "ta": "தெளிவாகக் கேட்கவில்லை. மீண்டும் சொல்ல முடியுமா, அல்லது தட்டச்சு செய்யுங்கள்.",
    "te": "సరిగ్గా వినిపించలేదు. మళ్లీ చెప్పగలరా, లేదా టైప్ చేయండి.",
    "bn": "ঠিকমতো শুনতে পাইনি। আবার বলবেন, নাকি লিখে দেবেন?",
}

NOTHING_UNDERSTOOD: dict[str, str] = {
    "en": "I could not pick out anything about your work from that. Could you tell me what work you do?",
    "hi": "इससे मुझे आपके काम के बारे में कुछ समझ नहीं आया। आप क्या काम करते हैं?",
    "mr": "यातून तुमच्या कामाबद्दल काही समजले नाही. तुम्ही कोणते काम करता?",
    "ta": "உங்கள் வேலை பற்றி எதுவும் புரியவில்லை. நீங்கள் என்ன வேலை செய்கிறீர்கள்?",
    "te": "మీ పని గురించి ఏమీ అర్థం కాలేదు. మీరు ఏ పని చేస్తారు?",
    "bn": "আপনার কাজ সম্পর্কে কিছু বুঝতে পারিনি। আপনি কী কাজ করেন?",
}

READY_TO_CONFIRM: dict[str, str] = {
    "en": "Thank you. Here is what I understood. Please check it and correct anything that is wrong.",
    "hi": "धन्यवाद। मैंने यह समझा है। कृपया देख लीजिए और कुछ ग़लत हो तो ठीक कर दीजिए।",
    "mr": "धन्यवाद. मला हे समजले आहे. कृपया तपासा आणि काही चुकले असल्यास दुरुस्त करा.",
    "ta": "நன்றி. நான் புரிந்துகொண்டது இதுதான். சரிபார்த்து தவறு இருந்தால் திருத்துங்கள்.",
    "te": "ధన్యవాదాలు. నేను అర్థం చేసుకున్నది ఇదే. తనిఖీ చేసి తప్పు ఉంటే సరిచేయండి.",
    "bn": "ধন্যবাদ। আমি এটুকু বুঝেছি। দেখে নিন এবং ভুল থাকলে ঠিক করুন।",
}

ACKNOWLEDGEMENTS: dict[str, str] = {
    "en": "Got it.",
    "hi": "समझ गया।",
    "mr": "समजले.",
    "ta": "புரிந்தது.",
    "te": "అర్థమైంది.",
    "bn": "বুঝেছি।",
}


def _localised(table: dict[str, str], language: str) -> str:
    return table.get(language) or table["en"]


@dataclass
class TurnResult:
    conversation: Conversation
    assistant_message: str
    extraction: ExtractionResult | None
    draft: dict[str, Any]
    pending_slot: SlotDefinition | None
    needs_confirmation: bool = False
    ready_to_confirm: bool = False
    transcript_for_correction: str | None = None
    newly_filled: list[str] = field(default_factory=list)
    progress: dict[str, Any] = field(default_factory=dict)


def start_conversation(
    db: Session,
    beneficiary: BeneficiaryProfile,
    *,
    language: str | None = None,
    channel: str = Channel.WEB_TEXT,
) -> tuple[Conversation, str]:
    """Open a conversation and return the greeting."""
    resolved_language = language or beneficiary.preferred_language or Language.EN
    conversation = Conversation(
        beneficiary_id=beneficiary.id,
        channel=channel,
        language=resolved_language,
        state="active",
        slots={},
        draft_profile=new_draft(),
    )
    db.add(conversation)
    db.flush()

    greeting = _localised(GREETINGS, resolved_language)
    _append_message(
        db,
        conversation,
        role="assistant",
        raw_text=greeting,
        channel=channel,
        detected_language=resolved_language,
    )
    db.commit()
    db.refresh(conversation)
    return conversation, greeting


def _append_message(
    db: Session,
    conversation: Conversation,
    *,
    role: str,
    raw_text: str,
    channel: str,
    normalized_text: str | None = None,
    detected_language: str | None = None,
    language_confidence: float | None = None,
    asr_confidence: float | None = None,
    is_code_switched: bool = False,
    speech_provider: str | None = None,
    extracted_entities: dict | None = None,
    needs_confirmation: bool = False,
    audio_reference: str | None = None,
) -> ConversationMessage:
    next_sequence = (
        db.execute(
            select(func.coalesce(func.max(ConversationMessage.sequence), -1)).where(
                ConversationMessage.conversation_id == conversation.id
            )
        ).scalar_one()
        + 1
    )
    message = ConversationMessage(
        conversation_id=conversation.id,
        sequence=next_sequence,
        role=role,
        raw_text=raw_text,
        normalized_text=normalized_text,
        detected_language=detected_language,
        language_confidence=language_confidence,
        asr_confidence=asr_confidence,
        is_code_switched=is_code_switched,
        channel=channel,
        speech_provider=speech_provider,
        extracted_entities=extracted_entities or {},
        needs_confirmation=needs_confirmation,
        audio_reference=audio_reference,
    )
    db.add(message)
    db.flush()
    return message


def next_slot(draft: dict[str, Any], asked: set[str]) -> SlotDefinition | None:
    """Highest-priority unanswered slot whose dependency is satisfied.

    Optional slots are only asked once every required slot is filled, and no
    slot is asked twice - if the beneficiary does not answer, we move on rather
    than looping.
    """
    filled = filled_slots_from_draft(draft)
    required_outstanding = [
        slot
        for slot in ordered_slots()
        if slot.required and slot.name not in filled and slot.name not in asked
    ]
    if required_outstanding:
        return required_outstanding[0]

    for slot in ordered_slots():
        if slot.required or slot.name in filled or slot.name in asked:
            continue
        if slot.depends_on and slot.depends_on not in filled:
            continue
        return slot
    return None


def handle_message(
    db: Session,
    conversation: Conversation,
    text: str,
    *,
    channel: str | None = None,
    language_hint: str | None = None,
    asr_confidence: float | None = None,
    speech_provider: str | None = None,
    slot_answer: str | None = None,
    audio_reference: str | None = None,
) -> TurnResult:
    """Process one beneficiary turn."""
    channel = channel or conversation.channel
    # Deep copy: the draft is nested, and mutating the loaded value in place
    # would leave SQLAlchemy unable to tell the column changed.
    slots_state: dict[str, Any] = deepcopy(dict(conversation.slots or {}))
    asked: set[str] = set(slots_state.get("_asked", []))
    draft: dict[str, Any] = deepcopy(dict(conversation.draft_profile or new_draft()))

    detection = detect_language(text, language_hint or conversation.language)
    normalized = normalize_text(text)

    # --- low ASR confidence: confirm before committing anything -------------
    if asr_confidence is not None and asr_confidence < settings.asr_confidence_threshold:
        _append_message(
            db,
            conversation,
            role="beneficiary",
            raw_text=text,
            normalized_text=normalized,
            channel=channel,
            detected_language=detection.language,
            language_confidence=detection.confidence,
            asr_confidence=asr_confidence,
            is_code_switched=detection.is_code_switched,
            speech_provider=speech_provider,
            needs_confirmation=True,
            audio_reference=audio_reference,
        )
        prompt = _localised(LOW_CONFIDENCE_PROMPTS, conversation.language)
        _append_message(
            db, conversation, role="assistant", raw_text=prompt, channel=channel,
            detected_language=conversation.language, needs_confirmation=True,
        )
        db.commit()
        db.refresh(conversation)
        return TurnResult(
            conversation=conversation,
            assistant_message=prompt,
            extraction=None,
            draft=draft,
            pending_slot=SLOTS_BY_NAME.get(conversation.pending_slot or ""),
            needs_confirmation=True,
            transcript_for_correction=text,
            progress=_progress(draft),
        )

    # --- extraction ---------------------------------------------------------
    extractor = get_profile_extractor()
    extraction = extractor.extract(db, text, language_hint or conversation.language)

    # A tapped choice answers its slot directly; the free text is still parsed
    # so an unprompted extra fact in the same turn is not lost.
    if slot_answer and conversation.pending_slot:
        draft = _apply_slot_answer(draft, conversation.pending_slot, slot_answer)

    before = filled_slots_from_draft(draft)
    draft = merge_extraction(draft, extraction)
    after = filled_slots_from_draft(draft)
    newly_filled = sorted(after - before)

    if detection.confidence >= 0.5:
        conversation.language = detection.language

    _append_message(
        db,
        conversation,
        role="beneficiary",
        raw_text=text,
        normalized_text=extraction.normalized_text or normalized,
        channel=channel,
        detected_language=extraction.language,
        language_confidence=extraction.language_confidence,
        asr_confidence=asr_confidence,
        is_code_switched=extraction.is_code_switched,
        speech_provider=speech_provider,
        extracted_entities=extraction.to_summary(),
        audio_reference=audio_reference,
    )

    if conversation.pending_slot:
        asked.add(conversation.pending_slot)

    # --- choose the next question ------------------------------------------
    upcoming = next_slot(draft, asked)
    filled = filled_slots_from_draft(draft)
    required_done = all(
        slot.name in filled or slot.name in asked
        for slot in ordered_slots()
        if slot.required
    )

    if not after and not newly_filled and not required_done:
        # Understood nothing at all from a confident transcript.
        assistant_message = _localised(NOTHING_UNDERSTOOD, conversation.language)
        upcoming = SLOTS_BY_NAME["occupation"]
        ready = False
    elif upcoming is not None and not required_done:
        acknowledgement = _localised(ACKNOWLEDGEMENTS, conversation.language) if newly_filled else ""
        assistant_message = (
            f"{acknowledgement} {upcoming.question_for(conversation.language)}".strip()
        )
        ready = False
    elif upcoming is not None and required_done and upcoming.required is False and not asked:
        assistant_message = upcoming.question_for(conversation.language)
        ready = False
    else:
        assistant_message = _localised(READY_TO_CONFIRM, conversation.language)
        upcoming = None
        ready = True

    conversation.pending_slot = upcoming.name if upcoming else None
    conversation.state = "awaiting_confirmation" if ready else "active"
    slots_state["_asked"] = sorted(asked)
    slots_state.update({name: True for name in filled})
    conversation.slots = slots_state
    conversation.draft_profile = draft

    _append_message(
        db,
        conversation,
        role="assistant",
        raw_text=assistant_message,
        channel=channel,
        detected_language=conversation.language,
    )
    db.commit()
    db.refresh(conversation)

    return TurnResult(
        conversation=conversation,
        assistant_message=assistant_message,
        extraction=extraction,
        draft=draft,
        pending_slot=upcoming,
        ready_to_confirm=ready,
        newly_filled=newly_filled,
        progress=_progress(draft),
    )


def _apply_slot_answer(draft: dict[str, Any], slot_name: str, value: str) -> dict[str, Any]:
    """Record an answer chosen from options rather than spoken."""
    fact = {"value": value, "confidence": 0.95, "evidence": "Chosen from the options shown", "extractor": "user_choice"}
    match slot_name:
        case "education":
            draft["education"] = fact
        case "mobility":
            draft["mobility"] = fact
        case "goal":
            if value not in {g["value"] for g in draft.get("goals", [])}:
                draft.setdefault("goals", []).append(fact)
        case _:
            pass
    return draft


def _progress(draft: dict[str, Any]) -> dict[str, Any]:
    filled = filled_slots_from_draft(draft)
    required = [s.name for s in ordered_slots() if s.required]
    return {
        "filled": sorted(filled),
        "required": required,
        "required_filled": sorted(set(required) & filled),
        "percent": round(100 * len(set(required) & filled) / max(1, len(required))),
    }


def progress_for(draft: dict[str, Any] | None) -> dict[str, Any]:
    """Public accessor for slot-filling progress."""
    return _progress(draft or new_draft())


def resume(db: Session, beneficiary_id: str) -> Conversation | None:
    """Most recent unfinished conversation, so a dropped call can continue."""
    return db.execute(
        select(Conversation)
        .where(
            Conversation.beneficiary_id == beneficiary_id,
            Conversation.state.in_(["active", "awaiting_confirmation"]),
        )
        .order_by(Conversation.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def mark_confirmed(db: Session, conversation: Conversation) -> None:
    conversation.state = "confirmed"
    conversation.completed_at = utcnow()
    conversation.pending_slot = None
    db.flush()
