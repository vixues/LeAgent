"""Execution event bus.

Broadcasts :class:`ProgressEvent` instances from the worker to connected
WebSocket clients via an in-memory transport.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol

import structlog

from ..engine.progress import ProgressEvent

logger = structlog.get_logger(__name__)

Subscriber = Callable[[ProgressEvent], Awaitable[None]]


class ExecutionEventBus(Protocol):
    async def publish_event(self, prompt_id: str, event: ProgressEvent) -> None: ...

    async def subscribe(self, prompt_id: str) -> AsyncIterator[ProgressEvent]: ...

    async def subscribe_all(self) -> AsyncIterator[ProgressEvent]: ...


class InMemoryEventBus(ExecutionEventBus):
    def __init__(self) -> None:
        self._channels: dict[str, set[asyncio.Queue[ProgressEvent]]] = {}
        self._broadcast: set[asyncio.Queue[ProgressEvent]] = set()
        self._lock = asyncio.Lock()

    async def publish_event(self, prompt_id: str, event: ProgressEvent) -> None:
        async with self._lock:
            for q in self._channels.get(prompt_id, set()):
                q.put_nowait(event)
            for q in self._broadcast:
                q.put_nowait(event)

    async def subscribe(self, prompt_id: str) -> AsyncIterator[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        async with self._lock:
            self._channels.setdefault(prompt_id, set()).add(q)
        try:
            while True:
                yield await q.get()
        finally:
            async with self._lock:
                self._channels.get(prompt_id, set()).discard(q)

    async def subscribe_all(self) -> AsyncIterator[ProgressEvent]:
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        async with self._lock:
            self._broadcast.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            async with self._lock:
                self._broadcast.discard(q)


_DEFAULT_BUS: ExecutionEventBus | None = None


async def get_event_bus(service_manager: Any | None = None) -> ExecutionEventBus:
    """Return the process-wide :class:`ExecutionEventBus`.

    Prefers the bus already constructed by :class:`ServiceManager` so that
    publishers (workflow executor) and subscribers (WebSocket router) share a
    single transport.
    """
    global _DEFAULT_BUS
    if service_manager is not None:
        shared = getattr(service_manager, "_workflow_event_bus", None)
        if shared is not None:
            _DEFAULT_BUS = shared
            return _DEFAULT_BUS
    if _DEFAULT_BUS is not None:
        return _DEFAULT_BUS
    _DEFAULT_BUS = InMemoryEventBus()
    return _DEFAULT_BUS


def reset_event_bus() -> None:
    global _DEFAULT_BUS
    _DEFAULT_BUS = None
