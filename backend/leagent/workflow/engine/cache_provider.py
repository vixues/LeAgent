"""Pluggable cache providers for workflow execution.

Lifecycle hooks mirror the runner flow:

- ``on_prompt_start(prompt_id)`` — begin tracking writes for this prompt.
- ``on_lookup(key)`` — returns a cached value or ``None`` on miss.
- ``should_cache(key, node_def)`` — filters which nodes we persist.
- ``on_store(key, value)`` — write a produced value.
- ``on_prompt_end(prompt_id)`` — finalize.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CacheProvider(ABC):
    @abstractmethod
    async def on_prompt_start(self, prompt_id: str) -> None: ...

    @abstractmethod
    async def on_prompt_end(self, prompt_id: str) -> None: ...

    @abstractmethod
    async def on_lookup(self, key: str) -> Any | None: ...

    @abstractmethod
    async def on_store(self, key: str, value: Any) -> None: ...

    def should_cache(self, key: str, node_def: dict[str, Any]) -> bool:
        return True


class NullCacheProvider(CacheProvider):
    async def on_prompt_start(self, prompt_id: str) -> None:
        return

    async def on_prompt_end(self, prompt_id: str) -> None:
        return

    async def on_lookup(self, key: str) -> Any | None:
        return None

    async def on_store(self, key: str, value: Any) -> None:
        return
