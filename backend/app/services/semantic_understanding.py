"""Multilingual semantic understanding of what a beneficiary said.

Two interchangeable engines turn one utterance - Kannada, Hindi, English,
Tamil, Telugu, or any mix of them - into the same `ExtractionResult` the rest
of the system already consumes (skill graph, skill gap, ranking):

* `LLMSemanticExtractor` - Claude reads the latest message together with the
  profile built so far and the question that was asked, and answers in a
  strict JSON schema with a closed vocabulary. Used when an API key is set.
* `EmbeddingSemanticExtractor` - offline. A multilingual sentence encoder
  (LaBSE by default) places spans of the utterance and short English concept
  descriptions in one shared meaning space, so "ಪಂಪ್ ರಿಪೇರಿ", "मोटर पंप ठीक
  कर लेता हूं" and "repair irrigation pumps" all land next to *pump repair*.
  The concept descriptions describe meanings, not surface keywords of any one
  language - nothing here is matched literally.

Both engines only ever produce values from a closed set (taxonomy skills,
education levels, goal and mobility bands). A meaning that does not resolve to
a known concept is dropped, never invented.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.enums import Confidence, EducationLevel, GoalType, Mobility
from ..models import Skill, SkillAlias
from .language_id import detect_language, extract_number, normalize_text
from .skill_normalization import SkillMatch, _infer_proficiency

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Context passed to an extractor
# ---------------------------------------------------------------------------


@dataclass
class ExtractionContext:
    """What the system already knows when the beneficiary speaks."""

    #: Slot the assistant just asked about, so short answers ("No.", "For
    #: several years") are read as answers to that question.
    pending_slot: str | None = None
    #: The question text itself, in the conversation language.
    question: str | None = None
    #: The running draft profile.
    draft: dict[str, Any] = field(default_factory=dict)
    #: 0..1 ASR confidence, None for typed input.
    asr_confidence: float | None = None


# ---------------------------------------------------------------------------
# Concept bank
# ---------------------------------------------------------------------------

#: Occupation titles. These are the same canonical titles the lexicon uses, so
#: existing profiles and analytics keep working.
OCCUPATIONS: dict[str, tuple[str, list[str]]] = {
    "Agriculture / farm work": (
        "Agriculture",
        [
            "I do farming",
            "I work in agriculture on my farm",
            "I am a farmer",
            "I grow crops on my land",
            "I used to do farming",
        ],
    ),
    "Agricultural labour": (
        "Agriculture",
        ["I work as a daily wage labourer on other people's farms", "I am a farm labourer"],
    ),
    "Dairy / livestock": (
        "Agriculture",
        ["I look after cows and buffaloes and sell milk", "I do dairy and livestock work"],
    ),
    "Machinery repair / mechanic": (
        "Engineering",
        ["I work as a mechanic", "I repair machines and vehicles in a workshop", "I used to work as a mechanic"],
    ),
    "Construction work": (
        "Construction",
        ["I work in construction as a mason", "I do building construction work", "I used to do construction work"],
    ),
    "Driving": (
        "Logistics",
        ["I work as a driver", "I drive an auto rickshaw or a vehicle for a living", "I used to work as a driver"],
    ),
    "Tailoring": ("Apparel", ["I work as a tailor", "I do stitching and tailoring work"]),
    "Shop / small trade": ("Retail", ["I run a small shop", "I do small trading business"]),
    "Electrician": ("Electrical", ["I work as an electrician", "I do house wiring work for people"]),
    "Currently not working": (None, ["I have no work right now", "I am unemployed", "I am sitting at home without a job"]),
}

GOALS: dict[str, list[str]] = {
    GoalType.SELF_EMPLOYMENT: [
        "I want to start my own business",
        "I want my own shop or workshop",
        "I want to be self employed and work for myself",
    ],
    GoalType.JOB: ["I want a job", "I need a salaried job with an employer", "I am looking for employment"],
    GoalType.APPRENTICESHIP: ["I want an apprenticeship", "I want to learn while working on the job"],
    GoalType.TRAINING: ["I want training and a certificate", "I want to learn a new skill in a course"],
    GoalType.HIGHER_INCOME: ["I want to earn more money", "I want a better income than now"],
}

MOBILITY: dict[str, list[str]] = {
    Mobility.LOW: [
        "I cannot travel far",
        "I can only work near my village",
        "I cannot go very far from home",
        "I am not comfortable travelling far",
    ],
    Mobility.MEDIUM: ["I can travel to the nearby town", "I can travel a short distance every day"],
    Mobility.HIGH: [
        "I can travel anywhere for work",
        "I am ready to move to the city",
        "I am comfortable travelling far",
    ],
}

#: Education levels that are named rather than numbered. Numbered school
#: levels are read from the class number (see `_education`), because a
#: sentence encoder places "10th" and "12th" almost on top of each other.
EDUCATION_NAMED = {"none", "iti", "diploma", "graduate", "postgraduate"}

#: Number words in English; other languages reach them through the encoder
#: ("ಹತ್ತನೇ" and "दसवीं" both land on "tenth").
NUMERALS: dict[int, list[str]] = {
    1: ["one", "first"], 2: ["two", "second"], 3: ["three", "third"], 4: ["four", "fourth"],
    5: ["five", "fifth"], 6: ["six", "sixth"], 7: ["seven", "seventh"], 8: ["eight", "eighth"],
    9: ["nine", "ninth"], 10: ["ten", "tenth"], 11: ["eleven", "eleventh"], 12: ["twelve", "twelfth"],
}

EDUCATION: dict[str, list[str]] = {
    EducationLevel.NONE: ["I never went to school", "I have not studied at all"],
    EducationLevel.PRIMARY: ["I studied only in primary school", "I studied up to 5th class"],
    EducationLevel.CLASS_8: ["I studied up to 8th standard", "I passed 8th class"],
    EducationLevel.CLASS_10: ["I studied up to 10th standard", "I passed 10th class SSLC", "I completed matriculation"],
    EducationLevel.CLASS_12: ["I passed 12th standard", "I completed PUC or higher secondary"],
    EducationLevel.ITI: ["I studied at an ITI", "I have an ITI trade certificate"],
    EducationLevel.DIPLOMA: ["I have a polytechnic diploma"],
    EducationLevel.GRADUATE: ["I completed a college degree", "I am a graduate"],
    EducationLevel.POSTGRADUATE: ["I have a master's degree", "I am a post graduate"],
}

#: Durations. `None` years means a qualitative statement that is recorded as
#: said ("several years") instead of being converted into a made-up number.
EXPERIENCE: dict[str, tuple[float | None, list[str]]] = {
    "Less than a year": (0.5, ["for a few months", "I started only recently"]),
    "About 1 year": (1, ["for one year"]),
    "About 2 years": (2, ["for two years"]),
    "About 3 years": (3, ["for three years"]),
    "About 4 years": (4, ["for four years"]),
    "About 5 years": (5, ["for five years"]),
    "About 6 years": (6, ["for six years"]),
    "About 8 years": (8, ["for eight years"]),
    "About 10 years": (10, ["for ten years"]),
    "About 15 years": (15, ["for fifteen years"]),
    "About 20 years": (20, ["for twenty years"]),
    "Several years": (None, ["for several years", "for many years", "for a long time"]),
}

INTERESTS: dict[str, list[str]] = {
    "mechanical": ["I like working with machines", "I enjoy mechanical work"],
    "electrical": ["I like electrical work"],
    "agriculture": ["I like farming work"],
    "enterprise": ["I like doing business and selling"],
    "computers": ["I like working on computers and mobiles"],
    "driving": ["I like driving vehicles"],
    "tailoring": ["I like stitching clothes"],
    "construction": ["I like building and construction work"],
}

ANSWERS: dict[str, list[str]] = {
    "yes": ["Yes", "Yes, of course", "Yes, that is fine"],
    "no": ["No", "No, not at all", "No, I can't"],
}

#: Whether a clause is about the present, the past, or a wish.
STATUS: dict[str, list[str]] = {
    "current": ["I do this work now", "I know how to do this", "I am doing this"],
    "past": ["I used to do this before but I stopped", "I did this earlier, not anymore"],
    "desired": ["I want to learn this", "I would like to do this in the future"],
}

#: Cosine-similarity floors, calibrated on LaBSE (see tests/test_semantic.py):
#: correct meanings score 0.80-0.97, the nearest wrong concept rarely above 0.77.
_ORDINAL_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:st|nd|rd|th)?(?!\d)", re.IGNORECASE)


def _level_for_class(number: int) -> str | None:
    if 1 <= number <= 5:
        return str(EducationLevel.PRIMARY)
    if 6 <= number <= 9:
        return str(EducationLevel.CLASS_8)
    if number in (10, 11):
        return str(EducationLevel.CLASS_10)
    if number == 12:
        return str(EducationLevel.CLASS_12)
    return None


THRESHOLD = {
    "occupation": 0.80,
    "skill": 0.80,
    "goal": 0.80,
    "mobility": 0.80,
    "education": 0.78,
    "experience": 0.82,
    "interest": 0.82,
    "answer": 0.85,
}
#: The winner must beat the runner-up of the same kind by this much.
MARGIN = 0.04
#: Lower bar for a skill named inside a clearly-desired clause.
DESIRED_SKILL_FLOOR = 0.65
#: A sentence is about schooling when some education concept scores this high.
EDUCATION_INTENT = 0.75
#: A clause is only treated as past or desired when it is clearly so.
STATUS_MARGIN = 0.05

_PUNCT_END = re.compile(r"[,.;:!?।॥]+$")


# ---------------------------------------------------------------------------
# Encoder (lazy singleton)
# ---------------------------------------------------------------------------


class _Encoder:
    """Loads the sentence encoder once, on first use, from the local cache."""

    def __init__(self) -> None:
        self._model = None
        self._failed = False
        self._lock = threading.Lock()

    def get(self):
        if self._model is not None or self._failed:
            return self._model
        with self._lock:
            if self._model is None and not self._failed:
                name = get_settings().semantic_model
                started = time.perf_counter()
                try:
                    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

                    self._model = SentenceTransformer(name)
                    logger.info("Loaded semantic model %s in %.1fs", name, time.perf_counter() - started)
                except Exception:  # noqa: BLE001 - any failure means "offline layer unavailable"
                    logger.warning("Semantic model %s unavailable; using the lexicon only", name, exc_info=True)
                    self._failed = True
        return self._model

    def encode(self, texts: list[str]):
        model = self.get()
        if model is None:
            return None
        return model.encode(texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)


ENCODER = _Encoder()


def semantic_model_available() -> bool:
    """Load the encoder if needed; True when the offline semantic layer works."""
    return ENCODER.get() is not None


def semantic_model_loaded() -> bool:
    """Whether the encoder is already in memory (never triggers a load)."""
    return ENCODER._model is not None


def warm_up(db_factory) -> None:
    """Load the encoder and embed the concept bank ahead of the first turn."""
    try:
        if semantic_model_available():
            with db_factory() as db:
                BANK.ensure(db)
    except Exception:  # noqa: BLE001 - warm-up is best effort; the first turn retries
        logger.warning("Semantic warm-up failed", exc_info=True)


@dataclass
class _Concept:
    kind: str
    value: str
    prototype: str


@dataclass
class _SkillInfo:
    skill_id: str
    code: str
    name: str


class _ConceptBank:
    """All concepts, embedded once per process (skills reload if the taxonomy changes)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._signature: tuple | None = None
        self.concepts: list[_Concept] = []
        self.matrix = None
        self.skills: dict[str, _SkillInfo] = {}

    def ensure(self, db: Session) -> bool:
        rows = db.execute(
            select(Skill.id, Skill.code, Skill.name)
            .where(Skill.is_active.is_(True), Skill.is_category.is_(False))
            .order_by(Skill.code)
        ).all()
        signature = tuple(r.code for r in rows)
        if signature == self._signature and self.matrix is not None:
            return True
        with self._lock:
            if signature == self._signature and self.matrix is not None:
                return True
            aliases: dict[str, list[str]] = {}
            for skill_id, alias in db.execute(
                select(SkillAlias.skill_id, SkillAlias.alias).where(SkillAlias.language == "en")
            ).all():
                aliases.setdefault(skill_id, []).append(alias)

            concepts: list[_Concept] = []
            skills: dict[str, _SkillInfo] = {}
            for skill_id, code, name in rows:
                skills[code] = _SkillInfo(skill_id, code, name)
                for phrase in dict.fromkeys([name, *aliases.get(skill_id, [])]):
                    concepts.append(_Concept("skill", code, phrase))
            for title, (_, protos) in OCCUPATIONS.items():
                concepts += [_Concept("occupation", title, p) for p in protos]
            for kind, table in (
                ("goal", GOALS),
                ("mobility", MOBILITY),
                ("education", EDUCATION),
                ("interest", INTERESTS),
                ("answer", ANSWERS),
                ("status", STATUS),
            ):
                for value, protos in table.items():
                    concepts += [_Concept(kind, str(value), p) for p in protos]
            for label, (_, protos) in EXPERIENCE.items():
                concepts += [_Concept("experience", label, p) for p in protos]
            for number, words in NUMERALS.items():
                concepts += [_Concept("numeral", str(number), w) for w in words]

            matrix = ENCODER.encode([c.prototype for c in concepts])
            if matrix is None:
                return False
            self.concepts, self.matrix, self.skills, self._signature = concepts, matrix, skills, signature
            return True


