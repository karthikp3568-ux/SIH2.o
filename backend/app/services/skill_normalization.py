"""Map free-text skill mentions onto the canonical skill taxonomy.

Matching is token-based rather than plain substring, because people do not
speak in dictionary form. "I repair pumps", "pump repairing" and "pumpset
repair" all have to reach the same taxonomy node.

The algorithm:
  1. Tokenise the utterance and light-stem Latin-script tokens (plurals, -ing).
  2. Try each alias longest-first. A multi-word alias matches when all of its
     tokens appear inside a small sliding window, in any order.
  3. Consume the matched token positions, but allow an alias to match if it
     brings at least one *new* token. That is what lets "I repair pumps and
     farm machinery" produce both `pump_repair` and `farm_machinery_maintenance`
     from one shared verb.

Aliases come from the database, so adding a regional-language surface form is a
data change, not a code change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.enums import Confidence, Proficiency, SkillSource, VerificationStatus
from ..models import Skill, SkillAlias
from .language_id import normalize_text
from .lexicon import (
    CERTIFICATION_CUES,
    MONTH_UNITS,
    OCCASIONAL_CUES,
    REGULAR_CUES,
    YEAR_UNITS,
)

#: Extra tokens a multi-word alias may be separated by and still match.
WINDOW_SLACK = 2

_LATIN_RE = re.compile(r"^[a-z0-9]+$")


def stem(token: str) -> str:
    """Very light stemmer, Latin script only.

    Deliberately conservative: it only strips plural and gerund endings. Indic
    tokens are returned untouched, because naive suffix stripping on Devanagari
    or Tamil does more harm than good.
    """
    if not _LATIN_RE.match(token):
        return token
    if len(token) > 5 and token.endswith("ing"):
        base = token[:-3]
        # "repairing" -> "repair", "fitting" -> "fitt" -> "fit"
        if len(base) > 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    # "-es" is only a plural marker after a sibilant ("boxes", "batches").
    # Elsewhere it is just an "-s" plural on an e-final stem ("machines").
    if len(token) > 4 and token.endswith(("ses", "xes", "zes", "ches", "shes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize_stemmed(text: str) -> list[str]:
    return [stem(t) for t in normalize_text(text).split() if t]


@dataclass
class SkillMatch:
    skill_id: str
    code: str
    name: str
    raw_label: str
    matched_alias: str
    alias_language: str
    #: Token index of the first matched token, used to find nearby durations.
    position: int = 0
    confidence: str = Confidence.MEDIUM
    confidence_score: float = 0.7
    proficiency: str = Proficiency.BASIC
    source: str = SkillSource.SELF_REPORTED
    verification_status: str = VerificationStatus.SELF_DECLARED
    years_experience: float | None = None
    evidence: str = ""
    is_category: bool = False
    #: True when the alias matched contiguously and in order.
    is_exact: bool = True


@dataclass
class AliasEntry:
    tokens: tuple[str, ...]
    skill_id: str
    code: str
    name: str
    language: str
    original: str
    is_category: bool


def build_alias_index(db: Session) -> list[AliasEntry]:
    """All aliases plus skill names, ordered most-specific first."""
    rows = db.execute(
        select(
            SkillAlias.alias,
            SkillAlias.language,
            Skill.id,
            Skill.code,
            Skill.name,
            Skill.is_category,
        )
        .join(Skill, Skill.id == SkillAlias.skill_id)
        .where(Skill.is_active.is_(True))
    ).all()

    seen: set[tuple[str, tuple[str, ...]]] = set()
    entries: list[AliasEntry] = []

    def add(alias: str, language: str, skill_id: str, code: str, name: str, is_category: bool) -> None:
        tokens = tuple(tokenize_stemmed(alias))
        if not tokens or (skill_id, tokens) in seen:
            return
        seen.add((skill_id, tokens))
        entries.append(
            AliasEntry(tokens, skill_id, code, name, language, alias, bool(is_category))
        )

    for alias, language, skill_id, code, name, is_category in rows:
        add(alias, language, skill_id, code, name, is_category)

    # The skill's own name is always a valid surface form.
    for skill_id, code, name, is_category in db.execute(
        select(Skill.id, Skill.code, Skill.name, Skill.is_category).where(Skill.is_active.is_(True))
    ).all():
        add(name, "en", skill_id, code, name, is_category)

    # More tokens first (more specific), then longer text. This is what makes a
    # leaf skill win over the category that contains it.
    entries.sort(key=lambda e: (len(e.tokens), sum(len(t) for t in e.tokens)), reverse=True)
    return entries


def _find_alias(
    alias_tokens: tuple[str, ...], text_tokens: list[str], consumed: set[int]
) -> tuple[list[int], bool] | None:
    """Locate `alias_tokens` in `text_tokens`.

    Returns (matched positions, is_exact) or None. A match must contribute at
    least one token position that is not already consumed, so two skills can
    legitimately share a verb but cannot both be claimed by the same noun.
    """
    size = len(alias_tokens)
    if size == 0 or size > len(text_tokens):
        return None

    # Pass 1: contiguous, in order.
    for start in range(len(text_tokens) - size + 1):
        window = text_tokens[start : start + size]
        if list(alias_tokens) == window:
            positions = list(range(start, start + size))
            if any(p not in consumed for p in positions):
                return positions, True

    if size == 1:
        return None

    # Pass 2: all tokens inside a slightly larger window, any order.
    needed = set(alias_tokens)
    span = size + WINDOW_SLACK
    for start in range(max(1, len(text_tokens) - span + 1)):
        window = text_tokens[start : start + span]
        if not needed.issubset(window):
            continue
        positions = [
            start + offset for offset, token in enumerate(window) if token in needed
        ]
        # Keep only the first occurrence of each needed token in the window.
        chosen: list[int] = []
        claimed: set[str] = set()
        for position in positions:
            token = text_tokens[position]
            if token not in claimed:
                claimed.add(token)
                chosen.append(position)
        if any(p not in consumed for p in chosen):
            return sorted(chosen), False
    return None


def _years_near(text_tokens: list[str], position: int, window: int = 12) -> float | None:
    """Look for a duration mentioned close to a skill mention."""
    start = max(0, position - window)
    segment = text_tokens[start : position + window]
    for index, token in enumerate(segment):
        if token in YEAR_UNITS or token in MONTH_UNITS:
            for back in range(index - 1, max(-1, index - 4), -1):
                candidate = segment[back]
                if candidate.replace(".", "", 1).isdigit():
                    quantity = float(candidate)
                    return quantity if token in YEAR_UNITS else round(quantity / 12.0, 2)
    return None


def _infer_proficiency(normalized: str, years: float | None) -> tuple[str, str, float]:
    """Return (proficiency, confidence_band, confidence_score).

    Deliberately conservative: a passing mention yields `basic`, never more.
    Overstating a beneficiary's level would push them towards training they are
    not ready for, or filter out training they actually need.
    """
    has_occasional = any(cue in normalized for cue in OCCASIONAL_CUES)
    has_regular = any(cue in normalized for cue in REGULAR_CUES)

    if years is not None and years >= 6:
        proficiency = Proficiency.ADVANCED
    elif years is not None and years >= 2:
        proficiency = Proficiency.INTERMEDIATE
    elif has_regular:
        proficiency = Proficiency.INTERMEDIATE
    else:
        proficiency = Proficiency.BASIC

    if has_occasional and proficiency == Proficiency.INTERMEDIATE and years is None:
        proficiency = Proficiency.BASIC

    if years is not None:
        return proficiency, Confidence.HIGH, 0.85
    if has_regular or has_occasional:
        return proficiency, Confidence.MEDIUM, 0.7
    return proficiency, Confidence.MEDIUM, 0.65


def match_skills_in_text(
    db: Session, text: str, alias_index: list[AliasEntry] | None = None
) -> list[SkillMatch]:
    """Find every taxonomy skill mentioned in `text`.

    Category nodes (e.g. "agriculture") are returned too, flagged `is_category`,
    because they are useful context even though they are not leaf abilities.
    """
    normalized = normalize_text(text)
    if not normalized:
        return []

    index = alias_index if alias_index is not None else build_alias_index(db)
    text_tokens = tokenize_stemmed(text)
    if not text_tokens:
        return []

    consumed: set[int] = set()
    matches: list[SkillMatch] = []
    seen_skills: set[str] = set()
    mentions_certificate = any(cue in normalized for cue in CERTIFICATION_CUES)

    for entry in index:
        if entry.skill_id in seen_skills:
            continue
        found = _find_alias(entry.tokens, text_tokens, consumed)
        if found is None:
            continue
        positions, is_exact = found
        consumed.update(positions)
        seen_skills.add(entry.skill_id)

        years = _years_near(text_tokens, positions[0])
        proficiency, band, score = _infer_proficiency(normalized, years)
        matches.append(
            SkillMatch(
                skill_id=entry.skill_id,
                code=entry.code,
                name=entry.name,
                raw_label=entry.original,
                matched_alias=entry.original,
                alias_language=entry.language,
                position=positions[0],
                confidence=band,
                confidence_score=score if is_exact else round(score * 0.9, 3),
                proficiency=proficiency,
                years_experience=years,
                # A certificate mentioned in the utterance is still only a claim
                # until an assessment or an admin verifies it. Never promoted here.
                verification_status=VerificationStatus.SELF_DECLARED,
                source=SkillSource.SELF_REPORTED,
                evidence=(
                    f"Mentioned as '{entry.original}'"
                    + (f" with about {years} year(s) of experience" if years else "")
                    + (
                        "; a certificate was mentioned and still needs verification"
                        if mentions_certificate
                        else ""
                    )
                ),
                is_category=entry.is_category,
                is_exact=is_exact,
            )
        )

    matches.sort(key=lambda m: m.position)
    return matches


def normalize_label(
    db: Session, label: str, alias_index: list[AliasEntry] | None = None
) -> SkillMatch | None:
    """Resolve a single free-text skill label to one taxonomy skill."""
    found = match_skills_in_text(db, label, alias_index)
    if not found:
        return None
    # Prefer a leaf skill over a broad category when both matched.
    leaves = [m for m in found if not m.is_category]
    return (leaves or found)[0]


def normalize_labels(db: Session, labels: list[str]) -> tuple[list[str], list[str]]:
    """Batch-resolve labels. Returns (skill_codes, unresolved_labels)."""
    index = build_alias_index(db)
    codes: list[str] = []
    unresolved: list[str] = []
    for label in labels:
        match = normalize_label(db, label, index)
        if match is None:
            unresolved.append(label)
        elif match.code not in codes:
            codes.append(match.code)
    return codes, unresolved


@dataclass
class NormalizationReport:
    """Returned by POST /skills/normalize so the caller can see what happened."""

    resolved: list[SkillMatch] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
