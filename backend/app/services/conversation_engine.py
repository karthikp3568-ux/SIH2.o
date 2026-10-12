"""Adaptive conversation engine.

No fixed questionnaire. Each turn the engine understands what it can (see
`semantic_understanding`), folds it into a draft profile, then asks about the
single highest-value fact still missing. The conversation is:

* stateful     - the draft and the slot state live in `conversations`, so every
                 turn builds on the previous ones and a refresh resumes it
* short        - a slot that is already known is never asked about
* never stuck  - an answer that is not understood gets one rephrased question
                 with an example; after that the engine moves on instead of
                 looping on the same question
* confirmable  - nothing reaches the real profile until the beneficiary confirms
* idempotent   - a client message id is processed once; a duplicate gets the
                 stored result back
* low-confidence aware - a poor ASR result is confirmed before it is used
"""

from __future__ import annotations

import logging
import time
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
from .labels import describe_new_facts
from .language_id import detect_language, normalize_text
from .profile_extraction import ExtractionResult, get_profile_extractor
from .profile_service import filled_slots_from_draft, merge_extraction, new_draft
from .semantic_understanding import ExtractionContext

settings = get_settings()
logger = logging.getLogger("app.conversation")

#: Languages the assistant can speak back in. Others fall back to English text.
SPOKEN_LANGUAGES = {"en", "hi", "kn", "mr", "ta", "te", "bn"}


GREETINGS: dict[str, str] = {
    "en": "Tell me about the work you do and what you would like to do next. Speak normally - I will listen.",
    "hi": "मुझे बताइए कि आप क्या काम करते हैं और आगे क्या करना चाहते हैं। आराम से बोलिए, मैं सुन रहा हूँ।",
    "kn": "ನೀವು ಯಾವ ಕೆಲಸ ಮಾಡುತ್ತೀರಿ ಮತ್ತು ಮುಂದೆ ಏನು ಮಾಡಲು ಬಯಸುತ್ತೀರಿ ಎಂದು ಹೇಳಿ. ಸಹಜವಾಗಿ ಮಾತನಾಡಿ - ನಾನು ಕೇಳುತ್ತಿದ್ದೇನೆ.",
    "mr": "तुम्ही कोणते काम करता आणि पुढे काय करू इच्छिता ते सांगा. सहज बोला, मी ऐकतो आहे.",
    "ta": "நீங்கள் என்ன வேலை செய்கிறீர்கள், அடுத்து என்ன செய்ய விரும்புகிறீர்கள் என்று சொல்லுங்கள். சாதாரணமாகப் பேசுங்கள்.",
    "te": "మీరు ఏ పని చేస్తారో, తర్వాత ఏమి చేయాలనుకుంటున్నారో చెప్పండి. మామూలుగా మాట్లాడండి.",
    "bn": "আপনি কী কাজ করেন এবং এরপর কী করতে চান বলুন। স্বাভাবিকভাবে বলুন, আমি শুনছি।",
}

LOW_CONFIDENCE_PROMPTS: dict[str, str] = {
    "en": "I’m not sure I heard that clearly. Is this what you said? You can also try again, or type it.",
    "hi": "मुझे ठीक से सुनाई नहीं दिया। क्या आपने यही कहा? आप दोबारा बोल सकते हैं, या लिख सकते हैं।",
    "kn": "ನನಗೆ ಅದು ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ನೀವು ಹೇಳಿದ್ದು ಇದೇನಾ? ಮತ್ತೊಮ್ಮೆ ಹೇಳಬಹುದು, ಅಥವಾ ಟೈಪ್ ಮಾಡಬಹುದು.",
    "mr": "मला नीट ऐकू आले नाही. तुम्ही हेच म्हणालात का? पुन्हा सांगा, किंवा लिहून द्या.",
    "ta": "தெளிவாகக் கேட்கவில்லை. நீங்கள் சொன்னது இதுவா? மீண்டும் சொல்லலாம், அல்லது தட்டச்சு செய்யலாம்.",
    "te": "సరిగ్గా వినిపించలేదు. మీరు చెప్పింది ఇదేనా? మళ్లీ చెప్పవచ్చు, లేదా టైప్ చేయవచ్చు.",
    "bn": "ঠিকমতো শুনতে পাইনি। আপনি কি এটাই বললেন? আবার বলতে পারেন, বা লিখে দিতে পারেন।",
}

