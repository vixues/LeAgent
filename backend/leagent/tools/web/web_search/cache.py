"""Simple in-process TTL cache for web search / fetch results."""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class TtlCache(Generic[T]):
    """Thread-safe dict with per-entry TTL (monotonic clock)."""

    def __init__(self, *, default_ttl_sec: float = 900.0, max_entries: int = 256) -> None:
        self._default_ttl = max(0.0, float(default_ttl_sec))
        self._max_entries = max(1, int(max_entries))
        self._lock = Lock()
        self._store: dict[str, tuple[float, T]] = {}

    def get(self, key: str) -> T | None:
        now = time.monotonic()
        with self._lock:
            hit = self._store.get(key)
            if hit is None:
                return None
            exp, value = hit
            if now >= exp:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: T, *, ttl_sec: float | None = None) -> None:
        ttl = self._default_ttl if ttl_sec is None else max(0.0, float(ttl_sec))
        if ttl <= 0:
            return
        exp = time.monotonic() + ttl
        with self._lock:
            if len(self._store) >= self._max_entries and key not in self._store:
                # Drop oldest by expiry
                oldest = min(self._store.items(), key=lambda kv: kv[1][0])[0]
                self._store.pop(oldest, None)
            self._store[key] = (exp, value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Module-level caches shared across tool calls in-process.
_search_cache: TtlCache[dict[str, Any]] | None = None
_fetch_cache: TtlCache[dict[str, Any]] | None = None


def get_search_cache(*, ttl_minutes: float = 15.0) -> TtlCache[dict[str, Any]]:
    global _search_cache
    if _search_cache is None:
        _search_cache = TtlCache(default_ttl_sec=max(0.0, ttl_minutes) * 60.0)
    return _search_cache


def get_fetch_cache(*, ttl_minutes: float = 15.0) -> TtlCache[dict[str, Any]]:
    global _fetch_cache
    if _fetch_cache is None:
        _fetch_cache = TtlCache(default_ttl_sec=max(0.0, ttl_minutes) * 60.0)
    return _fetch_cache


def reset_web_caches() -> None:
    """Test / settings-reload helper."""
    global _search_cache, _fetch_cache
    if _search_cache is not None:
        _search_cache.clear()
    if _fetch_cache is not None:
        _fetch_cache.clear()
    _search_cache = None
    _fetch_cache = None
