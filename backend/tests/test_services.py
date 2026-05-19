"""Tests for service layer: InMemoryCache, AuthService, EventManager."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ===========================================================================
# CacheEntry + InMemoryCache
# ===========================================================================


@pytest.mark.asyncio
class TestInMemoryCache:
    async def test_set_and_get(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        cache = InMemoryCache()
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    async def test_get_missing_key_returns_none(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        cache = InMemoryCache()
        result = await cache.get("nonexistent")
        assert result is None

    async def test_set_with_ttl_expires(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        import time
        cache = InMemoryCache()
        await cache.set("short_lived", "data", ttl=1)
        result = await cache.get("short_lived")
        assert result == "data"
        # Manually expire the entry
        cache._cache["short_lived"].expires_at = time.time() - 1
        result_expired = await cache.get("short_lived")
        assert result_expired is None

    async def test_delete_existing_key(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        cache = InMemoryCache()
        await cache.set("to_delete", "value")
        deleted = await cache.delete("to_delete")
        assert deleted is True
        assert await cache.get("to_delete") is None

    async def test_delete_missing_key_returns_false(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        cache = InMemoryCache()
        result = await cache.delete("nonexistent")
        assert result is False

    async def test_exists(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        cache = InMemoryCache()
        await cache.set("exists_key", 42)
        assert await cache.exists("exists_key") is True
        assert await cache.exists("missing_key") is False

    async def test_lru_eviction(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        cache = InMemoryCache(max_size=3)
        for i in range(5):
            await cache.set(f"key{i}", f"value{i}")
        assert len(cache._cache) <= 3

    async def test_overwrite_key(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        cache = InMemoryCache()
        await cache.set("k", "v1")
        await cache.set("k", "v2")
        assert await cache.get("k") == "v2"

    async def test_clear(self) -> None:
        from leagent.services.cache.service import InMemoryCache
        cache = InMemoryCache()
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        assert await cache.get("a") is None
        assert await cache.get("b") is None


# ===========================================================================
# AuthService
# ===========================================================================


class TestAuthService:
    def test_passthrough_auth(self) -> None:
        from leagent.services.auth.service import AuthService, LOCAL_USER_ID
        svc = AuthService()
        assert svc.verify_access_token("any") == LOCAL_USER_ID
        assert svc.verify_password("any", "any") is True

    def test_create_token_pair(self) -> None:
        from leagent.services.auth.service import AuthService
        svc = AuthService()
        pair = svc.create_token_pair(uuid4())
        assert pair.access_token == "local-token"
        assert pair.token_type == "bearer"


# ===========================================================================
# EventManager
# ===========================================================================


@pytest.mark.asyncio
class TestEventManager:
    def _manager(self):
        from leagent.services.event.manager import EventManager
        settings = MagicMock()
        settings.event = MagicMock()
        return EventManager(settings=settings)

    async def test_subscribe_and_emit(self) -> None:
        manager = self._manager()
        received = []

        async def handler(event) -> None:
            received.append(event)

        from leagent.services.event.manager import EventType
        manager.subscribe(EventType.TASK_CREATED, handler)
        await manager.emit_typed(EventType.TASK_CREATED, source="test", data={"task_id": "t-1"}, wait=True)

        assert len(received) == 1

    async def test_unsubscribe(self) -> None:
        manager = self._manager()
        received = []

        async def handler(event) -> None:
            received.append(event)

        from leagent.services.event.manager import EventType
        sub_id = manager.subscribe(EventType.TASK_STARTED, handler)
        manager.unsubscribe(sub_id)
        await manager.emit_typed(EventType.TASK_STARTED, source="test", data={})

        assert len(received) == 0

    async def test_emit_with_no_subscribers(self) -> None:
        manager = self._manager()
        from leagent.services.event.manager import EventType
        await manager.emit_typed(EventType.SYSTEM_STARTUP, source="test", data={})

    async def test_multiple_subscribers_same_event(self) -> None:
        manager = self._manager()
        calls = []

        async def h1(event) -> None:
            calls.append("h1")

        async def h2(event) -> None:
            calls.append("h2")

        from leagent.services.event.manager import EventType
        manager.subscribe(EventType.AGENT_MESSAGE, h1)
        manager.subscribe(EventType.AGENT_MESSAGE, h2)
        await manager.emit_typed(EventType.AGENT_MESSAGE, source="test", data={}, wait=True)

        assert "h1" in calls
        assert "h2" in calls

    async def test_handler_exception_does_not_prevent_others(self) -> None:
        manager = self._manager()
        calls = []

        async def bad_handler(event) -> None:
            raise ValueError("bad handler")

        async def good_handler(event) -> None:
            calls.append("good")

        from leagent.services.event.manager import EventType
        manager.subscribe(EventType.CUSTOM, bad_handler)
        manager.subscribe(EventType.CUSTOM, good_handler)
        await manager.emit_typed(EventType.CUSTOM, source="test", data={}, wait=True)

        assert "good" in calls
