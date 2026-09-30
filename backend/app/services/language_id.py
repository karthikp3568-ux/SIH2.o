"""Language identification, normalisation and code-switch detection.

Approach: Unicode script detection narrows the candidate set, then high-frequency
marker words disambiguate languages that share a script (Hindi vs Marathi in
Devanagari) and detect romanised Indic input typed in Latin script.

This is a deliberate, inspectable heuristic rather than a statistical model: it
is fast, needs no model download, and its confidence is honest - when the signal
is weak it *says* the confidence is low, which is what triggers confirmation in
the conversation engine.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from ..core.enums import Language

#: Unicode ranges -> the languages written in that script.
SCRIPT_RANGES: list[tuple[int, int, str, tuple[str, ...]]] = [
    (0x0900, 0x097F, "Devanagari", (Language.HI, Language.MR)),
    (0x0980, 0x09FF, "Bengali", (Language.BN,)),
    (0x0A00, 0x0A7F, "Gurmukhi", (Language.PA,)),
    (0x0A80, 0x0AFF, "Gujarati", (Language.GU,)),
    (0x0B00, 0x0B7F, "Oriya", (Language.OR,)),
    (0x0B80, 0x0BFF, "Tamil", (Language.TA,)),
    (0x0C00, 0x0C7F, "Telugu", (Language.TE,)),
    (0x0C80, 0x0CFF, "Kannada", (Language.KN,)),
    (0x0D00, 0x0D7F, "Malayalam", (Language.ML,)),
    (0x0041, 0x007A, "Latin", (Language.EN,)),
]

#: Words common in one Devanagari language and rare in the other.
DEVANAGARI_MARKERS: dict[str, tuple[str, ...]] = {
    Language.MR: ("आहे", "मला", "माझ", "काम करतो", "करतो", "नाही", "शेती", "पण", "मी"),
    Language.HI: ("है", "हूँ", "हूं", "मुझे", "मेरा", "करता", "नहीं", "खेती", "लेकिन", "मैं"),
}

#: Romanised Indic markers, used when the script is Latin.
ROMANISED_MARKERS: dict[str, tuple[str, ...]] = {
    Language.HI: (
        "mujhe", "mera", "meri", "hai", "hoon", "hun", "nahi", "nahin", "kaam",
        "karta", "karti", "chahta", "chahiye", "lekin", "aur", "kheti", "paise",
        "zyada", "jyada", "thik", "sakta", "gaon", "door",
    ),
    Language.MR: ("mala", "majha", "aahe", "karto", "shetat", "shetkari", "pan", "nahi", "kam"),
    Language.TA: ("naan", "enakku", "vela", "velai", "irukku", "mudiyathu", "venum", "pudikkum"),
    Language.TE: ("naaku", "nenu", "pani", "kavali", "cheyyanu", "ledu"),
}

_PUNCT_RE = re.compile(r"[^\w\sऀ-෿]", re.UNICODE)
_WS_RE = re.compile(r"\s+")

#: Number words -> digits, so "do saal" and "दो साल" both yield 2.
NUMBER_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "half": 1,
    "ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5, "panch": 5, "chhe": 6,
    "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10, "baarah": 12, "barah": 12,
    "pandrah": 15, "bees": 20,
    # Devanagari. "तीन" and "चार" are spelled the same in Hindi and Marathi, so
    # they appear once; the Marathi-only forms follow.
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6,
    "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "बारह": 12, "पंद्रह": 15, "बीस": 20,
    "दोन": 2, "पाच": 5,
    # Tamil
    "ஒன்று": 1, "இரண்டு": 2, "மூன்று": 3, "நான்கு": 4, "ஐந்து": 5, "பத்து": 10,
}

#: Indic digit forms mapped to ASCII.
_DIGIT_TRANSLATION = {
    ord(c): ord(str(i))
    for block_start in (0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66, 0x0BE6, 0x0C66, 0x0CE6, 0x0D66)
    for i, c in enumerate(chr(block_start + n) for n in range(10))
}


@dataclass
class LanguageDetection:
    language: str
    confidence: float
    scripts: dict[str, int] = field(default_factory=dict)
    is_code_switched: bool = False
    detail: str = ""


def _script_of(char: str) -> str | None:
    code = ord(char)
    for start, end, script, _ in SCRIPT_RANGES:
        if start <= code <= end:
            return script
    if char.isalpha():
        return "Latin" if code < 0x0250 else None
    return None


def normalize_text(text: str) -> str:
    """Canonical form used for keyword matching and storage.

    NFC-normalises, maps Indic digits to ASCII, lowercases, strips punctuation
    and collapses whitespace. Script and word order are preserved so the
    normalised text is still readable by a human reviewer.
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text).translate(_DIGIT_TRANSLATION)
    normalized = _PUNCT_RE.sub(" ", normalized.lower())
    return _WS_RE.sub(" ", normalized).strip()


