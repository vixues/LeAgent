"""Tests for the conversation_history util tool."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from leagent.services.session.state import SessionMessage, SessionState
from leagent.tools.base import ToolContext
from leagent.tools.util.conversation_history import ConversationHistoryTool


def _ctx(user_id=None, session_id=None) -> ToolContext:
    return ToolContext(
        user_id=str(user_id or uuid4()),
        session_id=str(session_id) if session_id else None,
        extra={},
    )


@pytest.mark.asyncio
async def test_extract_pulls_user_assistant_across_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    current_sid = uuid4()
    older_sid = uuid4()
    now = datetime.now(timezone.utc)

    sessions = [
        SimpleNamespace(
            id=current_sid,
            name="This week",
            message_count=2,
            last_message_at=now,
            updated_at=now,
            created_at=now - timedelta(days=1),
        ),
        SimpleNamespace(
            id=older_sid,
            name="Earlier",
            message_count=2,
            last_message_at=now - timedelta(days=2),
            updated_at=now - timedelta(days=2),
            created_at=now - timedelta(days=3),
        ),
    ]

    states = {
        current_sid: SessionState(
            session_id=current_sid,
            user_id=user_id,
            messages=[
                SessionMessage(
                    role="user",
                    content="Finished the Weixin channel",
                    created_at=now - timedelta(hours=2),
                ),
                SessionMessage(
                    role="assistant",
                    content="Great — shipped Weixin login + tests.",
                    created_at=now - timedelta(hours=1),
                ),
                SessionMessage(
                    role="tool",
                    content="noise",
                    created_at=now - timedelta(minutes=30),
                ),
            ],
        ),
        older_sid: SessionState(
            session_id=older_sid,
            user_id=user_id,
            messages=[
                SessionMessage(
                    role="user",
                    content="Drafted README updates",
                    created_at=now - timedelta(days=2),
                ),
                SessionMessage(
                    role="assistant",
                    content="Updated zh/en README sections.",
                    created_at=now - timedelta(days=2) + timedelta(hours=1),
                ),
            ],
        ),
    }

    class _FakeChat:
        async def list_sessions(self, uid, **kwargs):  # noqa: ANN001
            assert uid == user_id
            return sessions

        async def get_session(self, sid, *, user_id=None):  # noqa: ANN001
            for s in sessions:
                if s.id == sid:
                    return s
            return None

    class _FakeSessionManager:
        async def load(self, sid):  # noqa: ANN001
            return states.get(sid)

    class _FakeSM:
        chat = _FakeChat()
        session_manager = _FakeSessionManager()

    import leagent.main as main_mod

    monkeypatch.setattr(main_mod, "get_service_manager", lambda: _FakeSM())

    tool = ConversationHistoryTool()
    result = await tool.execute(
        {"operation": "extract", "days": 7},
        _ctx(user_id=user_id, session_id=current_sid),
    )

    assert result["operation"] == "extract"
    assert result["stats"]["session_count"] == 2
    assert result["stats"]["message_count"] == 4
    roles = {
        m["role"]
        for bundle in result["sessions"]
        for m in bundle["messages"]
    }
    assert roles == {"user", "assistant"}
    assert any("Weixin" in m["content"] for b in result["sessions"] for m in b["messages"])


@pytest.mark.asyncio
async def test_get_defaults_to_current_session(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    sid = uuid4()
    now = datetime.now(timezone.utc)
    state = SessionState(
        session_id=sid,
        user_id=user_id,
        messages=[
            SessionMessage(role="user", content="hello", created_at=now),
            SessionMessage(role="assistant", content="hi", created_at=now),
        ],
    )

    class _FakeChat:
        async def get_session(self, session_id, *, user_id=None):  # noqa: ANN001
            assert session_id == sid
            return SimpleNamespace(
                id=sid,
                name="Current",
                message_count=2,
                last_message_at=now,
            )

    class _FakeSessionManager:
        async def load(self, session_id):  # noqa: ANN001
            return state if session_id == sid else None

    class _FakeSM:
        chat = _FakeChat()
        session_manager = _FakeSessionManager()

    import leagent.main as main_mod

    monkeypatch.setattr(main_mod, "get_service_manager", lambda: _FakeSM())

    result = await ConversationHistoryTool().execute(
        {"operation": "get"},
        _ctx(user_id=user_id, session_id=sid),
    )
    assert result["operation"] == "get"
    assert result["count"] == 2
    assert result["session"]["session_id"] == str(sid)


@pytest.mark.asyncio
async def test_list_filters_by_window(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    now = datetime.now(timezone.utc)
    in_window = uuid4()
    out_window = uuid4()
    sessions = [
        SimpleNamespace(
            id=in_window,
            name="recent",
            message_count=1,
            last_message_at=now - timedelta(days=1),
            updated_at=now - timedelta(days=1),
            created_at=now - timedelta(days=2),
        ),
        SimpleNamespace(
            id=out_window,
            name="old",
            message_count=1,
            last_message_at=now - timedelta(days=30),
            updated_at=now - timedelta(days=30),
            created_at=now - timedelta(days=40),
        ),
    ]

    class _FakeChat:
        async def list_sessions(self, uid, **kwargs):  # noqa: ANN001
            return sessions

    class _FakeSM:
        chat = _FakeChat()
        session_manager = None

    import leagent.main as main_mod

    monkeypatch.setattr(main_mod, "get_service_manager", lambda: _FakeSM())

    result = await ConversationHistoryTool().execute(
        {"operation": "list", "days": 7},
        _ctx(user_id=user_id),
    )
    assert result["count"] == 1
    assert result["sessions"][0]["session_id"] == str(in_window)


@pytest.mark.asyncio
async def test_query_filters_content(monkeypatch: pytest.MonkeyPatch) -> None:
    user_id = uuid4()
    sid = uuid4()
    now = datetime.now(timezone.utc)
    state = SessionState(
        session_id=sid,
        user_id=user_id,
        messages=[
            SessionMessage(role="user", content="deployed Weixin", created_at=now),
            SessionMessage(role="user", content="fixed slides tool", created_at=now),
        ],
    )

    class _FakeChat:
        async def get_session(self, session_id, *, user_id=None):  # noqa: ANN001
            return SimpleNamespace(
                id=sid, name="x", message_count=2, last_message_at=now
            )

    class _FakeSessionManager:
        async def load(self, session_id):  # noqa: ANN001
            return state

    class _FakeSM:
        chat = _FakeChat()
        session_manager = _FakeSessionManager()

    import leagent.main as main_mod

    monkeypatch.setattr(main_mod, "get_service_manager", lambda: _FakeSM())

    result = await ConversationHistoryTool().execute(
        {"operation": "get", "session_id": str(sid), "query": "weixin"},
        _ctx(user_id=user_id, session_id=sid),
    )
    assert result["count"] == 1
    assert "Weixin" in result["messages"][0]["content"]


@pytest.mark.asyncio
async def test_requires_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeSM:
        chat = object()
        session_manager = object()

    import leagent.main as main_mod
    import leagent.tools.util.conversation_history as mod

    monkeypatch.setattr(main_mod, "get_service_manager", lambda: _FakeSM())
    monkeypatch.setattr(mod, "resolve_effective_user_id", lambda *a, **k: None)

    result = await ConversationHistoryTool().execute(
        {"operation": "list"},
        ToolContext(user_id=None, session_id=None, extra={}),
    )
    assert "user_id" in result["error"]


@pytest.mark.asyncio
async def test_invalid_operation() -> None:
    result = await ConversationHistoryTool().execute(
        {"operation": "delete"},
        _ctx(),
    )
    assert "Unsupported operation" in result["error"]