BANK = _ConceptBank()


# ---------------------------------------------------------------------------
# Embedding extractor
# ---------------------------------------------------------------------------


@dataclass
class _Span:
    start: int
    end: int  # exclusive, in words
    text: str


def _spans(text: str, max_len: int = 6) -> tuple[list[_Span], list[tuple[int, int]]]:
    """Every contiguous word window up to `max_len`, plus each clause and the whole text.

    Splitting is on whitespace and punctuation only - no language's words are
    treated specially - so it works the same for every script.
    """
    words = text.split()
    n = len(words)
    clauses: list[tuple[int, int]] = []
    start = 0
    for index, word in enumerate(words):
        if _PUNCT_END.search(word):
            clauses.append((start, index + 1))
            start = index + 1
    if start < n:
        clauses.append((start, n))

    windows: set[tuple[int, int]] = {(0, n)} | set(clauses)
    shortest = 1 if n <= 4 else 2
    for size in range(shortest, max_len + 1):
        for i in range(0, n - size + 1):
            windows.add((i, i + size))
    spans = [
        _Span(i, j, _PUNCT_END.sub("", " ".join(words[i:j])).strip())
        for i, j in sorted(windows)
        if j > i
    ]
    return [s for s in spans if s.text], clauses


@dataclass
class _Hit:
    kind: str
    value: str
    score: float
    span: _Span
    runner_up: float


