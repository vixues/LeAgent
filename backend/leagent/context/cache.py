"""Source-level memoisation with scope-aware TTL."""

from __future__ import annotations

import time
from dataclasses import dataclass

from leagent.context.types import ContextBlock, ContextScope

__all__ = [
    "CacheEntry",
    "SourceCache",
]


@dataclass(slots=True)
class CacheEntry:
    block: ContextBlock
    created_at: float
    hit_count: int = 0


class SourceCache:
    """Per-source memo keyed by invalidation_key with scope-aware TTL."""

    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._hits: int = 0
        self._misses: int = 0

    def get(self, key: str, scope: ContextScope) -> ContextBlock | None:
        """Return cached block if still valid for the scope."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        if scope == ContextScope.TURN:
            self._misses += 1
            return None
        entry.hit_count += 1
        self._hits += 1
        return entry.block

    def put(self, key: str, block: ContextBlock) -> None:
        self._store[key] = CacheEntry(block=block, created_at=time.monotonic())

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "size": len(self._store)}
