"""Prompt queue protocol.

A ``PromptQueue`` accepts :class:`PromptItem` jobs, hands them to worker
consumers via :meth:`get`, and records :class:`PromptHistoryEntry`
completion records.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4


@dataclass
class PromptItem:
    """A queued workflow run."""

    prompt_id: str
    flow_id: str
    user_id: str | None
    inputs: dict[str, Any]
    trigger_type: str = "manual"
    priority: int = 5  # lower = higher priority
    extra_data: dict[str, Any] = field(default_factory=dict)
    enqueued_at: float = 0.0
    attempts: int = 0

    @classmethod
    def new(cls, **kwargs: Any) -> "PromptItem":
        if "prompt_id" not in kwargs:
            kwargs["prompt_id"] = str(uuid4())
        import time
        kwargs.setdefault("enqueued_at", time.time())
        return cls(**kwargs)


@dataclass
class PromptHistoryEntry:
    prompt_id: str
    status: str
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    finished_at: float = 0.0


@runtime_checkable
class PromptQueue(Protocol):
    async def put(self, item: PromptItem) -> None: ...

    async def get(self, *, timeout: float | None = None) -> PromptItem | None: ...

    async def task_done(self, item: PromptItem, history: PromptHistoryEntry) -> None: ...

    async def history(self, prompt_id: str) -> PromptHistoryEntry | None: ...

    async def wipe(self) -> None: ...

    async def size(self) -> int: ...

    async def queue_position(self, prompt_id: str) -> int | None: ...
