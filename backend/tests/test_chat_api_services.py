"""Tests for the Chat API v1 services-layer upgrade.

Verifies that all chat endpoints delegate to ``ChatService`` and that the
shared agent-stream helpers work correctly — fully mocked, no DB or LLM.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from leagent.api.v1.chat import (
    SessionUpdateRequest,
    _format_frontend_event,
    _format_openai_chunk,
    _merge_stream_thinking_for_persist,
    _run_agent_stream,
)
from leagent.services.chat.service import ChatService
from leagent.db.models.message import (
    ChatSession,
    Message,
    MessageRead,
    MessageRole,
    MessageStatus,
    SessionRead,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_session(user_id: UUID | None = None, **kw: Any) -> ChatSession:
    defaults: dict[str, Any] = {
        "id": uuid4(),
        "user_id": user_id or uuid4(),
        "name": "test",
        "is_active": True,
        "message_count": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(kw)
    return ChatSession(**defaults)


def _fake_message(session_id: UUID, **kw: Any) -> Message:
    defaults: dict[str, Any] = {
        "id": uuid4(),
        "session_id": session_id,
        "role": MessageRole.USER,
        "content": "hello",
        "status": MessageStatus.COMPLETED,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(kw)
    return Message(**defaults)


def _mock_chat_service() -> MagicMock:
    svc = MagicMock(spec=ChatService)
    svc.create_session = AsyncMock()
    svc.get_session = AsyncMock()
    svc.list_sessions = AsyncMock()
    svc.delete_session = AsyncMock()
    svc.update_session = AsyncMock()
    svc.add_message = AsyncMock()
    svc.get_messages_paginated = AsyncMock()
    svc.get_history = AsyncMock()
    return svc


def _mock_db() -> MagicMock:
    return MagicMock()


def _mock_db() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------


class TestMergeStreamThinkingForPersist:
    def test_cumulative_replaces_without_duplication(self) -> None:
        acc = _merge_stream_thinking_for_persist(None, "hel")
        assert acc == "hel"
        acc = _merge_stream_thinking_for_persist(acc, "hello")
        assert acc == "hello"
        acc = _merge_stream_thinking_for_persist(acc, "hello world")
        assert acc == "hello world"

    def test_discrete_thoughts_append(self) -> None:
        acc = _merge_stream_thinking_for_persist(None, "plan A")
        acc = _merge_stream_thinking_for_persist(acc, "plan B")
        assert acc == "plan A\nplan B"

    def test_empty_fragment_keeps_previous(self) -> None:
        acc = _merge_stream_thinking_for_persist(None, "x")
        assert _merge_stream_thinking_for_persist(acc, "   ") == "x"


class TestFormatHelpers:
    def test_format_frontend_event(self) -> None:
        result = _format_frontend_event("content", "hello")
        assert result["event"] == "message"
        payload = json.loads(result["data"])
        assert payload["type"] == "content"
        assert payload["data"] == "hello"

    def test_format_openai_chunk(self) -> None:
        result = _format_openai_chunk("cid-1", 1234, "gpt-4", {"content": "hi"})
        assert result["event"] == "message"
        payload = json.loads(result["data"])
        assert payload["id"] == "cid-1"
        assert payload["object"] == "chat.completion.chunk"
        assert payload["choices"][0]["delta"]["content"] == "hi"
        assert payload["choices"][0]["finish_reason"] is None

    def test_format_openai_chunk_with_finish(self) -> None:
        result = _format_openai_chunk("cid-1", 1234, "gpt-4", {}, finish_reason="stop")
        payload = json.loads(result["data"])
        assert payload["choices"][0]["finish_reason"] == "stop"


# ---------------------------------------------------------------------------
# Agent stream helper
# ---------------------------------------------------------------------------


class TestRunAgentStream:
    @pytest.mark.asyncio
    async def test_token_events_accumulate(self) -> None:
        events = [
            MagicMock(type="token", data={"token": "Hello"}),
            MagicMock(type="token", data={"token": " world"}),
            MagicMock(type="complete", data={"text": "Hello world"}),
        ]

        async def _fake_stream(*a: Any, **kw: Any):
            for e in events:
                yield e

        agent = MagicMock()
        agent.run_stream = _fake_stream

        collected = []
        async for etype, edata, acc in _run_agent_stream(agent, "msg", uuid4(), uuid4()):
            if etype == "execution_started":
                continue
            collected.append((etype, acc))

        assert collected[0] == ("token", "Hello")
        assert collected[1] == ("token", "Hello world")
        assert collected[2] == ("complete", "Hello world")

    @pytest.mark.asyncio
    async def test_error_event_forwarded(self) -> None:
        events = [MagicMock(type="error", data={"error": "boom"})]

        async def _fake_stream(*a: Any, **kw: Any):
            for e in events:
                yield e

        agent = MagicMock()
        agent.run_stream = _fake_stream

        collected = []
        async for etype, edata, acc in _run_agent_stream(agent, "msg", uuid4(), uuid4()):
            if etype == "execution_started":
                continue
            collected.append((etype, edata))

        assert collected[0][0] == "error"
        assert collected[0][1]["error"] == "boom"
        assert "run_id" in collected[0][1]

    @pytest.mark.asyncio
    async def test_thinking_and_tool_events(self) -> None:
        events = [
            MagicMock(type="thinking", data={"thought": "hmm"}),
            MagicMock(type="tool_call", data={"tool": "search", "args": {}}),
            MagicMock(type="tool_result", data={"result": "found"}),
        ]

        async def _fake_stream(*a: Any, **kw: Any):
            for e in events:
                yield e

        agent = MagicMock()
        agent.run_stream = _fake_stream

        types = []
        async for etype, edata, acc in _run_agent_stream(agent, "msg", uuid4(), uuid4()):
            if etype == "execution_started":
                continue
            types.append(etype)

        assert types == ["thinking", "tool_call", "tool_result"]


# ---------------------------------------------------------------------------
# ChatService delegation (endpoint-level, mocked)
# ---------------------------------------------------------------------------


class TestSessionEndpointsDelegation:
    """Verify endpoints call the right ChatService methods."""

    @pytest.mark.asyncio
    async def test_create_session_delegates(self) -> None:
        from leagent.api.v1.chat import create_session
        from leagent.db.models.message import SessionCreate

        svc = _mock_chat_service()
        db = _mock_db()
        uid = uuid4()
        fake = _fake_session(uid)
        svc.create_session.return_value = fake

        with patch(
            "leagent.api.v1.chat._require_project_access",
            new_callable=AsyncMock,
        ):
            result = await create_session(SessionCreate(name="My Chat"), uid, svc, db)
        svc.create_session.assert_awaited_once()
        call_kw = svc.create_session.call_args
        assert call_kw[0][0] == uid

    @pytest.mark.asyncio
    async def test_get_session_delegates(self) -> None:
        from leagent.api.v1.chat import get_session

        svc = _mock_chat_service()
        db = _mock_db()
        uid = uuid4()
        sid = uuid4()
        fake = _fake_session(uid, id=sid)
        svc.get_session.return_value = fake

        with patch(
            "leagent.api.v1.chat._require_session_project_access",
            new_callable=AsyncMock,
        ):
            result = await get_session(sid, uid, svc, db)
        svc.get_session.assert_awaited_once_with(sid, user_id=uid)

    @pytest.mark.asyncio
    async def test_get_session_not_found_raises(self) -> None:
        from fastapi import HTTPException
        from leagent.api.v1.chat import get_session

        svc = _mock_chat_service()
        db = _mock_db()
        svc.get_session.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_session(uuid4(), uuid4(), svc, db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session_delegates(self) -> None:
        from leagent.api.v1.chat import delete_session

        svc = _mock_chat_service()
        db = _mock_db()
        svc.delete_session.return_value = True

        uid = uuid4()
        sid = uuid4()
        fake = _fake_session(uid, id=sid)
        svc.get_session.return_value = fake

        with patch(
            "leagent.api.v1.chat._require_session_project_access",
            new_callable=AsyncMock,
        ):
            await delete_session(sid, uid, svc, db)
        svc.delete_session.assert_awaited_once_with(sid, uid, soft=False)

    @pytest.mark.asyncio
    async def test_delete_session_not_found_raises(self) -> None:
        from fastapi import HTTPException
        from leagent.api.v1.chat import delete_session

        svc = _mock_chat_service()
        db = _mock_db()
        svc.get_session.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await delete_session(uuid4(), uuid4(), svc, db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_session_delegates(self) -> None:
        from leagent.api.v1.chat import update_session
        from leagent.db.models.message import chat_session_to_read

        svc = _mock_chat_service()
        db = _mock_db()
        svc.sanitize_metadata_patch = AsyncMock()
        svc.merge_session_metadata = AsyncMock()
        uid = uuid4()
        sid = uuid4()
        fake = _fake_session(uid, id=sid, name="Updated")
        svc.get_session.return_value = fake
        svc.update_session.return_value = fake

        body = SessionUpdateRequest(name="Updated")
        with patch(
            "leagent.api.v1.chat._require_session_project_access",
            new_callable=AsyncMock,
        ):
            result = await update_session(sid, body, uid, svc, db)
        svc.update_session.assert_awaited_once_with(sid, uid, name="Updated", is_active=None)
        assert result == chat_session_to_read(fake)
        assert svc.get_session.await_count == 2

    @pytest.mark.asyncio
    async def test_update_session_not_found_raises(self) -> None:
        from fastapi import HTTPException
        from leagent.api.v1.chat import update_session

        svc = _mock_chat_service()
        db = _mock_db()
        svc.get_session.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await update_session(uuid4(), SessionUpdateRequest(name="x"), uuid4(), svc, db)
        assert exc_info.value.status_code == 404


class TestMessageEndpointsDelegation:
    @pytest.mark.asyncio
    async def test_get_messages_delegates(self) -> None:
        from leagent.api.v1.chat import get_session_messages

        svc = _mock_chat_service()
        db = _mock_db()
        uid = uuid4()
        sid = uuid4()
        fake_session = _fake_session(uid, id=sid)
        svc.get_session.return_value = fake_session

        fake_msg = _fake_message(sid)
        svc.get_messages_paginated.return_value = (
            [MessageRead.model_validate(fake_msg)],
            1,
        )

        with patch(
            "leagent.api.v1.chat._require_session_project_access",
            new_callable=AsyncMock,
        ):
            result = await get_session_messages(sid, uid, svc, db, page=1, page_size=50)
        svc.get_session.assert_awaited_once_with(sid, user_id=uid)
        svc.get_messages_paginated.assert_awaited_once()
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_get_messages_session_not_found(self) -> None:
        from fastapi import HTTPException
        from leagent.api.v1.chat import get_session_messages

        svc = _mock_chat_service()
        db = _mock_db()
        svc.get_session.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_session_messages(uuid4(), uuid4(), svc, db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_send_message_inactive_session(self) -> None:
        from fastapi import HTTPException
        from leagent.api.v1.chat import send_message, SendMessageRequest

        svc = _mock_chat_service()
        uid = uuid4()
        sid = uuid4()
        inactive = _fake_session(uid, id=sid, is_active=False)
        svc.get_session.return_value = inactive

        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await send_message(
                sid, SendMessageRequest(content="hi"), uid, svc, mock_db,
            )
        assert exc_info.value.status_code == 400


class TestCompletionEndpointDelegation:
    @pytest.mark.asyncio
    async def test_empty_messages_raises_400(self) -> None:
        from fastapi import HTTPException
        from leagent.api.v1.chat import create_chat_completion, ChatCompletionRequest

        svc = _mock_chat_service()
        req = ChatCompletionRequest(messages=[], stream=False)
        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await create_chat_completion(req, uuid4(), svc, mock_db)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_creates_session_when_missing(self) -> None:
        from fastapi import HTTPException
        from leagent.api.v1.chat import (
            create_chat_completion,
            ChatCompletionRequest,
            ChatCompletionMessage,
        )

        svc = _mock_chat_service()
        uid = uuid4()
        fake = _fake_session(uid)
        svc.create_session.return_value = fake

        req = ChatCompletionRequest(
            messages=[ChatCompletionMessage(role=MessageRole.USER, content="hi")],
            stream=False,
        )
        mock_db = MagicMock()

        with patch("leagent.api.v1.chat.build_agent_controller", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await create_chat_completion(req, uid, svc, mock_db)
            assert exc_info.value.status_code == 503

        svc.create_session.assert_awaited_once()
        svc.add_message.assert_awaited_once()


# ---------------------------------------------------------------------------
# ChatService new methods (unit level, mocked DB)
# ---------------------------------------------------------------------------


class TestChatServiceUpdateSession:
    @pytest.mark.asyncio
    async def test_returns_none_without_db(self) -> None:
        svc = ChatService.__new__(ChatService)
        svc._db = None
        svc._cache = None
        result = await svc.update_session(uuid4(), uuid4(), name="x")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self) -> None:
        mock_db = MagicMock()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _session():
            yield MagicMock()

        mock_db.session = _session

        svc = ChatService.__new__(ChatService)
        svc._db = mock_db
        svc._cache = None
        with patch(
            "leagent.services.chat.service.load_chat_session_by_id",
            new=AsyncMock(return_value=None),
        ):
            result = await svc.update_session(uuid4(), uuid4(), name="x")
        assert result is None


class TestChatServiceGetMessagesPaginated:
    @pytest.mark.asyncio
    async def test_returns_empty_without_db(self) -> None:
        svc = ChatService.__new__(ChatService)
        svc._db = None
        svc._cache = None
        items, total = await svc.get_messages_paginated(uuid4())
        assert items == []
        assert total == 0