NOT_SURE: dict[str, str] = {
    "en": "I’m not fully sure I understood that. Could you say it another way?",
    "hi": "मुझे पूरी तरह समझ नहीं आया। क्या आप इसे दूसरे तरीके से कह सकते हैं?",
    "kn": "ನನಗೆ ಅದು ಸಂಪೂರ್ಣವಾಗಿ ಅರ್ಥವಾಗಲಿಲ್ಲ. ಬೇರೆ ರೀತಿಯಲ್ಲಿ ಹೇಳಬಹುದೇ?",
    "mr": "मला ते पूर्णपणे समजले नाही. तुम्ही वेगळ्या शब्दांत सांगाल का?",
    "ta": "எனக்கு அது முழுமையாகப் புரியவில்லை. வேறு விதமாகச் சொல்ல முடியுமா?",
    "te": "నాకు అది పూర్తిగా అర్థం కాలేదు. వేరే విధంగా చెప్పగలరా?",
    "bn": "আমি পুরোপুরি বুঝতে পারিনি। অন্যভাবে বলতে পারবেন?",
}

EXAMPLE_PREFIX: dict[str, str] = {
    "en": "For example:",
    "hi": "उदाहरण के लिए:",
    "kn": "ಉದಾಹರಣೆಗೆ:",
    "mr": "उदाहरणार्थ:",
    "ta": "உதாரணமாக:",
    "te": "ఉదాహరణకు:",
    "bn": "যেমন:",
}

MOVE_ON: dict[str, str] = {
    "en": "No problem - let’s move on. You can add it on the next screen.",
    "hi": "कोई बात नहीं, आगे बढ़ते हैं। आप इसे अगली स्क्रीन पर जोड़ सकते हैं।",
    "kn": "ಪರವಾಗಿಲ್ಲ, ಮುಂದುವರಿಯೋಣ. ಮುಂದಿನ ಪರದೆಯಲ್ಲಿ ಇದನ್ನು ಸೇರಿಸಬಹುದು.",
    "mr": "हरकत नाही, पुढे जाऊया. पुढच्या स्क्रीनवर हे जोडू शकता.",
    "ta": "பரவாயில்லை, அடுத்ததுக்குப் போகலாம். அடுத்த திரையில் இதைச் சேர்க்கலாம்.",
    "te": "ఫర్వాలేదు, ముందుకు వెళదాం. తర్వాతి స్క్రీన్‌లో దీన్ని జోడించవచ్చు.",
    "bn": "ঠিক আছে, এগিয়ে যাই। পরের স্ক্রিনে এটা যোগ করতে পারবেন।",
}

READY_TO_CONFIRM: dict[str, str] = {
    "en": "Thank you. Here is what I understood. Please check it and correct anything that is wrong.",
    "hi": "धन्यवाद। मैंने यह समझा है। कृपया देख लीजिए और कुछ ग़लत हो तो ठीक कर दीजिए।",
    "kn": "ಧನ್ಯವಾದಗಳು. ನಾನು ಅರ್ಥಮಾಡಿಕೊಂಡಿದ್ದು ಇದು. ದಯವಿಟ್ಟು ಪರಿಶೀಲಿಸಿ, ತಪ್ಪಿದ್ದರೆ ಸರಿಪಡಿಸಿ.",
    "mr": "धन्यवाद. मला हे समजले आहे. कृपया तपासा आणि काही चुकले असल्यास दुरुस्त करा.",
    "ta": "நன்றி. நான் புரிந்துகொண்டது இதுதான். சரிபார்த்து தவறு இருந்தால் திருத்துங்கள்.",
    "te": "ధన్యవాదాలు. నేను అర్థం చేసుకున్నది ఇదే. తనిఖీ చేసి తప్పు ఉంటే సరిచేయండి.",
    "bn": "ধন্যবাদ। আমি এটুকু বুঝেছি। দেখে নিন এবং ভুল থাকলে ঠিক করুন।",
}

