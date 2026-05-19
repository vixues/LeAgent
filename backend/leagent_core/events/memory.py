"""In-memory event bus for single-process / test use."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from leagent_core.events.base import EventBus, EventEnvelope, Subscriber


class _MemorySubscriber:
    """Subscriber backed by an ``asyncio.Queue``."""

    def __init__(self, bus: "InMemoryEventBus", topics: tuple[str, ...]) -> None:
        self._bus = bus
        self._topics = topics
        self._queue: asyncio.Queue[EventEnvelope | None] = asyncio.Queue()
        self._closed = False

    async def _enqueue(self, envelope: EventEnvelope) -> None:
        if self._closed:
            return
        await self._queue.put(envelope)

    def topics(self) -> tuple[str, ...]:
        return self._topics

    def __aiter__(self) -> AsyncIterator[EventEnvelope]:
        return self

    async def __anext__(self) -> EventEnvelope:
        envelope = await self._queue.get()
        if envelope is None:
            raise StopAsyncIteration
        return envelope

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._queue.put(None)
        self._bus._remove(self)  # noqa: SLF001


class InMemoryEventBus(EventBus):
    """Process-local event bus backed by ``asyncio.Queue``."""

    def __init__(self) -> None:
        self._subscribers: list[_MemorySubscriber] = []
        self._lock = asyncio.Lock()

    async def publish(self, envelope: EventEnvelope) -> None:
        async with self._lock:
            targets = [
                sub for sub in self._subscribers
                if _matches(envelope.topic, sub.topics())
            ]
        for sub in targets:
            await sub._enqueue(envelope)  # noqa: SLF001

    async def subscribe(self, *topics: str) -> Subscriber:
        sub = _MemorySubscriber(self, topics or ("*",))
        async with self._lock:
            self._subscribers.append(sub)
        return sub

    def _remove(self, sub: _MemorySubscriber) -> None:
        try:
            self._subscribers.remove(sub)
        except ValueError:
            pass

    async def aclose(self) -> None:
        async with self._lock:
            subs = list(self._subscribers)
            self._subscribers.clear()
        for sub in subs:
            await sub.aclose()


def _matches(topic: str, patterns: tuple[str, ...]) -> bool:
    for pat in patterns:
        if pat == "*" or pat == topic:
            return True
        if pat.endswith(".*") and topic.startswith(pat[:-1]):
            return True
    return False


__all__ = ["InMemoryEventBus"]
