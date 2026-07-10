"""Tests for mid-turn steer injection and next-turn message queueing."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from leagent.agent.control import (
    SessionControlRegistry,
    get_session_control_registry,
    reset_session_control_registry,
)
from leagent.agent.query import SteerMessage, _drain_steer_messages


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_session_control_registry()
    yield
    reset_session_control_registry()


# ---------------------------------------------------------------------------
# Registry semantics
# ---------------------------------------------------------------------------


def test_steer_fifo_drain():
    reg = SessionControlRegistry()
    reg.push_steer("s1", "first")
    reg.push_steer("s1", "second")
    assert reg.has_steer("s1")
    assert reg.drain_steer("s1") == ["first", "second"]
    assert reg.drain_steer("s1") == []
    assert not reg.has_steer("s1")


def test_steer_rejects_empty():
    reg = SessionControlRegistry()
    with pytest.raises(ValueError):
        reg.push_steer("s1", "   ")


def test_steer_sessions_are_isolated():
    reg = SessionControlRegistry()
    reg.push_steer("s1", "a")
    assert reg.drain_steer("s2") == []
    assert reg.drain_steer("s1") == ["a"]


def test_queue_lifecycle():
    reg = SessionControlRegistry()
    m1 = reg.queue_message("s1", "task one")
    m2 = reg.queue_message("s1", "task two")
    assert [m.id for m in reg.list_queued("s1")] == [m1.id, m2.id]
    assert reg.remove_queued("s1", m1.id)
    assert not reg.remove_queued("s1", m1.id)
    popped = reg.pop_next_queued("s1")
    assert popped is not None and popped.id == m2.id
    assert reg.pop_next_queued("s1") is None


def test_clear_session():
    reg = SessionControlRegistry()
    reg.push_steer("s1", "x")
    reg.queue_message("s1", "y")
    reg.clear_session("s1")
    assert reg.drain_steer("s1") == []
    assert reg.list_queued("s1") == []


# ---------------------------------------------------------------------------
# Query-loop drain helper
# ---------------------------------------------------------------------------


def _ctx(session_id):
    from leagent.agent.tool_use_context import ToolUseContext
    from leagent.context.file_state import FileState
    from leagent.tools.executor import ToolExecutor
    from leagent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    return ToolUseContext(
        abort_event=asyncio.Event(),
        tools=registry,
        executor=ToolExecutor(registry=registry, service_manager=None),
        file_state_cache=FileState(),
        session_id=session_id,
    )


def test_drain_returns_steer_messages():
    sid = uuid4()
    get_session_control_registry().push_steer(str(sid), "change approach")
    msgs = _drain_steer_messages(_ctx(sid))
    assert len(msgs) == 1
    assert isinstance(msgs[0], SteerMessage)
    assert msgs[0].to_openai() == {"role": "user", "content": "change approach"}


def test_drain_empty_without_session():
    assert _drain_steer_messages(_ctx(None)) == []


# ---------------------------------------------------------------------------
# Engine translation: steer becomes an append-only user message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_engine_translates_steer_to_user_append():
    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig

    engine = QueryEngine(QueryEngineConfig(cwd="."))
    before = list(engine.mutable_messages)
    out = []
    async for msg in engine._map_item(SteerMessage(content="focus on tests")):
        out.append(msg)
    assert len(out) == 1
    assert out[0].type == "steer"
    assert out[0].data == {"content": "focus on tests"}
    assert engine.mutable_messages == [*before, {"role": "user", "content": "focus on tests"}]
