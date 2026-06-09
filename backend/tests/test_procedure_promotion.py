"""Tests for procedural memory promotion on assistant message like."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from leagent.memory.procedure_promotion import (
    PROCEDURAL_PROMOTED_KEY,
    record_procedure_for_liked_assistant,
)
from leagent.db.models.message import MessageRole, MessageStatus


@pytest.mark.asyncio
async def test_promotion_skips_when_already_promoted() -> None:
    chat = MagicMock()
    mem = MagicMock()
    mem.record_procedure = AsyncMock()
    sid = uuid4()
    mid = uuid4()
    uid = uuid4()
    msg = MagicMock()
    msg.role = MessageRole.ASSISTANT
    msg.tool_calls = '[{"name": "list_dir", "id": "1"}]'
    msg.extensions = f'{{"{PROCEDURAL_PROMOTED_KEY}": "2020-01-01T00:00:00+00:00"}}'
    msg.content = "done"
    msg.status = MessageStatus.COMPLETED
    msg.error = None
    msg.latency_ms = 10
    msg.created_at = datetime.utcnow()
    msg.parent_id = None
    chat.get_session_message = AsyncMock(return_value=msg)

    ok, err, wrote, status = await record_procedure_for_liked_assistant(
        chat_svc=chat,
        agent_memory=mem,
        enable_memory=True,
        session_id=sid,
        assistant_message_id=mid,
        user_id=uid,
    )
    assert ok is True
    assert err is None
    assert wrote is False
    assert status["reason"] == "already_promoted"
    mem.record_procedure.assert_not_awaited()


@pytest.mark.asyncio
async def test_promotion_skips_without_tool_calls() -> None:
    chat = MagicMock()
    mem = MagicMock()
    mem.record_procedure = AsyncMock()
    sid = uuid4()
    mid = uuid4()
    uid = uuid4()
    msg = MagicMock()
    msg.role = MessageRole.ASSISTANT
    msg.tool_calls = None
    msg.extensions = None
    msg.content = "hello"
    msg.status = MessageStatus.COMPLETED
    msg.error = None
    msg.latency_ms = None
    msg.created_at = datetime.utcnow()
    msg.parent_id = None
    chat.get_session_message = AsyncMock(return_value=msg)

    ok, err, wrote, status = await record_procedure_for_liked_assistant(
        chat_svc=chat,
        agent_memory=mem,
        enable_memory=True,
        session_id=sid,
        assistant_message_id=mid,
        user_id=uid,
    )
    assert ok is True
    assert err is None
    assert wrote is False
    assert status["reason"] == "no_tool_calls"
    mem.record_procedure.assert_not_awaited()


@pytest.mark.asyncio
async def test_promotion_calls_record_procedure_with_tools() -> None:
    chat = MagicMock()
    mem = MagicMock()
    mem.record_procedure = AsyncMock()
    mem.procedure_write_status.return_value = {
        "pg_written": True,
        "vector_written": False,
        "embedding_degraded": False,
        "vector_degraded": True,
        "degraded": True,
        "embedding_error": None,
        "vector_error": "milvus unavailable",
    }
    chat.merge_message_extensions = AsyncMock(return_value=True)
    sid = uuid4()
    mid = uuid4()
    uid = uuid4()
    msg = MagicMock()
    msg.role = MessageRole.ASSISTANT
    msg.tool_calls = '[{"name": "read_file", "id": "1"}]'
    msg.extensions = None
    msg.content = "file contents summarized"
    msg.status = MessageStatus.COMPLETED
    msg.error = None
    msg.latency_ms = 42
    msg.created_at = datetime.utcnow()
    msg.parent_id = None
    chat.get_session_message = AsyncMock(return_value=msg)
    umsg = MagicMock()
    umsg.content = "read the file please"
    chat.find_previous_user_message = AsyncMock(return_value=umsg)

    ok, err, wrote, status = await record_procedure_for_liked_assistant(
        chat_svc=chat,
        agent_memory=mem,
        enable_memory=True,
        session_id=sid,
        assistant_message_id=mid,
        user_id=uid,
    )
    assert ok is True
    assert err is None
    assert wrote is True
    assert status["pg_written"] is True
    assert status["vector_written"] is False
    assert status["degraded"] is True
    mem.record_procedure.assert_awaited_once()
    chat.merge_message_extensions.assert_awaited_once()
    _args, call_kw = chat.merge_message_extensions.await_args
    assert PROCEDURAL_PROMOTED_KEY in call_kw["patch"]
