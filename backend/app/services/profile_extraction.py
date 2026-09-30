"""Phase 2 - turn an utterance into structured beneficiary facts.

Two extractors:

* `RuleBasedExtractor` (default) - deterministic lexicon + taxonomy matching.
  Every fact it produces carries the phrase that produced it, so a human can
  audit the extraction. It works offline and never invents a value.
* `LLMAssistedExtractor` - optional. It runs the rule-based extractor first,
  then asks an LLM only about fields the rules left empty. Rule-based results
  always win on conflict, and the LLM is constrained to a closed vocabulary, so
  it cannot introduce an unknown education level or invent a skill.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.enums import (
    Confidence,
    EducationLevel,
    GoalType,
    Mobility,
)
from ..models import Opportunity
from ..providers.llm import complete_json
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

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExtractionResult:
    language: str = "en"
    language_confidence: float = 0.0
    is_code_switched: bool = False
    normalized_text: str = ""

    education: ExtractedFact | None = None
    occupations: list[ExtractedFact] = field(default_factory=list)
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
            "education": self.education.as_dict() if self.education else None,
            "occupations": [o.as_dict() for o in self.occupations],
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
        self, db: Session, text: str, language_hint: str | None = None
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
# LLM-assisted extraction (optional)
# ---------------------------------------------------------------------------

_LLM_SYSTEM = """You extract structured facts from what a rural job seeker in India said about themselves.

Rules you must follow:
- Only report what the person actually said. If something was not said, use null.
- Never invent skills, courses, employers, schemes or qualifications.
- Use ONLY these values.
  education: none, primary, class_8, class_10, class_12, iti, diploma, graduate, postgraduate
  mobility: low, medium, high
  goal: job, apprenticeship, training, self_employment, higher_income, undecided
- "skills" must be short plain phrases describing what the person can do, in English.
- Reply with JSON only, no commentary.

JSON shape:
{"education": str|null, "occupation": str|null, "skills": [str],
 "interests": [str], "goal": str|null, "mobility": str|null,
 "experience_years": number|null, "age": number|null}"""

_ALLOWED_EDUCATION = {str(e) for e in EducationLevel}
_ALLOWED_MOBILITY = {str(m) for m in Mobility}
_ALLOWED_GOALS = {str(g) for g in GoalType}


class LLMAssistedExtractor:
    """Rule-based first; the LLM only fills gaps, inside a closed vocabulary."""

    name = "llm"

    def __init__(self) -> None:
        self._rules = RuleBasedExtractor()

    def extract(self, db: Session, text: str, language_hint: str | None = None) -> ExtractionResult:
        result = self._rules.extract(db, text, language_hint)
        payload = complete_json(_LLM_SYSTEM, f"The person said:\n{text}", max_tokens=600)
        if not payload:
            return result  # LLM unavailable or unparseable - deterministic result stands.

        if result.education is None:
            value = payload.get("education")
            if isinstance(value, str) and value in _ALLOWED_EDUCATION:
                result.education = ExtractedFact(
                    value=value, confidence=0.6, evidence="Inferred by language model", extractor="llm"
                )

        if result.mobility is None:
            value = payload.get("mobility")
            if isinstance(value, str) and value in _ALLOWED_MOBILITY:
                result.mobility = ExtractedFact(
                    value=value, confidence=0.6, evidence="Inferred by language model", extractor="llm"
                )

        if not result.goals:
            value = payload.get("goal")
            if isinstance(value, str) and value in _ALLOWED_GOALS:
                result.goals.append(
                    ExtractedFact(
                        value=value, confidence=0.6, evidence="Inferred by language model", extractor="llm"
                    )
                )

        if not result.occupations and isinstance(payload.get("occupation"), str):
            result.occupations.append(
                ExtractedFact(
                    value=payload["occupation"][:160],
                    confidence=0.55,
                    evidence="Inferred by language model",
                    extractor="llm",
                )
            )

        # LLM-proposed skills are re-matched against the taxonomy. Anything that
        # does not resolve to a known skill is discarded rather than stored.
        proposed = payload.get("skills")
        if isinstance(proposed, list):
            known = {s.code for s in result.skills}
            index = build_alias_index(db)
            for phrase in proposed[:10]:
                if not isinstance(phrase, str):
                    continue
                for match in match_skills_in_text(db, phrase, index):
                    if match.code not in known:
                        match.confidence = Confidence.LOW
                        match.confidence_score = 0.5
                        match.evidence = f"Language model suggested '{phrase}'; matched to taxonomy"
                        result.skills.append(match)
                        known.add(match.code)
        return result


def get_profile_extractor():
    """Extractor selected by PROFILE_EXTRACTOR."""
    if get_settings().profile_extractor == "llm":
        return LLMAssistedExtractor()
    return RuleBasedExtractor()
