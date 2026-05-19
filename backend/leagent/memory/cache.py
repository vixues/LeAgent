"""Tiered caching layer for the agent memory stack.

Provides L1 (in-process LRU) and L2 (Redis) caching for embeddings,
recall results, and memory metadata. Eliminates redundant embedding
API calls and store lookups when the same memories are accessed
across turns.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from leagent.services.cache.service import CacheService

logger = logging.getLogger(__name__)

_DEFAULT_L1_SIZE = 512
_DEFAULT_L2_TTL = 3600


class MemoryCache:
    """Two-tier cache for memory system lookups.

    L1: In-process LRU — sub-millisecond lookups for hot data.
    L2: Redis — shared across workers, ~1ms lookups.
    """

    def __init__(
        self,
        *,
        l1_max_size: int = _DEFAULT_L1_SIZE,
        l2_service: "CacheService | None" = None,
        l2_ttl: int = _DEFAULT_L2_TTL,
        namespace: str = "memory",
    ) -> None:
        self._l1: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._l1_max = l1_max_size
        self._l2 = l2_service
        self._l2_ttl = l2_ttl
        self._namespace = namespace
        self._hits = 0
        self._misses = 0

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @staticmethod
    def cache_key(prefix: str, text: str, model: str = "") -> str:
        raw = f"{prefix}:{model}:{text}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    async def get(self, key: str) -> Any | None:
        if key in self._l1:
            self._l1.move_to_end(key)
            self._hits += 1
            return self._l1[key][0]

        if self._l2 is not None:
            try:
                val = await self._l2.get(
                    f"{self._namespace}:{key}",
                    namespace=self._namespace,
                )
                if val is not None:
                    self._set_l1(key, val)
                    self._hits += 1
                    return val
            except Exception:
                pass

        self._misses += 1
        return None

    async def set(self, key: str, value: Any, *, ttl: int | None = None) -> None:
        self._set_l1(key, value)

        if self._l2 is not None:
            try:
                await self._l2.set(
                    f"{self._namespace}:{key}",
                    value,
                    namespace=self._namespace,
                    ttl=ttl or self._l2_ttl,
                )
            except Exception as exc:
                logger.debug("memory_cache_l2_write_failed: %s", exc)

    async def invalidate(self, key: str) -> None:
        self._l1.pop(key, None)
        if self._l2 is not None:
            try:
                await self._l2.delete(
                    f"{self._namespace}:{key}",
                    namespace=self._namespace,
                )
            except Exception:
                pass

    def clear_l1(self) -> None:
        self._l1.clear()

    def _set_l1(self, key: str, value: Any) -> None:
        if key in self._l1:
            self._l1.move_to_end(key)
            self._l1[key] = (value, time.monotonic())
        else:
            self._l1[key] = (value, time.monotonic())
            if len(self._l1) > self._l1_max:
                self._l1.popitem(last=False)


class EmbeddingCache(MemoryCache):
    """Specialized cache for embedding vectors.

    Keyed by ``sha256(text + model_name)`` so identical text embedded
    with the same model always cache-hits.
    """

    def __init__(
        self,
        *,
        l1_max_size: int = 1024,
        l2_service: "CacheService | None" = None,
        l2_ttl: int = 7200,
    ) -> None:
        super().__init__(
            l1_max_size=l1_max_size,
            l2_service=l2_service,
            l2_ttl=l2_ttl,
            namespace="embeddings",
        )

    async def get_embedding(
        self,
        text: str,
        model: str,
    ) -> list[float] | None:
        key = self.cache_key("emb", text, model)
        result = await self.get(key)
        if result is not None and isinstance(result, list):
            return result
        return None

    async def set_embedding(
        self,
        text: str,
        model: str,
        vector: list[float],
    ) -> None:
        key = self.cache_key("emb", text, model)
        await self.set(key, vector)


class RecallCache(MemoryCache):
    """Cache for recall query results.

    Short TTL since recall results are query-dependent, but saves
    redundant store lookups when the same query fires within a turn.
    """

    def __init__(
        self,
        *,
        l1_max_size: int = 256,
        l2_service: "CacheService | None" = None,
    ) -> None:
        super().__init__(
            l1_max_size=l1_max_size,
            l2_service=l2_service,
            l2_ttl=300,
            namespace="recall",
        )