def detect_language(text: str, hint: str | None = None) -> LanguageDetection:
    """Identify the language, its confidence, and whether scripts are mixed."""
    if not text or not text.strip():
        return LanguageDetection(
            language=hint or Language.EN, confidence=0.0, detail="empty input"
        )

    counts: dict[str, int] = {}
    for char in text:
        script = _script_of(char)
        if script:
            counts[script] = counts.get(script, 0) + 1

    if not counts:
        return LanguageDetection(
            language=hint or Language.EN, confidence=0.2, detail="no alphabetic characters"
        )

    total = sum(counts.values())
    dominant_script, dominant_count = max(counts.items(), key=lambda kv: kv[1])
    share = dominant_count / total

    # Mixed scripts with a meaningful minority share = code switching. Below 10%
    # it is usually a stray English technical word, which we do not flag.
    minority = total - dominant_count
    is_mixed = len(counts) > 1 and (minority / total) >= 0.10

    lowered = normalize_text(text)
    candidates = next(
        (langs for _, _, script, langs in SCRIPT_RANGES if script == dominant_script), (Language.EN,)
    )

    language = candidates[0]
    confidence = min(0.95, 0.55 + 0.4 * share)
    detail = f"{dominant_script} script, {share:.0%} of characters"

    if dominant_script == "Devanagari":
        scores = {
            lang: sum(1 for marker in markers if marker in lowered)
            for lang, markers in DEVANAGARI_MARKERS.items()
        }
        best_lang, best_score = max(scores.items(), key=lambda kv: kv[1])
        if best_score > 0:
            runner_up = max(v for k, v in scores.items() if k != best_lang)
            language = best_lang
            # A clear margin between the two raises confidence; a tie lowers it.
            confidence = min(0.95, confidence + 0.1 * (best_score - runner_up))
            detail += f"; {best_lang} marker words matched ({best_score})"
        else:
            language = Language.HI
            confidence = min(confidence, 0.6)
            detail += "; no Hindi/Marathi marker words, defaulting to Hindi"

    elif dominant_script == "Latin":
        tokens = set(lowered.split())
        romanised = {
            lang: len(tokens & set(markers)) for lang, markers in ROMANISED_MARKERS.items()
        }
        best_lang, best_score = max(romanised.items(), key=lambda kv: kv[1])
        if best_score >= 2:
            language = best_lang
            confidence = min(0.85, 0.5 + 0.1 * best_score)
            detail = f"Latin script with {best_score} romanised {best_lang} marker words"
            is_mixed = True  # romanised Indic in Latin script is itself a mix
        else:
            language = Language.EN
            detail = f"Latin script, {share:.0%} of characters"

    if hint and hint == language:
        confidence = min(0.98, confidence + 0.05)
    elif hint and hint != language and share < 0.6:
        # Respect the user's declared language when our own signal is weak.
        detail += f"; weak signal, deferring to declared language '{hint}'"
        language, confidence = hint, max(0.4, confidence - 0.15)

    return LanguageDetection(
        language=language,
        confidence=round(confidence, 3),
        scripts=counts,
        is_code_switched=is_mixed,
        detail=detail,
    )


def extract_number(text: str) -> float | None:
    """First numeric quantity in the text, digits or number words."""
    normalized = normalize_text(text)
    digit_match = re.search(r"\b(\d+(?:\.\d+)?)\b", normalized)
    if digit_match:
        return float(digit_match.group(1))
    for token in normalized.split():
        if token in NUMBER_WORDS:
            return float(NUMBER_WORDS[token])
    return None
