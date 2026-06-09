"""Tests for GET /v1/chat/sessions/{id}/agent-memory."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from leagent.memory.types import Episode, Fact, Procedure
from leagent.services.auth.deps import get_current_user_id
from leagent.services.chat.service import get_chat_service
from leagent.db.models.message import ChatSession


def _session_for_user(session_id: UUID, user_id: UUID) -> ChatSession:
    now = datetime.utcnow()
    return ChatSession(
        id=session_id,
        user_id=user_id,
        name="t",
        is_active=True,
        message_count=0,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
class TestChatAgentMemoryEndpoint:
    async def test_returns_404_when_session_missing(
        self,
        async_client: Any,
        test_user: dict[str, Any],
        app: Any,
    ) -> None:
        uid = UUID(test_user["user_id"])

        async def _user_id() -> UUID:
            return uid

        mock_chat = MagicMock()
        mock_chat.get_session = AsyncMock(return_value=None)
        app.dependency_overrides[get_current_user_id] = _user_id
        app.dependency_overrides[get_chat_service] = lambda: mock_chat
        try:
            sid = uuid4()
            resp = await async_client.get(
                f"/api/v1/chat/sessions/{sid}/agent-memory",
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404
        mock_chat.get_session.assert_awaited_once()

    async def test_memory_disabled_returns_enabled_false(
        self,
        async_client: Any,
        test_user: dict[str, Any],
        app: Any,
    ) -> None:
        uid = UUID(test_user["user_id"])
        sid = uuid4()
        mock_chat = MagicMock()
        mock_chat.get_session = AsyncMock(return_value=_session_for_user(sid, uid))

        sm = MagicMock()
        sm.agent_memory = None

        async def _user_id() -> UUID:
            return uid

        app.dependency_overrides[get_current_user_id] = _user_id
        app.dependency_overrides[get_chat_service] = lambda: mock_chat
        try:
            with patch("leagent.main.get_service_manager", return_value=sm):
                resp = await async_client.get(
                    f"/api/v1/chat/sessions/{sid}/agent-memory",
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["episodes"] == []
        assert body["facts"] == []
        assert body["procedures"] == []

    async def test_happy_path_snapshot(
        self,
        async_client: Any,
        test_user: dict[str, Any],
        app: Any,
    ) -> None:
        uid = UUID(test_user["user_id"])
        sid = uuid4()
        mock_chat = MagicMock()
        mock_chat.get_session = AsyncMock(return_value=_session_for_user(sid, uid))

        ep = Episode(session_id=sid, user_id=uid, summary="Q: hi\nA: hello")
        fact = Fact(user_id=uid, key="locale", value="en-US", confidence=0.9)
        proc = Procedure(
            name="read_file",
            signature="abc123",
            description="Read a path and return contents",
            user_id=uid,
            run_count=2,
            success_count=2,
        )

        mem = MagicMock()
        mem.episodic = MagicMock()
        mem.episodic.list_recent = AsyncMock(return_value=[ep])
        mem.semantic = MagicMock()
        mem.semantic.list_for_user = AsyncMock(return_value=[fact])
        mem.procedural = MagicMock()
        mem.procedural.list_recent_for_user = AsyncMock(return_value=[proc])
        sm = MagicMock()
        sm.agent_memory = mem

        async def _user_id() -> UUID:
            return uid

        app.dependency_overrides[get_current_user_id] = _user_id
        app.dependency_overrides[get_chat_service] = lambda: mock_chat
        try:
            with patch("leagent.main.get_service_manager", return_value=sm):
                resp = await async_client.get(
                    f"/api/v1/chat/sessions/{sid}/agent-memory",
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is True
        assert len(body["episodes"]) == 1
        assert body["episodes"][0]["summary"] == ep.summary
        assert body["episodes"][0]["session_id"] == str(sid)
        assert len(body["facts"]) == 1
        assert body["facts"][0]["key"] == "locale"
        assert len(body["procedures"]) == 1
        assert body["procedures"][0]["name"] == "read_file"
        assert body["procedures"][0]["success_rate"] == 1.0

        mem.episodic.list_recent.assert_awaited_once_with(session_id=sid, limit=50)
        mem.semantic.list_for_user.assert_awaited_once_with(uid, limit=50)
        mem.procedural.list_recent_for_user.assert_awaited_once_with(
            user_id=uid,
            limit=50,
        )