ACKNOWLEDGEMENTS: dict[str, str] = {
    "en": "Got it.",
    "hi": "समझ गया।",
    "kn": "ಅರ್ಥವಾಯಿತು.",
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
    #: The beneficiary message this turn stored (or confirmed).
    message_id: str | None = None
    #: The language the assistant answered in.
    language: str = "en"
    #: Facts this turn added, as {slot, label} for the "+ Pump repair" chips.
    understood: list[dict[str, str]] = field(default_factory=list)
    #: Set when the answer was not understood and the engine asked again differently.
    clarification: bool = False
    #: Set when this is a stored result returned for a duplicate submission.
    replayed: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "assistant_message": self.assistant_message,
            "extraction": self.extraction.to_summary() if self.extraction else None,
            "draft": self.draft,
            "pending_slot": self.pending_slot.name if self.pending_slot else None,
            "needs_confirmation": self.needs_confirmation,
            "ready_to_confirm": self.ready_to_confirm,
            "transcript_for_correction": self.transcript_for_correction,
            "newly_filled": self.newly_filled,
            "progress": self.progress,
            "message_id": self.message_id,
            "language": self.language,
            "understood": self.understood,
            "clarification": self.clarification,
        }


@dataclass
class _ReplayedExtraction:
    """Stands in for an ExtractionResult when a stored turn is replayed."""

    summary: dict[str, Any] | None

    def to_summary(self) -> dict[str, Any] | None:
        return self.summary


def _from_snapshot(conversation: Conversation, data: dict[str, Any]) -> TurnResult:
    return TurnResult(
        conversation=conversation,
        assistant_message=data["assistant_message"],
        extraction=_ReplayedExtraction(data.get("extraction")) if data.get("extraction") else None,  # type: ignore[arg-type]
        draft=data.get("draft") or {},
        pending_slot=SLOTS_BY_NAME.get(data.get("pending_slot") or ""),
        needs_confirmation=data.get("needs_confirmation", False),
        ready_to_confirm=data.get("ready_to_confirm", False),
        transcript_for_correction=data.get("transcript_for_correction"),
        newly_filled=data.get("newly_filled", []),
        progress=data.get("progress", {}),
        message_id=data.get("message_id"),
        language=data.get("language", conversation.language),
        understood=data.get("understood", []),
        clarification=data.get("clarification", False),
        replayed=True,
    )


def _draft_from_profile(beneficiary: BeneficiaryProfile) -> dict[str, Any]:
    """A new draft that already knows what the stored profile knows about place.

    Location cannot come from speech, so a location already on the profile is
    carried in rather than asked for again.
    """
    draft = new_draft()
    location = beneficiary.primary_location
    if location is not None and location.latitude is not None and location.longitude is not None:
        draft["location"] = {
            "label": location.label,
            "village": location.village,
            "district": location.district,
            "state": location.state,
            "pincode": location.pincode,
            "latitude": location.latitude,
            "longitude": location.longitude,
            "source": "profile",
        }
    return draft


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
        draft_profile=_draft_from_profile(beneficiary),
        # The greeting asks about work, so the first answer is read as one.
        pending_slot="occupation",
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
    client_message_id: str | None = None,
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
        client_message_id=client_message_id,
    )
    db.add(message)
    db.flush()
    return message


def find_by_client_id(db: Session, conversation: Conversation, client_message_id: str) -> ConversationMessage | None:
    return db.execute(
        select(ConversationMessage).where(
            ConversationMessage.conversation_id == conversation.id,
            ConversationMessage.client_message_id == client_message_id,
        )
    ).scalar_one_or_none()


