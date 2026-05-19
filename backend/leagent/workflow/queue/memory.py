"""In-memory ``PromptQueue`` backed by a priority heap.

All operations are safe across multiple tasks in the same event loop.
"""

from __future__ import annotations

import asyncio
import heapq
import time
from typing import Any

from .base import PromptHistoryEntry, PromptItem, PromptQueue


class InMemoryPromptQueue(PromptQueue):
    """Single-process priority queue."""

    def __init__(self) -> None:
        self._heap: list[tuple[int, float, str, PromptItem]] = []
        self._seq = 0
        self._cond = asyncio.Condition()
        self._history: dict[str, PromptHistoryEntry] = {}
        self._index: dict[str, tuple[int, float, str, PromptItem]] = {}

    async def put(self, item: PromptItem) -> None:
        async with self._cond:
            self._seq += 1
            entry = (item.priority, item.enqueued_at, str(self._seq), item)
            heapq.heappush(self._heap, entry)
            self._index[item.prompt_id] = entry
            self._cond.notify_all()

    async def get(self, *, timeout: float | None = None) -> PromptItem | None:
        async with self._cond:
            start = time.monotonic()
            while not self._heap:
                remaining = None if timeout is None else timeout - (time.monotonic() - start)
                if remaining is not None and remaining <= 0:
                    return None
                try:
                    await asyncio.wait_for(self._cond.wait(), timeout=remaining)
                except asyncio.TimeoutError:
                    return None
            _, _, _, item = heapq.heappop(self._heap)
            self._index.pop(item.prompt_id, None)
            return item

    async def task_done(self, item: PromptItem, history: PromptHistoryEntry) -> None:
        history.finished_at = time.time()
        self._history[item.prompt_id] = history

    async def history(self, prompt_id: str) -> PromptHistoryEntry | None:
        return self._history.get(prompt_id)

    async def wipe(self) -> None:
        async with self._cond:
            self._heap.clear()
            self._index.clear()
            self._history.clear()

    async def size(self) -> int:
        return len(self._heap)

    async def queue_position(self, prompt_id: str) -> int | None:
        if prompt_id not in self._index:
            return None
        target = self._index[prompt_id]
        sorted_heap = sorted(self._heap)
        for idx, entry in enumerate(sorted_heap):
            if entry is target:
                return idx
        return None

    # Debug / introspection -------------------------------------------------

    async def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "prompt_id": item.prompt_id,
                "flow_id": item.flow_id,
                "priority": item.priority,
                "enqueued_at": item.enqueued_at,
            }
            for _, _, _, item in sorted(self._heap)
        ]
