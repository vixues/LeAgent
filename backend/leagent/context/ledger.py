"""Structured audit ledger for context assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "LedgerRow",
    "ContextLedger",
]


@dataclass(slots=True)
class LedgerRow:
    source_id: str
    bytes: int
    tokens: int
    cache_hit: bool
    skip_reason: str
    truncated: bool
    dropped: bool
    render_target: str
    priority: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ContextLedger:
    rows: list[LedgerRow] = field(default_factory=list)
    stable_hash: str = ""
    project_memory_hash: str = ""
    full_hash: str = ""
    duration_ms: int = 0
    cache_stats: dict[str, int] = field(default_factory=dict)

    def to_structlog_dict(self) -> dict[str, Any]:
        return {
            "stable_hash": self.stable_hash,
            "project_memory_hash": self.project_memory_hash,
            "full_hash": self.full_hash,
            # Avoid ``duration_ms`` — same key as HTTP access logs in one request can confuse render/merge.
            "prepare_duration_ms": self.duration_ms,
            "cache_stats": self.cache_stats,
            "sources": [
                {
                    "id": r.source_id,
                    "bytes": r.bytes,
                    "tokens": r.tokens,
                    "hit": r.cache_hit,
                    "skip": r.skip_reason,
                    "truncated": r.truncated,
                    "dropped": r.dropped,
                    "target": r.render_target,
                }
                for r in self.rows
            ],
        }
