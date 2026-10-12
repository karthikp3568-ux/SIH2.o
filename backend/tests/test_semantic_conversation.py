"""Multilingual semantic understanding and the stateful conversation.

These run against the real offline encoder (LaBSE), the same path a
beneficiary's speech takes when no LLM key is configured. They are skipped
only when the model cannot be loaded on this machine.
"""

from __future__ import annotations

import uuid

import pytest

from conftest import auth

from app.services import semantic_understanding as semantic
from app.services.conversation_engine import next_slot
from app.services.profile_extraction import SemanticExtractor
from app.services.profile_service import merge_extraction, new_draft
from app.services.semantic_understanding import ExtractionContext, LLMSemanticExtractor

pytestmark = pytest.mark.skipif(
    not semantic.semantic_model_available(), reason="multilingual sentence encoder not available"
)

KANNADA = range(0x0C80, 0x0D00)


def _extract(db, text: str, slot: str | None = None):
    return SemanticExtractor().extract(db, text, None, ExtractionContext(pending_slot=slot))


def _skill_codes(result) -> set[str]:
    return {s.code for s in result.skills if not s.is_category}


# ---------------------------------------------------------------------------
# Extraction: the exact demo cases, in each language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "ನಾನು ಕೃಷಿ ಕೆಲಸ ಮಾಡುತ್ತೇನೆ ಮತ್ತು ಪಂಪ್ ರಿಪೇರಿ ಮಾಡುತ್ತೇನೆ.",  # A - Kannada
        "मैं खेती करता हूं और मोटर पंप ठीक कर लेता हूं।",  # B - Hindi
        "I work on my farm and repair irrigation pumps.",  # C - English
        "ನಾನು agriculture ಮಾಡ್ತೀನಿ, pumps repair ಮಾಡ್ತೀನಿ.",  # D - code-switched
    ],
    ids=["A-kannada", "B-hindi", "C-english", "D-code-switch"],
)
def test_occupation_and_skill_in_every_language(db, text):
    result = _extract(db, text)
    assert [o.value for o in result.occupations] == ["Agriculture / farm work"]
    assert "pump_repair" in _skill_codes(result)


def test_case_e_goal_in_kannada_with_english_word(db):
    result = _extract(db, "ನನಗೆ ನನ್ನದೇ business ಶುರು ಮಾಡಬೇಕು.")
    assert [g.value for g in result.goals] == ["self_employment"]
    assert not result.skills and not result.occupations


def test_case_f_mobility_in_kannada(db):
    result = _extract(db, "ನಾನು ತುಂಬಾ ದೂರ ಹೋಗಲು ಆಗುವುದಿಲ್ಲ.")
    assert result.mobility is not None and result.mobility.value == "low"


@pytest.mark.parametrize(
    "text", ["I completed 10th standard.", "मैंने दसवीं पास की है", "ನಾನು ಹತ್ತನೇ ತರಗತಿ ಓದಿದ್ದೇನೆ"]
)
def test_case_g_education(db, text):
    result = _extract(db, text)
    assert result.education is not None and result.education.value == "class_10"


def test_short_answers_are_read_against_the_question(db):
    assert _extract(db, "No.", slot="mobility").mobility.value == "low"
    several = _extract(db, "For several years.", slot="experience").experience_years
    # A qualitative answer is kept as said; no number is invented for it.
    assert several.value is None and several.label == "Several years"
    assert _extract(db, "ಐದು ವರ್ಷಗಳಿಂದ", slot="experience").experience_years.value == 5


def test_desired_skill_is_not_recorded_as_a_current_skill(db):
    result = _extract(db, "I want to learn welding")
    assert "welding" not in _skill_codes(result)
    assert "welding" in {i.value for i in result.interests}


def test_past_occupation_is_not_current(db):
    result = _extract(db, "ನಾನು ಮೊದಲು ಕೃಷಿ ಮಾಡುತ್ತಿದ್ದೆ, ಈಗ ಮೆಕ್ಯಾನಿಕ್ ಕೆಲಸ ಮಾಡುತ್ತೇನೆ.")
    assert [o.value for o in result.occupations] == ["Machinery repair / mechanic"]
    assert [o.value for o in result.previous_occupations] == ["Agriculture / farm work"]


@pytest.mark.parametrize("text", ["hello", "what?", "okay"])
def test_nothing_is_invented_from_small_talk(db, text):
    result = _extract(db, text)
    assert not (result.occupations or result.skills or result.goals or result.education or result.mobility)


# ---------------------------------------------------------------------------
# Merging and slot selection
# ---------------------------------------------------------------------------


def test_case_h_profile_merges_across_turns(db):
    draft = new_draft()
    for text in ("I work in agriculture.", "I repair pumps.", "I want my own business."):
        draft = merge_extraction(draft, _extract(db, text))
    assert [o["value"] for o in draft["occupations"]] == ["Agriculture / farm work"]
    assert "pump_repair" in {s["code"] for s in draft["skills"]}
    assert [g["value"] for g in draft["goals"]] == ["self_employment"]


