"""Embedding providers.

DEFAULT: `LocalHashingEmbedding`. Be precise about what this is - it is a
deterministic hashed n-gram vectoriser (word unigrams + bigrams + character
4-grams, signed hashing, sublinear TF, L2 normalised). It captures lexical and
morphological similarity, including across transliteration variants, and it
needs no model download and no network. It is NOT a neural sentence embedding
and does not capture deep paraphrase.

Two things make retrieval behave semantically despite that:
  1. queries are expanded through the skill-taxonomy alias graph before
     embedding (see services/retrieval.py), and
  2. vector similarity is only ~60% of the retrieval score, blended with BM25
     and then hard-filtered on structured metadata.

Set EMBEDDING_PROVIDER=sentence_transformers for true neural embeddings once
the optional dependency is installed.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

import numpy as np

from ..config import get_settings
from .base import EmbeddingProvider, ProviderNotConfigured, ProviderStatus

_TOKEN_RE = re.compile(r"[\wऀ-෿]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Unicode-aware word tokenizer covering Latin and Indic scripts."""
    return _TOKEN_RE.findall((text or "").lower())


def _hash_index(feature: str, dim: int) -> tuple[int, float]:
    """Map a feature to a bucket and a sign (signed hashing reduces collision bias)."""
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "big")
    return value % dim, 1.0 if (value >> 63) & 1 else -1.0


class LocalHashingEmbedding:
    """Offline deterministic vectoriser. No model files, no network."""

    name = "local_hashing"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def status(self) -> ProviderStatus:
        return ProviderStatus(
            name=self.name,
            kind="embedding",
            configured=True,
            detail=(
                f"Deterministic hashed n-gram vectoriser ({self.dim}d). "
                "Offline; lexical/morphological similarity, not neural paraphrase."
            ),
            is_offline_default=True,
        )

    def _features(self, text: str) -> dict[str, float]:
        tokens = tokenize(text)
        counts: dict[str, float] = {}
        for token in tokens:
            counts[f"w:{token}"] = counts.get(f"w:{token}", 0.0) + 1.0
            # Character 4-grams give partial credit for spelling and
            # transliteration variants ("borewell" / "bore well" / "borwell").
            if len(token) > 4:
                padded = f"^{token}$"
                for i in range(len(padded) - 3):
                    gram = padded[i : i + 4]
                    counts[f"c:{gram}"] = counts.get(f"c:{gram}", 0.0) + 0.5
        for a, b in zip(tokens, tokens[1:], strict=False):
            counts[f"b:{a}_{b}"] = counts.get(f"b:{a}_{b}", 0.0) + 1.5
        return counts

    def embed_one(self, text: str) -> list[float]:
        vector = np.zeros(self.dim, dtype=np.float32)
        for feature, count in self._features(text).items():
            index, sign = _hash_index(feature, self.dim)
            # Sublinear TF dampens the effect of repeated words.
            vector[index] += sign * (1.0 + math.log(count)) if count > 1 else sign * count
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class SentenceTransformerEmbedding:
    """Optional neural provider. Requires `pip install sentence-transformers`."""

    name = "sentence_transformers"

    def __init__(self, model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2") -> None:
        self.model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - optional path
            raise ProviderNotConfigured(
                "sentence-transformers is not installed. Install it or set "
                "EMBEDDING_PROVIDER=local_hashing."
            ) from exc
        self._model = SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def status(self) -> ProviderStatus:  # pragma: no cover - optional path
        return ProviderStatus(
            name=self.name,
            kind="embedding",
            configured=True,
            detail=f"Neural multilingual embeddings via {self.model_name} ({self.dim}d).",
        )

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover - optional path
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]

    def embed_one(self, text: str) -> list[float]:  # pragma: no cover - optional path
        return self.embed([text])[0]


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "sentence_transformers":
        try:
            return SentenceTransformerEmbedding()
        except ProviderNotConfigured:
            # Degrade rather than break the app; the status endpoint reports it.
            return LocalHashingEmbedding(dim=settings.embedding_dim)
    return LocalHashingEmbedding(dim=settings.embedding_dim)


def cosine_similarity(a: list[float] | np.ndarray, b: list[float] | np.ndarray) -> float:
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    if va.size == 0 or vb.size == 0 or va.size != vb.size:
        return 0.0
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)
