"""Phase 1 and 2: language identification, extraction and skill normalisation."""

from __future__ import annotations

import pytest

from app.core.enums import EducationLevel, GoalType, Mobility, Proficiency, VerificationStatus
from app.services.language_id import detect_language, extract_number, normalize_text
from app.services.profile_extraction import RuleBasedExtractor
from app.services.skill_normalization import (
    build_alias_index,
    match_skills_in_text,
    normalize_label,
    stem,
)

RAVI_UTTERANCE = (
    "I work in agriculture and I repair pumps sometimes. I want to earn more. "
    "I like mechanical work but I cannot travel very far."
)


class TestLanguageIdentification:
    def test_detects_english(self):
        result = detect_language("I work in agriculture and repair pumps")
        assert result.language == "en"
        assert result.confidence > 0.5
        assert not result.is_code_switched

    def test_detects_hindi_devanagari(self):
        result = detect_language("मैं खेती का काम करता हूँ और पंप ठीक करता हूँ")
        assert result.language == "hi"
        assert result.confidence > 0.6

    def test_distinguishes_marathi_from_hindi(self):
        result = detect_language("मी शेती करतो आणि मला मशीनचे काम आवडते आहे")
        assert result.language == "mr", result.detail

    def test_detects_tamil(self):
        assert detect_language("நான் விவசாயம் செய்கிறேன்").language == "ta"

    def test_flags_code_switching(self):
        result = detect_language("मुझे mechanical work पसंद है और मैं pump repair करता हूँ")
        assert result.is_code_switched is True

    def test_romanised_hindi_is_flagged(self):
        result = detect_language("mujhe zyada kamana hai lekin main door nahi ja sakta")
        assert result.language == "hi"
        assert result.is_code_switched is True

    def test_empty_input_reports_zero_confidence(self):
        assert detect_language("").confidence == 0.0

    def test_normalize_maps_indic_digits(self):
        assert "5" in normalize_text("मुझे ५ साल का अनुभव है")

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("5 years", 5.0), ("do saal", 2.0), ("दो साल", 2.0), ("ten", 10.0)],
    )
    def test_extract_number(self, text, expected):
        assert extract_number(text) == expected


class TestStemming:
    @pytest.mark.parametrize(
        ("word", "expected"),
        [
            ("pumps", "pump"),
            ("repairing", "repair"),
            ("machines", "machine"),
            ("pass", "pass"),
            ("business", "business"),
            ("पंप", "पंप"),
        ],
    )
    def test_stem(self, word, expected):
        assert stem(word) == expected


class TestSkillNormalization:
    def test_matches_reversed_word_order(self, db):
        """'I repair pumps' must reach the same node as 'pump repair'."""
        codes = {m.code for m in match_skills_in_text(db, "I repair pumps sometimes")}
        assert "pump_repair" in codes

    def test_matches_plural_and_gerund(self, db):
        codes = {m.code for m in match_skills_in_text(db, "I have been repairing pumps")}
        assert "pump_repair" in codes

    def test_two_skills_can_share_one_verb(self, db):
        codes = {m.code for m in match_skills_in_text(db, "I repair pumps and farm machinery")}
        assert "pump_repair" in codes
        assert "farm_machinery_maintenance" in codes

    def test_leaf_skill_beats_its_category(self, db):
        codes = {m.code for m in match_skills_in_text(db, "I do farm machinery repair")}
        assert "farm_machinery_maintenance" in codes
        assert "farm_machinery" not in codes

    def test_matches_hindi_alias(self, db):
        codes = {m.code for m in match_skills_in_text(db, "मैं पंप मरम्मत करता हूँ")}
        assert "pump_repair" in codes

    def test_unrelated_text_matches_nothing(self, db):
        assert match_skills_in_text(db, "the weather is very hot today") == []

    def test_no_false_match_across_distant_words(self, db):
        """'pump' and 'repair' far apart must not be joined into pump repair."""
        text = "I repair tractors every day and there is an old pump lying in the field somewhere"
        codes = {m.code for m in match_skills_in_text(db, text)}
        assert "pump_repair" not in codes

    def test_normalize_label_prefers_leaf(self, db):
        match = normalize_label(db, "farm machinery maintenance")
        assert match is not None
        assert match.code == "farm_machinery_maintenance"

    def test_alias_index_is_ordered_most_specific_first(self, db):
        index = build_alias_index(db)
        token_counts = [len(e.tokens) for e in index]
        assert token_counts == sorted(token_counts, reverse=True)


