"""Ephemeral per-task scratchpad with tool history.

Two focused primitives:

* :class:`ToolHistory` — append-only ring buffer of tool invocations.
* :class:`Scratchpad` — key/value map with TTL for intermediate results.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from cachetools import TTLCache

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 60 * 60 * 2
DEFAULT_TOOL_HISTORY_LIMIT = 50


def _now() -> float:
    return time.time()


@dataclass(slots=True)
class ToolInvocation:
    """One entry in the tool history ring buffer."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    result_preview: str | None = None
    success: bool = True
    error: str | None = None
    duration_ms: int | None = None
    timestamp: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result_preview": self.result_preview,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolInvocation:
        return cls(
            name=str(data.get("name") or "unknown"),
            arguments=dict(data.get("arguments") or {}),
            result_preview=(
                str(data["result_preview"]) if data.get("result_preview") else None
            ),
            success=bool(data.get("success", True)),
            error=str(data["error"]) if data.get("error") else None,
            duration_ms=(
                int(data["duration_ms"]) if data.get("duration_ms") is not None else None
            ),
            timestamp=float(data.get("timestamp") or _now()),
        )


class WorkingScratchpad:
    """In-memory per-task scratchpad + tool history."""

    def __init__(
        self,
        *,
        redis: Any | None = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        tool_history_limit: int = DEFAULT_TOOL_HISTORY_LIMIT,
    ) -> None:
        self._ttl = max(60, int(ttl_seconds))
        self._limit = max(1, int(tool_history_limit))
        self._store: TTLCache[str, dict[str, Any]] = TTLCache(
            maxsize=10_000, ttl=float(self._ttl)
        )
        self._tools: TTLCache[str, list[dict[str, Any]]] = TTLCache(
            maxsize=10_000, ttl=float(self._ttl)
        )

    # -- scratchpad -----------------------------------------------------

    async def set(
        self,
        task_id: str | UUID,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        tid = str(task_id)
        blob = json.dumps(value, default=str)
        bucket = dict(self._store.get(tid, {}))
        bucket[key] = blob
        self._store[tid] = bucket

    async def get(self, task_id: str | UUID, key: str) -> Any:
        blob = self._store.get(str(task_id), {}).get(key)
        return _decode(blob)

    async def all(self, task_id: str | UUID) -> dict[str, Any]:
        store = self._store.get(str(task_id), {})
        return {k: _decode(v) for k, v in store.items()}

    async def clear(self, task_id: str | UUID) -> None:
        self._store.pop(str(task_id), None)
        self._tools.pop(str(task_id), None)

    # -- tool history ---------------------------------------------------

    async def append_tool(
        self, task_id: str | UUID, invocation: ToolInvocation
    ) -> None:
        tid = str(task_id)
        queue = list(self._tools.get(tid, []))
        queue.append(invocation.to_dict())
        if len(queue) > self._limit:
            del queue[: len(queue) - self._limit]
        self._tools[tid] = queue

    async def tool_history(
        self, task_id: str | UUID, *, limit: int | None = None
    ) -> list[ToolInvocation]:
        queue = self._tools.get(str(task_id), [])
        slice_ = queue[-limit:] if limit else queue
        return [ToolInvocation.from_dict(entry) for entry in slice_]


def _decode(blob: Any) -> Any:
    if blob is None:
        return None
    text = blob if isinstance(blob, str) else blob.decode()
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


__all__ = ["ToolInvocation", "WorkingScratchpad"]
