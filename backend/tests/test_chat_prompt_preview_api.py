"""Tests for GET /v1/chat/sessions/{id}/prompt-preview."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from leagent.services.auth.deps import get_current_user_id
from leagent.services.chat.service import get_chat_service
from leagent.db.models.message import ChatSession


class _FakeSessionLock:
    """Minimal async context manager for ``session_manager.locked``."""

    def __init__(self, llm_messages: list[dict[str, Any]]) -> None:
        self._llm_messages = llm_messages

    async def __aenter__(self) -> MagicMock:
        state = MagicMock()
        state.llm_messages = MagicMock(return_value=list(self._llm_messages))
        return state

    async def __aexit__(self, *args: object) -> bool:
        return False


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
class TestPromptPreviewEndpoint:
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
                f"/api/v1/chat/sessions/{sid}/prompt-preview",
                params={"query": "hello"},
            )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 404

    async def test_returns_503_when_session_manager_missing(
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
        sm.session_manager = None

        async def _user_id() -> UUID:
            return uid

        app.dependency_overrides[get_current_user_id] = _user_id
        app.dependency_overrides[get_chat_service] = lambda: mock_chat
        try:
            with patch("leagent.main.get_service_manager", return_value=sm):
                resp = await async_client.get(
                    f"/api/v1/chat/sessions/{sid}/prompt-preview",
                    params={"query": "hello"},
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 503
        assert "Session manager" in resp.json().get("message", "")

    async def test_happy_path_uses_mocked_context_manager(
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
        sm.session_manager = MagicMock()
        sm.session_manager.locked = MagicMock(
            side_effect=lambda _sid: _FakeSessionLock([{"role": "user", "content": "hello"}]),
        )
        sm.settings = MagicMock()
        sm.agent_memory = None

        turn = MagicMock()
        turn.built_prompt.system_text = "assembled system"
        turn.built_prompt.total_chars = 16
        turn.built_prompt.stable_hash = "stab"
        turn.built_prompt.full_hash = "full"
        turn.built_prompt.variant_key = "default_agent:default"
        turn.built_prompt.layers = []

        ctx_instance = MagicMock()
        ctx_instance.prepare_turn = AsyncMock(return_value=turn)

        async def _user_id() -> UUID:
            return uid

        app.dependency_overrides[get_current_user_id] = _user_id
        app.dependency_overrides[get_chat_service] = lambda: mock_chat
        try:
            with patch("leagent.main.get_service_manager", return_value=sm):
                with patch("leagent.context.ContextManager", return_value=ctx_instance):
                    resp = await async_client.get(
                        f"/api/v1/chat/sessions/{sid}/prompt-preview",
                        params={"query": "hello world"},
                    )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        body = resp.json()
        assert body["query_used"] == "hello world"
        assert body["system_text"] == "assembled system"
        assert body["stable_hash"] == "stab"
        assert body["layers"] == []
        assert body["approx_transcript_tokens"] == 1  # len("hello") // 3
        assert body["approx_context_tokens"] == 1
        ctx_instance.prepare_turn.assert_awaited_once()