class EmbeddingSemanticExtractor:
    """Offline multilingual understanding with a sentence encoder."""

    name = "semantic_embedding"

    def extract(self, db: Session, text: str, language_hint: str | None = None, context: ExtractionContext | None = None):
        from .profile_extraction import ExtractedFact, ExtractionResult  # noqa: PLC0415

        context = context or ExtractionContext()
        detection = detect_language(text, language_hint)
        result = ExtractionResult(
            language=detection.language,
            language_confidence=detection.confidence,
            is_code_switched=detection.is_code_switched,
            normalized_text=normalize_text(text),
            extractor=self.name,
        )
        if not text.strip() or not BANK.ensure(db):
            return result

        spans, clauses = _spans(text.strip())
        vectors = ENCODER.encode([s.text for s in spans])
        if vectors is None:
            return result
        sims = vectors @ BANK.matrix.T  # spans x prototypes

        hits = self._best_per_value(spans, sims)
        word_count = len(text.split())

        def clause_of(span: _Span) -> _Span:
            for i, j in clauses:
                if i <= span.start and span.end <= j:
                    return next((s for s in spans if s.start == i and s.end == j), span)
            return span

        status_cache: dict[tuple[int, int], str] = {}

        def status_of(span: _Span) -> str:
            # A multi-word span carries its own tense ("I stopped farming");
            # a single word needs its clause for context.
            clause = span if span.end - span.start >= 2 else clause_of(span)
            key = (clause.start, clause.end)
            if key not in status_cache:
                index = spans.index(clause)
                scores = {
                    value: max(
                        float(sims[index, k])
                        for k, c in enumerate(BANK.concepts)
                        if c.kind == "status" and c.value == value
                    )
                    for value in STATUS
                }
                best = max(scores, key=scores.get)
                status_cache[key] = (
                    best if best != "current" and scores[best] - scores["current"] >= STATUS_MARGIN else "current"
                )
            return status_cache[key]

        def accepted(kind: str) -> list[_Hit]:
            return [
                h
                for h in hits.get(kind, [])
                if h.score >= THRESHOLD[kind] and h.score - h.runner_up >= MARGIN
            ]

        def fact(hit: _Hit, value: Any, *, label: str | None = None, scale: float = 1.0) -> ExtractedFact:
            item = ExtractedFact(
                value=value,
                confidence=round(min(0.95, hit.score) * scale, 3),
                evidence=f"Understood '{hit.span.text}'",
                extractor=self.name,
            )
            if label:
                item.label = label
            return item

        # -- skills (several allowed, one per stretch of speech) -------------
        chosen_skills: list[_Hit] = []
        ranked_skills = sorted(hits.get("skill", []), key=lambda h: -h.score)
        for position, hit in enumerate(ranked_skills):
            if hit.score < THRESHOLD["skill"]:
                # "I want to learn welding": the wish words dilute the match, so
                # a clearly-leading skill in a clearly-desired clause is kept as
                # an interest (never as a skill the person already has).
                next_score = ranked_skills[position + 1].score if position + 1 < len(ranked_skills) else 0.0
                if not (
                    position == 0
                    and hit.score >= DESIRED_SKILL_FLOOR
                    and hit.score - next_score >= 0.08
                    and status_of(hit.span) == "desired"
                ):
                    continue
            if any(_overlaps(hit.span, other.span) for other in chosen_skills):
                continue
            chosen_skills.append(hit)
        for hit in chosen_skills:
            info = BANK.skills[hit.value]
            status = status_of(hit.span)
            if status == "desired":
                result.interests.append(fact(hit, info.code, label=f"Wants to learn {info.name.lower()}"))
                continue
            if status == "past":
                continue
            years = _years_in(hit.span.text) or _years_in(clause_of(hit.span).text)
            proficiency, band, score = _infer_proficiency(result.normalized_text, years)
            result.skills.append(
                SkillMatch(
                    skill_id=info.skill_id,
                    code=info.code,
                    name=info.name,
                    raw_label=hit.span.text,
                    matched_alias=info.name,
                    alias_language=detection.language,
                    position=hit.span.start,
                    confidence=band,
                    confidence_score=round(min(score, hit.score), 3),
                    proficiency=proficiency,
                    years_experience=years,
                    evidence=f"Understood '{hit.span.text}' as {info.name.lower()}"
                    + (f", about {years:g} year(s)" if years else ""),
                    is_category=False,
                    is_exact=False,
                )
            )

        # -- occupation: current vs previous ----------------------------------
        skill_spans = [h.span for h in chosen_skills]
        for hit in sorted(accepted("occupation"), key=lambda h: -h.score)[:2]:
            # "I repair pumps" is a skill; only call it an occupation when the
            # same words were not already taken by a better skill match.
            if any(_overlaps(hit.span, s) and h.score >= hit.score for s, h in zip(skill_spans, chosen_skills)):
                continue
            status = status_of(hit.span)
            sector = OCCUPATIONS[hit.value][0]
            occupation = fact(hit, hit.value)
            occupation.evidence += f" (sector: {sector})" if sector else ""
            if status == "past":
                result.previous_occupations.append(occupation)
            elif status == "current":
                result.occupations.append(occupation)

        # -- single-valued slots ------------------------------------------------
        for hit in accepted("goal")[:1]:
            result.goals.append(fact(hit, hit.value))
        for hit in accepted("mobility")[:1]:
            result.mobility = fact(hit, hit.value)
        result.education = self._education(text, spans, sims, hits, context, fact)
        for hit in accepted("interest"):
            # "I want to start a business" is a goal, not a liking for business.
            if status_of(hit.span) == "current" and not result.goals:
                result.interests.append(fact(hit, hit.value))

        if result.experience_years is None:
            number = _years_in(text)
            mentions_duration = accepted("experience") or context.pending_slot == "experience"
            if number and mentions_duration:
                result.experience_years = ExtractedFact(
                    value=number, confidence=0.85, evidence=f"Heard '{text.strip()}'", extractor=self.name
                )
            elif accepted("experience"):
                hit = accepted("experience")[0]
                years, _ = EXPERIENCE[hit.value]
                result.experience_years = fact(hit, years, label=hit.value)

        # -- short yes/no answers to the question just asked --------------------
        if word_count <= 4 and context.pending_slot == "mobility" and result.mobility is None:
            for hit in accepted("answer")[:1]:
                band = Mobility.HIGH if hit.value == "yes" else Mobility.LOW
                result.mobility = fact(hit, str(band), scale=0.9)
                result.mobility.evidence = f"Answered '{text.strip()}' to the travel question"

        return result

    @staticmethod
    def _education(text, spans, sims, hits, context, fact):
        """Is this about schooling, and if so which level?"""
        candidates = hits.get("education", [])
        if not candidates:
            return None
        top = max(candidates, key=lambda h: h.score)
        if top.score < EDUCATION_INTENT and context.pending_slot != "education":
            return None

        # Named levels (ITI, diploma, degree, never studied) by meaning.
        named = sorted((h for h in candidates if h.value in EDUCATION_NAMED), key=lambda h: -h.score)
        best_numbered = max((h.score for h in candidates if h.value not in EDUCATION_NAMED), default=0.0)
        if named and named[0].score >= THRESHOLD["education"] and named[0].score - best_numbered >= MARGIN:
            return fact(named[0], named[0].value)

        # Numbered levels from the class number: digits first, then number words.
        level = None
        match = _ORDINAL_RE.search(text)
        if match:
            level = _level_for_class(int(match.group(1)))
        else:
            numeral_columns = [(k, int(c.value)) for k, c in enumerate(BANK.concepts) if c.kind == "numeral"]
            words = [w for w in (_PUNCT_END.sub("", w) for w in text.split()) if w]
            word_vectors = ENCODER.encode(words) if words else None
            # Best score per *level*: "tenth" and "eleventh" are the same level,
            # so they must not count as rivals of each other.
            scores: dict[str, float] = {}
            if word_vectors is not None:
                for row in word_vectors @ BANK.matrix.T:
                    for k, number in numeral_columns:
                        candidate = _level_for_class(number)
                        if candidate:
                            scores[candidate] = max(scores.get(candidate, 0.0), float(row[k]))
            ranked = sorted(scores.items(), key=lambda kv: -kv[1])
            if ranked and ranked[0][1] >= 0.82 and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= 0.03):
                level = ranked[0][0]
        if level is None:
            return None
        return fact(_Hit("education", level, top.score, top.span, 0.0), level)

    @staticmethod
    def _best_per_value(spans: list[_Span], sims) -> dict[str, list[_Hit]]:
        """Best-scoring span for every concept value, with the runner-up of its kind."""
        best: dict[tuple[str, str], tuple[float, int]] = {}
        for k, concept in enumerate(BANK.concepts):
            if concept.kind in {"status", "numeral"}:
                continue
            column = sims[:, k]
            index = int(column.argmax())
            score = float(column[index])
            key = (concept.kind, concept.value)
            if score > best.get(key, (-1.0, 0))[0]:
                best[key] = (score, index)

        by_kind: dict[str, list[tuple[str, float, int]]] = {}
        for (kind, value), (score, index) in best.items():
            by_kind.setdefault(kind, []).append((value, score, index))

        hits: dict[str, list[_Hit]] = {}
        for kind, items in by_kind.items():
            items.sort(key=lambda item: -item[1])
            for value, score, index in items:
                # A rival only counts when it was heard in the same words: "I
                # farmed before, now I'm a mechanic" holds two occupations in two
                # clauses, and they must not cancel each other out.
                others = [
                    s for v, s, i in items if v != value and _overlaps(spans[i], spans[index])
                ]
                # Several skills can share one sentence; every other kind competes.
                runner_up = 0.0 if kind == "skill" else (max(others) if others else 0.0)
                hits.setdefault(kind, []).append(_Hit(kind, value, score, spans[index], runner_up))
        return hits


