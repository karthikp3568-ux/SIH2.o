"""Document chunking.

Chunks are built from structured records, not scraped PDFs, so each one is
small, self-contained and already carries the metadata retrieval filters on.
Where free text is long it is split on sentence boundaries with a small overlap
so a fact is not cut in half between chunks.
"""

from __future__ import annotations

import hashlib
import re

DEFAULT_MAX_CHARS = 750
DEFAULT_OVERLAP = 120

_SENTENCE_RE = re.compile(r"(?<=[.!?।])\s+")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(
    text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    """Split text into overlapping chunks, preferring sentence boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    sentences = [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        # A single over-long sentence is hard-split rather than dropped.
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(sentence), max_chars - overlap):
                chunks.append(sentence[start : start + max_chars].strip())
            continue
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap else ""
            current = f"{tail} {sentence}".strip()

    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c]


def estimate_tokens(text: str) -> int:
    """Rough token count. Indic scripts tokenize less efficiently than Latin."""
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = len(text) - ascii_chars
    return int(ascii_chars / 4 + other / 2) + 1
