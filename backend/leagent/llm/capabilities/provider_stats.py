"""Provider performance store — production feedback for self-optimization.

Records the live outcome of every generation attempt (success / failure,
latency, and — when an evaluator scores the asset — perceptual quality) keyed
by ``(task, provider)``. The :class:`CapabilityRouter` consults the derived
*reliability score* to bias candidate ranking within a cost tier, so providers
that perform well on real traffic are preferred over ones that fail or produce
low-quality output. This is a lightweight, in-process bandit — no external
store required — and is safe to use credential-free (it simply has no data).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

__all__ = ["ProviderStat", "ProviderStatsStore", "get_provider_stats", "reset_provider_stats"]

#: EMA smoothing factor for the rolling quality average.
_QUALITY_ALPHA = 0.3
#: Neutral reliability for a provider we have never observed — keeps ranking
#: stable (cost tier + registration order) until real data accrues.
NEUTRAL_SCORE = 0.5


@dataclass
class ProviderStat:
    """Rolling performance counters for one ``(task, provider)`` pair."""

    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    quality_ema: float | None = None
    samples: int = 0

    @property
    def attempts(self) -> int:
        return self.successes + self.failures

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 1.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.successes if self.successes else 0.0

    def reliability(self) -> float:
        """A 0..1 score combining success rate and (optional) quality.

        With no quality signal it is the raw success rate; once quality is
        observed the two are blended so a provider that "succeeds" but produces
        poor assets is ranked below a reliable, high-quality one.
        """
        if self.attempts == 0:
            return NEUTRAL_SCORE
        if self.quality_ema is None:
            return self.success_rate
        return 0.5 * self.success_rate + 0.5 * self.quality_ema

    def to_dict(self) -> dict[str, Any]:
        return {
            "successes": self.successes,
            "failures": self.failures,
            "attempts": self.attempts,
            "success_rate": round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "quality_ema": round(self.quality_ema, 4) if self.quality_ema is not None else None,
            "reliability": round(self.reliability(), 4),
            "samples": self.samples,
        }


class ProviderStatsStore:
    """Thread-safe in-memory store of per-provider performance."""

    def __init__(self) -> None:
        self._stats: dict[tuple[str, str], ProviderStat] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(task: str, provider: str) -> tuple[str, str]:
        return (str(task), str(provider))

    def record_attempt(
        self,
        task: str,
        provider: str,
        *,
        success: bool,
        latency_ms: float | None = None,
    ) -> None:
        key = self._key(task, provider)
        with self._lock:
            stat = self._stats.setdefault(key, ProviderStat())
            if success:
                stat.successes += 1
                if latency_ms is not None:
                    stat.total_latency_ms += max(0.0, float(latency_ms))
            else:
                stat.failures += 1

    def record_quality(self, task: str, provider: str, score: float) -> None:
        """Fold a perceptual/eval quality score (0..1) into the rolling average."""
        try:
            value = max(0.0, min(float(score), 1.0))
        except (TypeError, ValueError):
            return
        key = self._key(task, provider)
        with self._lock:
            stat = self._stats.setdefault(key, ProviderStat())
            if stat.quality_ema is None:
                stat.quality_ema = value
            else:
                stat.quality_ema = (1 - _QUALITY_ALPHA) * stat.quality_ema + _QUALITY_ALPHA * value
            stat.samples += 1

    def reliability(self, task: str, provider: str) -> float:
        with self._lock:
            stat = self._stats.get(self._key(task, provider))
            return stat.reliability() if stat is not None else NEUTRAL_SCORE

    def get(self, task: str, provider: str) -> ProviderStat | None:
        with self._lock:
            stat = self._stats.get(self._key(task, provider))
            return ProviderStat(**vars(stat)) if stat is not None else None

    def snapshot(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {f"{t}:{p}": s.to_dict() for (t, p), s in self._stats.items()}

    def clear(self) -> None:
        with self._lock:
            self._stats.clear()


_GLOBAL_STORE: ProviderStatsStore | None = None


def get_provider_stats() -> ProviderStatsStore:
    """Return the process-wide provider stats store (lazy singleton)."""
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        _GLOBAL_STORE = ProviderStatsStore()
    return _GLOBAL_STORE


def reset_provider_stats() -> None:
    """Reset the global store (test isolation)."""
    if _GLOBAL_STORE is not None:
        _GLOBAL_STORE.clear()
