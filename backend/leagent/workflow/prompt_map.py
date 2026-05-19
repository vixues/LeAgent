"""``prompt_id -> execution_id`` lookup table."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID


class PromptExecutionMap:
    async def set(self, prompt_id: str, execution_id: UUID) -> None: ...
    async def get(self, prompt_id: str) -> UUID | None: ...
    async def delete(self, prompt_id: str) -> None: ...


class InMemoryPromptMap:

    def __init__(self) -> None:
        self._data: dict[str, UUID] = {}
        self._lock = asyncio.Lock()

    async def set(self, prompt_id: str, execution_id: UUID) -> None:
        async with self._lock:
            self._data[prompt_id] = execution_id

    async def get(self, prompt_id: str) -> UUID | None:
        async with self._lock:
            return self._data.get(prompt_id)

    async def delete(self, prompt_id: str) -> None:
        async with self._lock:
            self._data.pop(prompt_id, None)


def build_prompt_map(redis_client: Any | None = None) -> PromptExecutionMap:
    """Return an in-memory prompt map."""
    return InMemoryPromptMap()


__all__ = [
    "InMemoryPromptMap",
    "PromptExecutionMap",
    "build_prompt_map",
]
