"""Embeddings behind one interface. Business code never imports a provider SDK (CLAUDE.md §3)."""

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.ai.routing import provider_routing
from app.core.config import get_settings


class EmbeddingError(Exception):
    """The embedding provider failed or returned something unusable."""


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    input_tokens: int
    cost_eur: float


class Embedder(Protocol):
    @property
    def model(self) -> str: ...

    def embed(self, texts: list[str]) -> EmbeddingResult: ...


def _words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]{2,}", text)


class HashEmbedder:
    """Deterministic bag-of-words hashing into ``dim`` buckets (signed, L2-normalized).

    Texts that share words get a high cosine similarity, which is enough to test retrieval
    logic offline. It is NOT a semantic model and must never run in production.
    """

    model = "hash-embedder-v1"

    def __init__(self, dim: int) -> None:
        self._dim = dim

    def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors = []
        for text in texts:
            vec = [0.0] * self._dim
            for word in _words(text):
                h = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "big")
                vec[h % self._dim] += 1.0 if (h >> 63) & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return EmbeddingResult(vectors, self.model, sum(len(_words(t)) for t in texts), 0.0)


class LiteLLMEmbedder:
    def __init__(self, model: str, dim: int, batch_size: int = 64) -> None:
        self._model, self._dim, self._batch = model, dim, batch_size

    @property
    def model(self) -> str:
        return self._model

    def embed(self, texts: list[str]) -> EmbeddingResult:
        import litellm  # imported lazily: heavy, and only needed when a real model is set

        vectors: list[list[float]] = []
        tokens, cost = 0, 0.0
        for i in range(0, len(texts), self._batch):
            try:
                resp = litellm.embedding(
                    model=self._model,
                    input=texts[i : i + self._batch],
                    timeout=60,
                    num_retries=2,
                    **provider_routing(self._model),
                )
            except Exception as exc:
                raise EmbeddingError(f"embedding provider error: {exc}") from exc
            vectors.extend(item["embedding"] for item in resp.data)
            tokens += int(getattr(resp.usage, "prompt_tokens", 0) or 0)
            cost += float((getattr(resp, "_hidden_params", {}) or {}).get("response_cost") or 0.0)
        s = get_settings()
        if not cost:  # OpenRouter reports no cost for embeddings: the known price, then
            cost = tokens / 1_000_000 * s.embedding_price_usd_per_million
        return EmbeddingResult(vectors, self._model, tokens, cost * s.usd_eur_rate)


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_model:
        return LiteLLMEmbedder(s.embedding_model, s.embedding_dim)
    if s.environment == "production":
        raise EmbeddingError("EMBEDDING_MODEL must be set in production")
    return HashEmbedder(s.embedding_dim)