def _overlaps(a: _Span, b: _Span) -> bool:
    return a.start < b.end and b.start < a.end


def _years_in(text: str) -> float | None:
    """A duration stated with digits or number words, when it reads as years."""
    value = extract_number(text)
    if value is None or not (0 < value <= 60):
        return None
    return float(value)


# ---------------------------------------------------------------------------
# Skill phrase -> taxonomy (shared by the LLM path)
# ---------------------------------------------------------------------------


def resolve_skill_phrase(db: Session, phrase: str) -> tuple[_SkillInfo, float] | None:
    """Closest taxonomy skill for an English skill phrase, or None if nothing is close."""
    if not phrase.strip() or not BANK.ensure(db):
        return None
    vector = ENCODER.encode([phrase])
    if vector is None:
        return None
    sims = (vector @ BANK.matrix.T)[0]
    best_code, best_score = None, 0.0
    for k, concept in enumerate(BANK.concepts):
        if concept.kind == "skill" and float(sims[k]) > best_score:
            best_code, best_score = concept.value, float(sims[k])
    if best_code is None or best_score < THRESHOLD["skill"] - 0.05:
        return None
    return BANK.skills[best_code], best_score


def _taxonomy_skill(db: Session, phrase: str) -> _SkillInfo | None:
    """Semantic match when the encoder is available, exact alias match otherwise."""
    resolved = resolve_skill_phrase(db, phrase)
    if resolved is not None:
        return resolved[0]
    from .skill_normalization import match_skills_in_text  # noqa: PLC0415

    for match in match_skills_in_text(db, phrase):
        if not match.is_category:
            return _SkillInfo(match.skill_id, match.code, match.name)
    return None


