"""Embedding provider protocol used by the agent memory stack.

The cognitive stores (episodic, semantic, procedural) all need to turn
arbitrary text into dense vectors. Rather than letting each store pull in
:class:`LLMService` directly, they talk to an :class:`EmbeddingProvider`.

``LLMServiceEmbeddingProvider`` is the production implementation: it
delegates to :meth:`LLMService.embed` with an in-memory LRU cache.

``NullEmbeddingProvider`` returns zero vectors, which disables semantic
search but lets the BM25 / ILIKE fallback path continue to work.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any, Iterable, Protocol, runtime_checkable

from cachetools import LRUCache

if TYPE_CHECKING:
    from leagent.llm import LLMService

logger = logging.getLogger(__name__)

_CACHE_MAX_SIZE = 10_000


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Async-only embedding provider used by memory stores."""

    dimension: int

    async def embed(self, texts: Iterable[str]) -> list[list[float]]:
        ...

    async def embed_one(self, text: str) -> list[float]:
        ...


class NullEmbeddingProvider:
    """No-op provider that returns zero vectors."""

    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension
        self.last_degraded = True
        self.last_error: str | None = "null_embedding_provider"

    async def embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [[0.0] * self.dimension for _ in texts]

    async def embed_one(self, text: str) -> list[float]:
        return [0.0] * self.dimension


class LLMServiceEmbeddingProvider:
    """Production embedding provider backed by :class:`LLMService`.

    Uses an in-memory LRU cache keyed by ``(model, text)`` SHA-256.
    """

    def __init__(
        self,
        llm_service: "LLMService",
        *,
        redis: Any | None = None,
        model: str | None = None,
        dimension: int = 1024,
        ttl_seconds: int = 0,
    ) -> None:
        self._llm = llm_service
        self._model = model
        self.dimension = dimension
        self.last_degraded = False
        self.last_error: str | None = None
        self._cache: LRUCache[str, list[float]] = LRUCache(maxsize=_CACHE_MAX_SIZE)

    @property
    def model(self) -> str:
        return self._model or "default"

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256(
            (self.model + "\x00" + text).encode("utf-8")
        ).hexdigest()
        return digest

    async def embed(self, texts: Iterable[str]) -> list[list[float]]:
        items = [t or "" for t in texts]
        if not items:
            return []

        cached: list[list[float] | None] = []
        for t in items:
            key = self._cache_key(t)
            cached.append(self._cache.get(key))

        missing = [i for i, v in enumerate(cached) if v is None]
        if not missing:
            self.last_degraded = False
            self.last_error = None
            return [v for v in cached if v is not None]

        to_embed = [items[i] for i in missing]
        try:
            response = await self._llm.embed(to_embed, model=self._model)
        except Exception as exc:  # noqa: BLE001
            logger.warning("embedding_backend_failed: %s", exc)
            self.last_degraded = True
            self.last_error = str(exc)
            raise RuntimeError(f"embedding_backend_failed: {exc}") from exc

        vectors = list(response.embeddings or [])
        if vectors and len(vectors[0]) != self.dimension:
            self.dimension = len(vectors[0])

        for pos, idx in enumerate(missing):
            if pos >= len(vectors):
                self.last_degraded = True
                self.last_error = "embedding_response_incomplete"
                raise RuntimeError("embedding_response_incomplete")
            vec = vectors[pos]
            cached[idx] = vec
            self._cache[self._cache_key(items[idx])] = vec

        self.last_degraded = False
        self.last_error = None

        out: list[list[float]] = []
        for v in cached:
            if v is None:
                self.last_degraded = True
                self.last_error = "embedding_cache_incomplete"
                raise RuntimeError("embedding_cache_incomplete")
            out.append(v)
        return out

    async def embed_one(self, text: str) -> list[float]:
        result = await self.embed([text])
        if not result:
            raise RuntimeError("embedding_empty")
        return result[0]


__all__ = [
    "EmbeddingProvider",
    "LLMServiceEmbeddingProvider",
    "NullEmbeddingProvider",
]
