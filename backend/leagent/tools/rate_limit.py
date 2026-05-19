"""Simple per-process sliding-window limits for tool execution."""

from __future__ import annotations

import os
import time
from collections import defaultdict


class SlidingWindowRateLimiter:
    """Fixed-window counter per arbitrary string key (e.g. ``user_id:tool_name``)."""

    __slots__ = ("_hits", "max_calls", "window_sec")

    def __init__(self, *, max_calls: int, window_sec: float) -> None:
        self.max_calls = max_calls
        self.window_sec = window_sec
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_sec
        seq = self._hits[key]
        seq[:] = [t for t in seq if t >= cutoff]
        if len(seq) >= self.max_calls:
            return False
        seq.append(now)
        return True


def tool_rate_limit_from_env() -> tuple[SlidingWindowRateLimiter | None, int]:
    """Parse ``LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE`` (0 or unset = disabled)."""
    raw = (os.getenv("LEAGENT_TOOL_RATE_LIMIT_PER_MINUTE") or "").strip()
    if not raw:
        return None, 60
    try:
        n = int(raw)
    except ValueError:
        return None, 60
    if n <= 0:
        return None, 60
    return SlidingWindowRateLimiter(max_calls=n, window_sec=60.0), 60


__all__ = ["SlidingWindowRateLimiter", "tool_rate_limit_from_env"]