# ---------------------------------------------------------------------------
# LLM extractor
# ---------------------------------------------------------------------------

LLM_SYSTEM = """You are a multilingual beneficiary-profile extraction engine for a livelihood service in rural India.

The person may speak Kannada, Hindi, English, Tamil, Telugu, Marathi, Bengali, or a mixture of languages (code-switching). Understand the meaning; do not depend on English keywords.

Read the LATEST USER MESSAGE in the light of the QUESTION THEY WERE ANSWERING and the PREVIOUS PROFILE, and extract only facts that are explicitly stated or strongly supported by the latest message.

Rules:
1. Never invent facts. Unknown values are null or empty lists.
2. Report only what the latest message adds or changes; the caller preserves previous facts.
3. Interpret meaning, not literal words. A short answer ("No.", "For several years.") answers the question that was asked.
4. Distinguish skills the person has now (status "current") from skills they want to learn (status "desired").
5. Distinguish current occupation from past occupation. If they stopped one kind of work, put it in previous_occupation.
6. Use only the allowed enum values. Map the person's work to the closest occupation category; use "Other" with a short English description only if none fits.
7. Skill phrases are short plain English, e.g. "pump repair", "tractor driving".
8. Give a confidence between 0 and 1 for each field you fill, 0 for fields you leave empty.
9. Set understood to false if the message contains no usable profile information."""