def replay(conversation: Conversation, message: ConversationMessage) -> TurnResult | None:
    """The stored result of an already-processed message, if it has one."""
    if not message.response_snapshot:
        return None
    return _from_snapshot(conversation, message.response_snapshot)


def next_slot(draft: dict[str, Any], asked: set[str]) -> SlotDefinition | None:
    """The highest-value slot that is unknown and not yet asked.

    Slots run in priority order (work, skills, experience, education, goal,
    travel, place). A slot is skipped when it is filled, when it was already
    asked once, or when its dependency is missing. Someone who said "I repair
    pumps" has told us their work, so they are not then asked what work they do.
    """
    filled = filled_slots_from_draft(draft)
    if "skills" in filled:
        filled.add("occupation")
    for slot in ordered_slots():
        if slot.name in filled or slot.name in asked or not slot.proactive:
            continue
        if slot.depends_on and slot.depends_on not in filled:
            continue
        return slot
    return None


def _topic_for(slot: SlotDefinition, draft: dict[str, Any]) -> str | None:
    """What the person already said, to make the next question specific."""
    if slot.name in {"experience", "skills"}:
        skills = [s for s in draft.get("skills", []) if not s.get("is_category")]
        if skills:
            return str(skills[0].get("name", "")).lower() or None
    return None


def _question(slot: SlotDefinition, language: str, draft: dict[str, Any]) -> str:
    return slot.question_for(language, topic=_topic_for(slot, draft))


def _clarification(slot: SlotDefinition | None, language: str) -> str:
    message = _localised(NOT_SURE, language)
    example = slot.example_for(language) if slot else None
    if example:
        message = f"{message} {_localised(EXAMPLE_PREFIX, language)} {example}"
    return message


def _last_question(conversation: Conversation) -> str | None:
    for message in reversed(conversation.messages):
        if message.role == "assistant":
            return message.raw_text
    return None


def _resolve_language(conversation: Conversation, extraction: ExtractionResult, hint: str | None) -> str:
    """Answer in the language the person is speaking when that is clear.

    The language chosen in the UI is the default; it is only overridden when
    the utterance is confidently in another language the assistant can speak.
    """
    current = hint or conversation.language
    detected = extraction.language
    if (
        detected
        and detected != current
        and detected in SPOKEN_LANGUAGES
        and extraction.language_confidence >= 0.7
    ):
        return detected
    return current if current in SPOKEN_LANGUAGES else "en"