def test_later_turn_never_erases_known_facts(db):
    draft = merge_extraction(new_draft(), _extract(db, "I work in agriculture and repair pumps."))
    draft = merge_extraction(draft, _extract(db, "hello"))
    assert draft["occupations"] and draft["skills"]


def test_stopping_work_moves_it_to_previous(db):
    draft = merge_extraction(new_draft(), _extract(db, "I work in agriculture."))
    draft = merge_extraction(draft, _extract(db, "ನಾನು ಮೊದಲು ಕೃಷಿ ಮಾಡುತ್ತಿದ್ದೆ, ಈಗ ಮೆಕ್ಯಾನಿಕ್ ಕೆಲಸ ಮಾಡುತ್ತೇನೆ."))
    assert [o["value"] for o in draft["occupations"]] == ["Machinery repair / mechanic"]
    assert [o["value"] for o in draft["previous_occupations"]] == ["Agriculture / farm work"]


def test_missing_slot_detection_follows_what_is_known(db):
    draft = new_draft()
    assert next_slot(draft, set()).name == "occupation"
    draft = merge_extraction(draft, _extract(db, "I repair pumps."))
    # "I repair pumps" already says what work they do: don't ask that again.
    assert next_slot(draft, set()).name == "experience"
    draft = merge_extraction(draft, _extract(db, "For five years", slot="experience"))
    assert next_slot(draft, set()).name == "education"


# ---------------------------------------------------------------------------
# The conversation API
# ---------------------------------------------------------------------------


@pytest.fixture
def conversation_id(client, beneficiary_token) -> str:
    response = client.post(
        "/api/conversation/start",
        headers=auth(beneficiary_token),
        json={"language": "en", "resume": False},
    )
    assert response.status_code == 200, response.text
    return response.json()["conversation"]["id"]