_OCCUPATION_CHOICES = [*OCCUPATIONS.keys(), "Other"]
_EDUCATION_CHOICES = [str(e) for e in EducationLevel]
_GOAL_CHOICES = [str(g) for g in GoalType]
_MOBILITY_CHOICES = [str(m) for m in Mobility]
_INTEREST_CHOICES = list(INTERESTS.keys())


def _nullable_enum(choices: list[str]) -> dict:
    return {"anyOf": [{"type": "string", "enum": choices}, {"type": "null"}]}


_OCCUPATION_SCHEMA = {
    "anyOf": [
        {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": _OCCUPATION_CHOICES},
                "description_en": {"type": "string"},
            },
            "required": ["category", "description_en"],
            "additionalProperties": False,
        },
        {"type": "null"},
    ]
}

LLM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "understood": {"type": "boolean"},
        "language": {"type": "string"},
        "education": _nullable_enum(_EDUCATION_CHOICES),
        "current_occupation": _OCCUPATION_SCHEMA,
        "previous_occupation": _OCCUPATION_SCHEMA,
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "phrase_en": {"type": "string"},
                    "status": {"type": "string", "enum": ["current", "desired"]},
                },
                "required": ["phrase_en", "status"],
                "additionalProperties": False,
            },
        },
        "experience": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "years": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                        "description_en": {"type": "string"},
                    },
                    "required": ["years", "description_en"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ]
        },
        "interests": {"type": "array", "items": {"type": "string", "enum": _INTEREST_CHOICES}},
        "goal": _nullable_enum(_GOAL_CHOICES),
        "mobility": _nullable_enum(_MOBILITY_CHOICES),
        "max_travel_km": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        "confidence": {
            "type": "object",
            "properties": {
                key: {"type": "number"}
                for key in ("education", "occupation", "skills", "experience", "goal", "mobility", "interests")
            },
            "required": ["education", "occupation", "skills", "experience", "goal", "mobility", "interests"],
            "additionalProperties": False,
        },
    },
    "required": [
        "understood", "language", "education", "current_occupation", "previous_occupation", "skills",
        "experience", "interests", "goal", "mobility", "max_travel_km", "confidence",
    ],
    "additionalProperties": False,
}