class TestProfileExtraction:
    @pytest.fixture
    def extraction(self, db):
        return RuleBasedExtractor().extract(db, RAVI_UTTERANCE)

    def test_extracts_occupation(self, extraction):
        assert any("Agriculture" in str(o.value) for o in extraction.occupations)

    def test_extracts_pump_repair_skill(self, extraction):
        assert "pump_repair" in {s.code for s in extraction.skills}

    def test_extracts_mechanical_interest(self, extraction):
        assert "mechanical" in {i.value for i in extraction.interests}

    def test_extracts_low_mobility(self, extraction):
        assert extraction.mobility is not None
        assert extraction.mobility.value == Mobility.LOW

    def test_extracts_higher_income_goal(self, extraction):
        assert GoalType.HIGHER_INCOME in {g.value for g in extraction.goals}

    def test_every_fact_carries_evidence(self, extraction):
        assert extraction.mobility.evidence
        assert all(s.evidence for s in extraction.skills)

    def test_skills_are_self_declared_not_verified(self, extraction):
        """A spoken claim must never be recorded as verified."""
        assert all(
            s.verification_status == VerificationStatus.SELF_DECLARED for s in extraction.skills
        )

    def test_occasional_work_stays_basic_proficiency(self, extraction):
        pump = next(s for s in extraction.skills if s.code == "pump_repair")
        assert pump.proficiency == Proficiency.BASIC

    def test_years_raise_proficiency(self, db):
        result = RuleBasedExtractor().extract(
            db, "I have been repairing pumps for about 5 years"
        )
        pump = next(s for s in result.skills if s.code == "pump_repair")
        assert pump.proficiency == Proficiency.INTERMEDIATE
        assert pump.years_experience == 5

    def test_extracts_education(self, db):
        result = RuleBasedExtractor().extract(db, "I am 10th pass and I work on a farm")
        assert result.education is not None
        assert result.education.value == EducationLevel.CLASS_10

    def test_extracts_self_employment_goal(self, db):
        result = RuleBasedExtractor().extract(
            db, "I would prefer to start my own work rather than a job"
        )
        assert GoalType.SELF_EMPLOYMENT in {g.value for g in result.goals}

    def test_extracts_from_hindi(self, db):
        result = RuleBasedExtractor().extract(
            db,
            "मैं खेती का काम करता हूँ और कभी कभी पंप ठीक करता हूँ। मुझे ज्यादा कमाना है। "
            "मुझे मशीन का काम पसंद है लेकिन मैं दूर नहीं जा सकता।",
        )
        assert result.language == "hi"
        assert "pump_repair" in {s.code for s in result.skills}
        assert result.mobility.value == Mobility.LOW
        assert GoalType.HIGHER_INCOME in {g.value for g in result.goals}

    def test_extracts_travel_constraint(self, extraction):
        assert any(kind == "travel" for kind, _ in extraction.constraints)

    def test_extracts_pincode(self, db):
        result = RuleBasedExtractor().extract(db, "My village pincode is 422103")
        assert result.pincode is not None
        assert result.pincode.value == "422103"

    def test_nothing_invented_from_empty_text(self, db):
        result = RuleBasedExtractor().extract(db, "   ")
        assert result.education is None
        assert result.skills == []
        assert result.goals == []