def _say(client, token, conversation_id, text, **extra):
    response = client.post(
        f"/api/conversation/{conversation_id}/message",
        headers=auth(token),
        json={"text": text, "client_message_id": uuid.uuid4().hex, **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _beneficiary_messages(client, token, conversation_id) -> list[dict]:
    body = client.get(f"/api/conversation/{conversation_id}", headers=auth(token)).json()
    return [m for m in body["messages"] if m["role"] == "beneficiary"]


def test_contextual_follow_up(client, beneficiary_token, conversation_id):
    body = _say(client, beneficiary_token, conversation_id, "I repair pumps.")
    assert body["next_slot"] == "experience"
    assert body["next_question"].endswith("How long have you been doing pump repair?")
    assert {"slot": "skills", "label": "Pump repair"} in body["profile_update"]


def test_kannada_answer_gets_a_kannada_question(client, beneficiary_token, conversation_id):
    body = _say(
        client, beneficiary_token, conversation_id,
        "ನಾನು ಕೃಷಿ ಕೆಲಸ ಮಾಡುತ್ತೇನೆ ಮತ್ತು ಪಂಪ್ ರಿಪೇರಿ ಮಾಡುತ್ತೇನೆ.", language="kn",
    )
    assert body["language"] == "kn"
    assert any(ord(ch) in KANNADA for ch in body["next_question"])
    assert body["next_slot"] != "occupation"
    labels = {u["label"] for u in body["profile_update"]}
    assert {"Agriculture", "Pump repair"} <= labels


def test_no_repeated_fallback(client, beneficiary_token, conversation_id):
    first = _say(client, beneficiary_token, conversation_id, "hello")
    assert first["clarification"] is True
    assert first["next_slot"] == "occupation"
    assert "For example" in first["next_question"]
    second = _say(client, beneficiary_token, conversation_id, "hmm, okay")
    # After one rephrase the engine moves on rather than asking again.
    assert second["clarification"] is False
    assert second["next_slot"] != "occupation"
    assert second["next_question"] != first["next_question"]
    for body in (first, second):
        assert "could not pick out" not in body["next_question"]


def test_duplicate_message_is_processed_once(client, beneficiary_token, conversation_id):
    message_id = uuid.uuid4().hex
    payload = {"text": "I work in agriculture and repair pumps.", "client_message_id": message_id}
    url = f"/api/conversation/{conversation_id}/message"
    first = client.post(url, headers=auth(beneficiary_token), json=payload).json()
    second = client.post(url, headers=auth(beneficiary_token), json=payload).json()
    assert first["replayed"] is False and second["replayed"] is True
    assert second["message_id"] == first["message_id"]
    assert second["next_question"] == first["next_question"]
    assert len(_beneficiary_messages(client, beneficiary_token, conversation_id)) == 1


def test_low_asr_confidence_is_confirmed_once(client, beneficiary_token, conversation_id):
    doubtful = _say(
        client, beneficiary_token, conversation_id, "I repair pumps", asr_confidence=0.4, speech_provider="mock"
    )
    assert doubtful["needs_confirmation"] is True
    assert doubtful["draft_profile"]["skills"] == []
    confirmed = _say(
        client, beneficiary_token, conversation_id, "I repair pumps", confirm_message_id=doubtful["message_id"]
    )
    assert "pump_repair" in {s["code"] for s in confirmed["draft_profile"]["skills"]}
    # Confirming re-used the stored message instead of adding a second copy.
    messages = _beneficiary_messages(client, beneficiary_token, conversation_id)
    assert len(messages) == 1 and messages[0]["needs_confirmation"] is False


def test_conversation_persists_and_resumes(client, beneficiary_token, conversation_id):
    _say(client, beneficiary_token, conversation_id, "I work in agriculture and repair pumps.")
    body = client.get(f"/api/conversation/{conversation_id}", headers=auth(beneficiary_token)).json()
    assert body["draft_profile"]["occupations"]
    assert body["pending_slot"]["name"] == "experience"
    resumed = client.post(
        "/api/conversation/start", headers=auth(beneficiary_token), json={"language": "en", "resume": True}
    ).json()
    assert resumed["conversation"]["id"] == conversation_id


# ---------------------------------------------------------------------------
# End to end: the Ravi demo, voice transcript -> profile -> pathways
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script_key", ["english", "hindi", "kannada"])
def test_ravi_demo_reaches_confirmation_and_pathways(client, script_key):
    reset = client.post("/api/demo/ravi/reset").json()
    token, conversation_id = reset["tokens"]["access_token"], reset["conversation_id"]
    script = client.get("/api/demo/script").json()[script_key]
    language = script[0]["language"]

    asked = []
    body = None
    for line in script:
        body = _say(client, token, conversation_id, line["text"], language=language, asr_confidence=0.9)
        asked.append(body["next_slot"])
        assert body["clarification"] is False, (line["text"], body["next_question"])
    assert body["ready_to_confirm"] is True
    # Every question asked was a different one.
    asked_slots = [s for s in asked if s]
    assert len(asked_slots) == len(set(asked_slots))

    draft = body["draft_profile"]
    assert [o["value"] for o in draft["occupations"]] == ["Agriculture / farm work"]
    assert "pump_repair" in {s["code"] for s in draft["skills"]}
    assert draft["education"]["value"] == "class_10"
    assert [g["value"] for g in draft["goals"]] == ["self_employment"]
    assert draft["mobility"]["value"] == "low"
    assert draft["experience_years"]

    confirmed = client.post(
        f"/api/conversation/{conversation_id}/confirm", headers=auth(token), json={}
    ).json()
    assert confirmed["recommendations_generated"] is True
    assert "pump_repair" in {s["code"] for s in confirmed["profile"]["skills"]}


# ---------------------------------------------------------------------------
# LLM path (no network: the model call is replaced, the validation is real)
# ---------------------------------------------------------------------------


def test_llm_payload_is_validated_against_the_closed_vocabulary(db):
    payload = {
        "understood": True,
        "language": "kn",
        "education": "class_10",
        "current_occupation": {"category": "Agriculture / farm work", "description_en": "farming"},
        "previous_occupation": None,
        "skills": [
            {"phrase_en": "water pump repair", "status": "current"},
            {"phrase_en": "rocket engineering", "status": "current"},  # not in taxonomy
            {"phrase_en": "welding", "status": "desired"},
        ],
        "experience": {"years": None, "description_en": "several years"},
        "interests": ["mechanical"],
        "goal": "self_employment",
        "mobility": "low",
        "max_travel_km": None,
        "confidence": {k: 0.9 for k in ("education", "occupation", "skills", "experience", "goal", "mobility", "interests")},
    }
    result = LLMSemanticExtractor().to_result(db, "ನಾನು ...", "kn", payload)
    assert _skill_codes(result) == {"pump_repair"}  # invented skill dropped, desired one not current
    assert "welding" in {i.value for i in result.interests}
    assert result.education.value == "class_10"
    assert result.goals[0].value == "self_employment"
    assert result.experience_years.value is None and result.experience_years.label == "several years"


def test_llm_is_used_first_and_failure_falls_back_offline(db, monkeypatch):
    monkeypatch.setattr(LLMSemanticExtractor, "available", lambda self: True)
    monkeypatch.setattr(LLMSemanticExtractor, "call", lambda self, text, context: None)  # outage
    result = SemanticExtractor().extract(db, "ನಾನು ಕೃಷಿ ಕೆಲಸ ಮಾಡುತ್ತೇನೆ ಮತ್ತು ಪಂಪ್ ರಿಪೇರಿ ಮಾಡುತ್ತೇನೆ.", "kn")
    assert result.extractor.startswith("semantic_embedding")
    assert "pump_repair" in _skill_codes(result)