def _compact_profile(draft: dict[str, Any]) -> dict[str, Any]:
    """The previous profile as the model should see it: values only, no evidence."""

    def value(fact):
        return fact.get("label") or fact.get("value") if isinstance(fact, dict) else None

    return {
        "education": value(draft.get("education")),
        "occupations": [o.get("value") for o in draft.get("occupations", [])],
        "previous_occupations": [o.get("value") for o in draft.get("previous_occupations", [])],
        "skills": [s.get("name") for s in draft.get("skills", []) if not s.get("is_category")],
        "experience": value(draft.get("experience_years")),
        "interests": [i.get("value") for i in draft.get("interests", [])],
        "goals": [g.get("value") for g in draft.get("goals", [])],
        "mobility": value(draft.get("mobility")),
    }


class LLMSemanticExtractor:
    """Claude-based extraction with a strict schema and a closed vocabulary."""

    name = "semantic_llm"

    def available(self) -> bool:
        settings = get_settings()
        return settings.llm_provider == "anthropic" and bool(settings.anthropic_api_key)

    def call(self, text: str, context: ExtractionContext) -> dict | None:
        """One structured request. Returns the parsed JSON, or None on any failure."""
        import anthropic  # noqa: PLC0415

        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=20.0, max_retries=1)
        user = (
            f"PREVIOUS PROFILE:\n{json.dumps(_compact_profile(context.draft), ensure_ascii=False)}\n\n"
            f"QUESTION THEY WERE ANSWERING:\n{context.question or '(opening question about their work)'}\n\n"
            f"LATEST USER MESSAGE:\n{text}"
        )
        started = time.perf_counter()
        try:
            response = client.beta.messages.create(
                model=settings.llm_model,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                # Short extraction on a latency-sensitive voice turn.
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": LLM_SCHEMA}},
                system=LLM_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIConnectionError:
            logger.warning("LLM extraction: network error; falling back to the offline engine")
            return None
        except anthropic.RateLimitError:
            logger.warning("LLM extraction: rate limited; falling back to the offline engine")
            return None
        except anthropic.APIStatusError as exc:
            logger.warning("LLM extraction failed with HTTP %s; falling back", exc.status_code)
            return None
        latency = time.perf_counter() - started
        if response.stop_reason == "refusal":
            logger.warning("LLM extraction refused; falling back to the offline engine")
            return None
        body = next((b.text for b in response.content if b.type == "text"), "")
        try:
            payload = json.loads(body)
        except ValueError:
            logger.warning("LLM extraction returned unparseable JSON; falling back")
            return None
        logger.info("LLM extraction in %.2fs (model %s)", latency, response.model)
        return payload

    def extract(self, db: Session, text: str, language_hint: str | None = None, context: ExtractionContext | None = None):
        context = context or ExtractionContext()
        payload = self.call(text, context)
        if payload is None:
            return None
        return self.to_result(db, text, language_hint, payload)

    def to_result(self, db: Session, text: str, language_hint: str | None, payload: dict):
        """Validate a model payload against the closed vocabulary."""
        from .profile_extraction import ExtractedFact, ExtractionResult  # noqa: PLC0415

        detection = detect_language(text, language_hint)
        result = ExtractionResult(
            language=detection.language,
            language_confidence=detection.confidence,
            is_code_switched=detection.is_code_switched,
            normalized_text=normalize_text(text),
            extractor=self.name,
        )
        confidence = payload.get("confidence") or {}
        evidence = f"Understood from '{text.strip()[:120]}'"

        def conf(key: str) -> float:
            try:
                return round(max(0.0, min(0.95, float(confidence.get(key, 0.6)))), 3)
            except (TypeError, ValueError):
                return 0.6

        def make(value, key, label=None) -> ExtractedFact:
            item = ExtractedFact(value=value, confidence=conf(key), evidence=evidence, extractor=self.name)
            if label:
                item.label = label
            return item

        if payload.get("education") in _EDUCATION_CHOICES:
            result.education = make(payload["education"], "education")
        if payload.get("goal") in _GOAL_CHOICES:
            result.goals.append(make(payload["goal"], "goal"))
        if payload.get("mobility") in _MOBILITY_CHOICES:
            result.mobility = make(payload["mobility"], "mobility")
        if isinstance(payload.get("max_travel_km"), (int, float)) and 0 < payload["max_travel_km"] <= 500:
            result.max_travel_km = make(float(payload["max_travel_km"]), "mobility")

        for key, target in (("current_occupation", result.occupations), ("previous_occupation", result.previous_occupations)):
            occupation = payload.get(key)
            if isinstance(occupation, dict) and occupation.get("category") in _OCCUPATION_CHOICES:
                category = occupation["category"]
                title = (occupation.get("description_en") or "").strip()[:160] if category == "Other" else category
                if title:
                    target.append(make(title, "occupation"))

        experience = payload.get("experience")
        if isinstance(experience, dict):
            years = experience.get("years")
            years = float(years) if isinstance(years, (int, float)) and 0 < years <= 60 else None
            label = (experience.get("description_en") or "").strip()[:60] or None
            if years or label:
                result.experience_years = make(years, "experience", label=None if years else label)

        for tag in payload.get("interests") or []:
            if tag in INTERESTS:
                result.interests.append(make(tag, "interests"))

        known: set[str] = set()
        for skill in payload.get("skills") or []:
            phrase = (skill or {}).get("phrase_en", "")
            info = _taxonomy_skill(db, phrase)
            if info is None:
                continue  # Not in the taxonomy - dropped, never stored as an invented skill.
            if info.code in known:
                continue
            known.add(info.code)
            if skill.get("status") == "desired":
                result.interests.append(make(info.code, "skills", label=f"Wants to learn {info.name.lower()}"))
                continue
            years = result.experience_years.value if result.experience_years and len(payload.get("skills") or []) == 1 else None
            proficiency, band, _ = _infer_proficiency(result.normalized_text, years)
            result.skills.append(
                SkillMatch(
                    skill_id=info.skill_id,
                    code=info.code,
                    name=info.name,
                    raw_label=phrase,
                    matched_alias=info.name,
                    alias_language=detection.language,
                    confidence=band if conf("skills") >= 0.6 else Confidence.LOW,
                    confidence_score=conf("skills"),
                    proficiency=proficiency,
                    years_experience=years,
                    evidence=f"Understood '{phrase}' as {info.name.lower()}",
                    is_exact=False,
                )
            )
        return result
