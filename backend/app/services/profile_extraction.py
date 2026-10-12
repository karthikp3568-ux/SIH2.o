"""Phase 2 - turn an utterance into structured beneficiary facts.

Extractors:

* `SemanticExtractor` (default) - multilingual meaning, not keywords. Claude
  when an API key is configured, otherwise an offline multilingual sentence
  encoder (see `semantic_understanding`). Both use a closed vocabulary.
* `RuleBasedExtractor` - deterministic lexicon + taxonomy matching. Within the
  semantic pipeline it supplies only exact numbers, PIN codes and districts, and
  is the last resort when no semantic layer is available.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.enums import Mobility
from ..models import Opportunity
from .language_id import detect_language, extract_number, normalize_text
from .lexicon import (
    CONSTRAINT_PHRASES,
    EDUCATION_PHRASES,
    GOAL_PHRASES,
    INTEREST_PHRASES,
    MOBILITY_PHRASES,
    OCCUPATION_PHRASES,
    YEAR_UNITS,
)
from .skill_normalization import SkillMatch, build_alias_index, match_skills_in_text


@dataclass
class ExtractedFact:
    """One extracted value plus the evidence that produced it."""

    value: str | float | int | None
    confidence: float
    evidence: str
    extractor: str = "rule_based"
    #: Human wording kept when the value alone would lose meaning
    #: ("Several years" has no exact number, and none is invented).
    label: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionResult:
    language: str = "en"
    language_confidence: float = 0.0
    is_code_switched: bool = False
    normalized_text: str = ""
    #: Which understanding layer(s) produced this result, for logs and audit.
    extractor: str = "rule_based"

    education: ExtractedFact | None = None
    occupations: list[ExtractedFact] = field(default_factory=list)
    #: Work the person said they used to do and stopped.
    previous_occupations: list[ExtractedFact] = field(default_factory=list)
    skills: list[SkillMatch] = field(default_factory=list)
    interests: list[ExtractedFact] = field(default_factory=list)
    goals: list[ExtractedFact] = field(default_factory=list)
    constraints: list[tuple[str, ExtractedFact]] = field(default_factory=list)
    mobility: ExtractedFact | None = None
    max_travel_km: ExtractedFact | None = None
    experience_years: ExtractedFact | None = None
    age: ExtractedFact | None = None
    target_income: ExtractedFact | None = None
    pincode: ExtractedFact | None = None
    district: ExtractedFact | None = None
    state: ExtractedFact | None = None

    #: Fields the extractor is confident enough to commit without asking.
    def filled_slots(self) -> set[str]:
        filled: set[str] = set()
        if self.education:
            filled.add("education")
        if self.occupations:
            filled.add("occupation")
        if self.skills:
            filled.add("skills")
        if self.interests:
            filled.add("interests")
        if self.goals:
            filled.add("goal")
        if self.mobility:
            filled.add("mobility")
        if self.experience_years:
            filled.add("experience")
        if self.pincode or self.district:
            filled.add("location")
        return filled

    def to_summary(self) -> dict:
        """Compact JSON view used for the confirmation screen and audit."""
        return {
            "language": self.language,
            "language_confidence": self.language_confidence,
            "is_code_switched": self.is_code_switched,
            "extractor": self.extractor,
            "education": self.education.as_dict() if self.education else None,
            "occupations": [o.as_dict() for o in self.occupations],
            "previous_occupations": [o.as_dict() for o in self.previous_occupations],
            "skills": [
                {
                    "code": s.code,
                    "name": s.name,
                    "raw_label": s.raw_label,
                    "proficiency": s.proficiency,
                    "confidence": s.confidence,
                    "source": s.source,
                    "verification_status": s.verification_status,
                    "years_experience": s.years_experience,
                    "evidence": s.evidence,
                    "is_category": s.is_category,
                }
                for s in self.skills
            ],
            "interests": [i.as_dict() for i in self.interests],
            "goals": [g.as_dict() for g in self.goals],
            "constraints": [{"kind": k, **f.as_dict()} for k, f in self.constraints],
            "mobility": self.mobility.as_dict() if self.mobility else None,
            "max_travel_km": self.max_travel_km.as_dict() if self.max_travel_km else None,
            "experience_years": self.experience_years.as_dict() if self.experience_years else None,
            "age": self.age.as_dict() if self.age else None,
            "target_income": self.target_income.as_dict() if self.target_income else None,
            "location": {
                "pincode": self.pincode.as_dict() if self.pincode else None,
                "district": self.district.as_dict() if self.district else None,
                "state": self.state.as_dict() if self.state else None,
            },
        }


_PINCODE_RE = re.compile(r"\b([1-9]\d{5})\b")
_AGE_RE = re.compile(r"\b(?:age|umar|उम्र|वय|வயது)\D{0,10}(\d{1,2})\b")
_AGE_ALT_RE = re.compile(r"\b(\d{1,2})\s*(?:years old|year old|saal ka|साल का|वर्षांचा)")
_KM_RE = re.compile(r"\b(\d{1,3})\s*(?:km|kilometer|kilometre|किमी|किलोमीटर|கி மீ)")
_INCOME_RE = re.compile(
    r"\b(\d{3,7})\s*(?:rupees|rs|inr|रुपये|रुपए|ரூபாய்)|(?:rupees|rs|inr|रुपये|ரூபாய்)\s*(\d{3,7})"
)


def _first_phrase_hit(normalized: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        candidate = normalize_text(phrase)
        if candidate and candidate in normalized:
            return phrase
    return None


class RuleBasedExtractor:
    """Deterministic extractor. Offline, auditable, never fabricates."""

    name = "rule_based"

    def extract(
        self, db: Session, text: str, language_hint: str | None = None, context=None
    ) -> ExtractionResult:
        detection = detect_language(text, language_hint)
        normalized = normalize_text(text)
        result = ExtractionResult(
            language=detection.language,
            language_confidence=detection.confidence,
            is_code_switched=detection.is_code_switched,
            normalized_text=normalized,
        )
        if not normalized:
            return result

        self._extract_education(normalized, result)
        self._extract_occupation(normalized, result)
        self._extract_mobility(normalized, result)
        self._extract_goals(normalized, result)
        self._extract_interests(normalized, result)
        self._extract_constraints(normalized, result)
        self._extract_numbers(normalized, result)
        self._extract_location(db, normalized, result)

        result.skills = match_skills_in_text(db, text, build_alias_index(db))
        return result

    # -- individual field extractors ---------------------------------------

    def _extract_education(self, normalized: str, result: ExtractionResult) -> None:
        for level, phrases in EDUCATION_PHRASES:
            hit = _first_phrase_hit(normalized, phrases)
            if hit:
                result.education = ExtractedFact(
                    value=str(level),
                    confidence=0.85,
                    evidence=f"Heard '{hit}'",
                )
                return

    def _extract_occupation(self, normalized: str, result: ExtractionResult) -> None:
        for title, sector, phrases in OCCUPATION_PHRASES:
            hit = _first_phrase_hit(normalized, phrases)
            if hit:
                result.occupations.append(
                    ExtractedFact(
                        value=title,
                        confidence=0.8,
                        evidence=f"Heard '{hit}'" + (f" (sector: {sector})" if sector else ""),
                    )
                )

    def _extract_mobility(self, normalized: str, result: ExtractionResult) -> None:
        # Check LOW and HIGH before MEDIUM: they are the explicit statements,
        # while MEDIUM cues are vaguer and would otherwise shadow them.
        for band in (Mobility.LOW, Mobility.HIGH, Mobility.MEDIUM):
            hit = _first_phrase_hit(normalized, MOBILITY_PHRASES[band])
            if hit:
                result.mobility = ExtractedFact(
                    value=str(band), confidence=0.85, evidence=f"Heard '{hit}'"
                )
                return

    def _extract_goals(self, normalized: str, result: ExtractionResult) -> None:
        for goal, phrases in GOAL_PHRASES.items():
            hit = _first_phrase_hit(normalized, phrases)
            if hit:
                result.goals.append(
                    ExtractedFact(value=str(goal), confidence=0.8, evidence=f"Heard '{hit}'")
                )

    def _extract_interests(self, normalized: str, result: ExtractionResult) -> None:
        for tag, phrases in INTEREST_PHRASES.items():
            hit = _first_phrase_hit(normalized, phrases)
            if hit:
                result.interests.append(
                    ExtractedFact(value=tag, confidence=0.75, evidence=f"Heard '{hit}'")
                )

    def _extract_constraints(self, normalized: str, result: ExtractionResult) -> None:
        for kind, label, phrases in CONSTRAINT_PHRASES:
            hit = _first_phrase_hit(normalized, phrases)
            if hit:
                result.constraints.append(
                    (kind, ExtractedFact(value=label, confidence=0.75, evidence=f"Heard '{hit}'"))
                )

    def _extract_numbers(self, normalized: str, result: ExtractionResult) -> None:
        age_match = _AGE_RE.search(normalized) or _AGE_ALT_RE.search(normalized)
        if age_match:
            age = int(age_match.group(1))
            if 14 <= age <= 80:
                result.age = ExtractedFact(
                    value=age, confidence=0.8, evidence=f"Heard '{age_match.group(0)}'"
                )

        km_match = _KM_RE.search(normalized)
        if km_match:
            result.max_travel_km = ExtractedFact(
                value=float(km_match.group(1)),
                confidence=0.85,
                evidence=f"Heard '{km_match.group(0)}'",
            )

        income_match = _INCOME_RE.search(normalized)
        if income_match:
            amount = income_match.group(1) or income_match.group(2)
            if amount:
                result.target_income = ExtractedFact(
                    value=int(amount), confidence=0.7, evidence=f"Heard '{income_match.group(0)}'"
                )

        # Experience: a duration stated next to a year unit anywhere in the text.
        for unit in YEAR_UNITS:
            normalized_unit = normalize_text(unit)
            if not normalized_unit or normalized_unit not in normalized:
                continue
            index = normalized.find(normalized_unit)
            window = normalized[max(0, index - 25) : index]
            years = extract_number(window)
            if years and 0 < years <= 60:
                result.experience_years = ExtractedFact(
                    value=years, confidence=0.8, evidence=f"Heard '{window.strip()} {unit}'"
                )
                break

    def _extract_location(self, db: Session, normalized: str, result: ExtractionResult) -> None:
        pincode = _PINCODE_RE.search(normalized)
        if pincode:
            result.pincode = ExtractedFact(
                value=pincode.group(1), confidence=0.9, evidence=f"Heard PIN {pincode.group(1)}"
            )

        # Match district/state names we actually hold data for. Guessing at
        # place names we have no coordinates for would be worse than silence -
        # the UI asks for location explicitly instead.
        districts = db.execute(
            select(Opportunity.district).where(Opportunity.district.is_not(None)).distinct()
        ).scalars().all()
        for district in districts:
            if district and normalize_text(district) in normalized:
                result.district = ExtractedFact(
                    value=district, confidence=0.7, evidence=f"Heard '{district}'"
                )
                break

        states = db.execute(
            select(Opportunity.state).where(Opportunity.state.is_not(None)).distinct()
        ).scalars().all()
        for state in states:
            if state and normalize_text(state) in normalized:
                result.state = ExtractedFact(
                    value=state, confidence=0.7, evidence=f"Heard '{state}'"
                )
                break


# ---------------------------------------------------------------------------
# Semantic pipeline (default)
# ---------------------------------------------------------------------------


class SemanticExtractor:
    """Meaning first, keywords last.

    1. The LLM, when one is configured, reads the message with the profile so far.
    2. Otherwise (or when the call fails) the offline multilingual encoder does.
    3. The deterministic extractor then contributes only what semantics cannot
       do well - exact numbers (age, km, income), PIN codes and known district
       names - and fills a categorical field only if both semantic layers left
       it empty, so it can never override an understood meaning.
    """

    name = "semantic"

    def __init__(self, *, force_llm: bool = False) -> None:
        from .semantic_understanding import EmbeddingSemanticExtractor, LLMSemanticExtractor  # noqa: PLC0415

        self._llm = LLMSemanticExtractor()
        self._embedding = EmbeddingSemanticExtractor()
        self._rules = RuleBasedExtractor()
        self._force_llm = force_llm

    def extract(self, db: Session, text: str, language_hint: str | None = None, context=None) -> ExtractionResult:
        from .semantic_understanding import semantic_model_available  # noqa: PLC0415

        semantic: ExtractionResult | None = None
        if self._llm.available():
            semantic = self._llm.extract(db, text, language_hint, context)
        if semantic is None and not self._force_llm and semantic_model_available():
            semantic = self._embedding.extract(db, text, language_hint, context)

        rules = self._rules.extract(db, text, language_hint)
        if semantic is None:
            return rules
        return _combine(semantic, rules)


def _combine(semantic: ExtractionResult, rules: ExtractionResult) -> ExtractionResult:
    """Semantic result, topped up with what only the rules can supply."""
    result = semantic
    for key in ("age", "max_travel_km", "target_income", "pincode", "district", "state"):
        if getattr(result, key) is None and getattr(rules, key) is not None:
            setattr(result, key, getattr(rules, key))
    if result.education is None:
        result.education = rules.education
    if result.mobility is None:
        result.mobility = rules.mobility
    if result.experience_years is None:
        result.experience_years = rules.experience_years
    if not result.goals:
        result.goals = rules.goals
    if not result.occupations and not result.previous_occupations:
        result.occupations = rules.occupations
    if not result.constraints:
        result.constraints = rules.constraints
    # Interests are left to the semantic layer: a keyword cannot tell "I like
    # business" from "I want to start a business" (a goal, already recorded).
    codes = {s.code for s in result.skills}
    # A leaf skill the encoder missed is added only on an exact alias match.
    # Category nodes are not: a keyword cannot tell "I run a business" from
    # "I want to start a business", and the skill graph derives categories
    # from the taxonomy anyway.
    # Nor is a skill the semantic layer understood as something they *want* to learn.
    wanted = {str(i.value) for i in result.interests}
    result.skills += [
        s for s in rules.skills
        if s.code not in codes and s.code not in wanted and s.is_exact and not s.is_category
    ]
    result.extractor = f"{semantic.extractor}+rules"
    return result


def get_profile_extractor():
    """Extractor selected by PROFILE_EXTRACTOR."""
    mode = get_settings().profile_extractor
    if mode == "rule_based":
        return RuleBasedExtractor()
    return SemanticExtractor(force_llm=mode == "llm")