def _scale_confidence(extraction: ExtractionResult, factor: float) -> None:
    """Lower the confidence of every fact from a doubtfully-heard transcript."""
    facts = [
        extraction.education, extraction.mobility, extraction.experience_years,
        extraction.max_travel_km, extraction.age, *extraction.occupations,
        *extraction.goals, *extraction.interests,
    ]
    for fact in facts:
        if fact is not None:
            fact.confidence = round(fact.confidence * factor, 3)
    for skill in extraction.skills:
        skill.confidence_score = round(skill.confidence_score * factor, 3)


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
    client_message_id: str | None = None,
    confirm_message_id: str | None = None,
) -> TurnResult:
    """Process one beneficiary turn."""
    started = time.perf_counter()
    channel = channel or conversation.channel
    text = text.strip()

    if client_message_id:
        existing = find_by_client_id(db, conversation, client_message_id)
        if existing is not None:
            replayed = replay(conversation, existing)
            if replayed is not None:
                logger.info(
                    "[Conversation] duplicate conversation_id=%s message_id=%s -> replayed stored result",
                    conversation.id, client_message_id,
                )
                return replayed

    # Deep copy: the draft is nested, and mutating the loaded value in place
    # would leave SQLAlchemy unable to tell the column changed.
    slots_state: dict[str, Any] = deepcopy(dict(conversation.slots or {}))
    asked: set[str] = set(slots_state.get("_asked", []))
    misses: dict[str, int] = dict(slots_state.get("_misses", {}))
    draft: dict[str, Any] = deepcopy({**new_draft(), **dict(conversation.draft_profile or {})})
    pending = SLOTS_BY_NAME.get(conversation.pending_slot or "")
    question_asked = _last_question(conversation)

    detection = detect_language(text, language_hint or conversation.language)
    normalized = normalize_text(text)

    # A transcript the person confirmed after a low-confidence turn is reused,
    # not stored a second time.
    confirming: ConversationMessage | None = None
    if confirm_message_id:
        candidate = db.get(ConversationMessage, confirm_message_id)
        if (
            candidate is not None
            and candidate.conversation_id == conversation.id
            and candidate.role == "beneficiary"
            and candidate.needs_confirmation
        ):
            confirming = candidate

    # --- low ASR confidence: confirm before committing anything -------------
    if (
        confirming is None
        and asr_confidence is not None
        and asr_confidence < settings.asr_confidence_threshold
    ):
        language = conversation.language
        user_message = _append_message(
            db, conversation, role="beneficiary", raw_text=text, normalized_text=normalized,
            channel=channel, detected_language=detection.language,
            language_confidence=detection.confidence, asr_confidence=asr_confidence,
            is_code_switched=detection.is_code_switched, speech_provider=speech_provider,
            needs_confirmation=True, audio_reference=audio_reference,
            client_message_id=client_message_id,
        )
        prompt = _localised(LOW_CONFIDENCE_PROMPTS, language)
        _append_message(
            db, conversation, role="assistant", raw_text=prompt, channel=channel,
            detected_language=language, needs_confirmation=True,
        )
        result = TurnResult(
            conversation=conversation,
            assistant_message=prompt,
            extraction=None,
            draft=draft,
            pending_slot=pending,
            needs_confirmation=True,
            transcript_for_correction=text,
            progress=_progress(draft),
            message_id=user_message.id,
            language=language,
        )
        user_message.response_snapshot = result.snapshot()
        db.commit()
        db.refresh(conversation)
        _log_turn(conversation, client_message_id, text, asr_confidence, detection.language, None, result, started)
        return result

    # --- understanding ------------------------------------------------------
    context = ExtractionContext(
        pending_slot=pending.name if pending else None,
        question=question_asked,
        draft=draft,
        asr_confidence=asr_confidence,
    )
    extraction = get_profile_extractor().extract(
        db, text, language_hint or conversation.language, context=context
    )
    if asr_confidence is not None and asr_confidence < settings.asr_moderate_confidence:
        _scale_confidence(extraction, max(asr_confidence, 0.5))

    before_draft = deepcopy(draft)
    before = filled_slots_from_draft(draft)
    # A tapped choice answers its slot directly; the free text is still parsed
    # so an unprompted extra fact in the same turn is not lost.
    if slot_answer and pending:
        draft = _apply_slot_answer(draft, pending.name, slot_answer)
    draft = merge_extraction(draft, extraction)
    after = filled_slots_from_draft(draft)
    newly_filled = sorted(after - before)
    understood = describe_new_facts(before_draft, draft)

    language = _resolve_language(conversation, extraction, language_hint)
    conversation.language = language

    if confirming is not None:
        user_message = confirming
        user_message.needs_confirmation = False
        user_message.raw_text = text
        user_message.normalized_text = extraction.normalized_text or normalized
        user_message.extracted_entities = extraction.to_summary()
        if client_message_id and user_message.client_message_id is None:
            user_message.client_message_id = client_message_id
    else:
        user_message = _append_message(
            db, conversation, role="beneficiary", raw_text=text,
            normalized_text=extraction.normalized_text or normalized, channel=channel,
            detected_language=extraction.language, language_confidence=extraction.language_confidence,
            asr_confidence=asr_confidence, is_code_switched=extraction.is_code_switched,
            speech_provider=speech_provider, extracted_entities=extraction.to_summary(),
            audio_reference=audio_reference, client_message_id=client_message_id,
        )

    # --- decide what to say next -----------------------------------------------
    clarification = False
    prefix = ""
    answered_pending = pending is None or pending.name in after or (
        pending.name == "occupation" and "skills" in after
    )
    if pending is not None and not answered_pending:
        if understood or newly_filled:
            # The beneficiary shared other relevant information (e.g., skills, goal, education).
            # We acknowledge their input and advance to the next unfilled slot rather than looping.
            asked.add(pending.name)
            clarification = False
        else:
            misses[pending.name] = misses.get(pending.name, 0) + 1
            if misses[pending.name] <= settings.max_clarifications_per_slot:
                # Ask once with a rephrased example, never an infinite loop.
                clarification = True
            else:
                asked.add(pending.name)
                prefix = _localised(MOVE_ON, language) if not understood else ""
    elif pending is not None:
        asked.add(pending.name)

    if clarification:
        upcoming: SlotDefinition | None = pending
        acknowledgement = _localised(ACKNOWLEDGEMENTS, language) if understood else ""
        body = _clarification(pending, language) if not understood else _question(pending, language, draft)
        if understood and pending.example_for(language):
            body = f"{body} {_localised(EXAMPLE_PREFIX, language)} {pending.example_for(language)}"
        assistant_message = f"{acknowledgement} {body}".strip()
        ready = False
    else:
        upcoming = next_slot(draft, asked)
        if upcoming is None:
            assistant_message = _localised(READY_TO_CONFIRM, language)
            ready = True
        else:
            acknowledgement = _localised(ACKNOWLEDGEMENTS, language) if understood else prefix
            assistant_message = f"{acknowledgement} {_question(upcoming, language, draft)}".strip()
            ready = False

    conversation.pending_slot = upcoming.name if upcoming else None
    conversation.state = "awaiting_confirmation" if ready else "active"
    slots_state["_asked"] = sorted(asked)
    slots_state["_misses"] = misses
    slots_state.update({name: True for name in after})
    conversation.slots = slots_state
    conversation.draft_profile = draft

    _append_message(
        db, conversation, role="assistant", raw_text=assistant_message, channel=channel,
        detected_language=language,
    )
    result = TurnResult(
        conversation=conversation,
        assistant_message=assistant_message,
        extraction=extraction,
        draft=draft,
        pending_slot=upcoming,
        ready_to_confirm=ready,
        newly_filled=newly_filled,
        progress=_progress(draft),
        message_id=user_message.id,
        language=language,
        understood=understood,
        clarification=clarification,
    )
    user_message.response_snapshot = result.snapshot()
    db.commit()
    db.refresh(conversation)
    _log_turn(conversation, client_message_id, text, asr_confidence, extraction.language, extraction, result, started)
    return result


def _log_turn(conversation, client_message_id, text, asr_confidence, language, extraction, result, started) -> None:
    """One structured line per turn. Transcripts only outside production."""
    if settings.environment == "production" and not settings.debug:
        return
    logger.info(
        "[Conversation] conversation_id=%s message_id=%s language=%s asr_confidence=%s "
        "extractor=%s transcript=%r profile_delta=%s merged=%s next_slot=%s state=%s "
        "clarification=%s next_question=%r latency_ms=%d",
        conversation.id,
        client_message_id,
        language,
        asr_confidence,
        extraction.extractor if extraction else "-",
        text[:200],
        [u["label"] for u in result.understood],
        sorted(filled_slots_from_draft(result.draft)),
        result.pending_slot.name if result.pending_slot else None,
        conversation.state,
        result.clarification,
        result.assistant_message[:160],
        int((time.perf_counter() - started) * 1000),
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


__all__ = [
    "TurnResult",
    "find_by_client_id",
    "handle_message",
    "mark_confirmed",
    "next_slot",
    "progress_for",
    "replay",
    "resume",
    "start_conversation",
]
