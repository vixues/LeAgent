"""SSE wire-contract regression for the chat stream adapter.

Phase 1 of the agent-runtime upgrade reroutes chat through the SDK kernel
``run_loop``. ``AgentEvent`` shares the exact ``{type, data}`` shape of the
former ``SDKMessage``, so the ``AgentController`` -> ``StreamHandler`` ->
:func:`run_agent_stream` mapping (and therefore the SSE ``type`` strings the
frontend depends on) must be unchanged.

This test pins those wire ``type`` strings and the derived ``task_progress``
events so a regression in the kernel reroute is caught before merge.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from leagent.agent.base import StreamEvent
from leagent.api.v1.chat.agent_stream import run_agent_stream


class _FakeAgent:
    """Minimal agent whose ``run_stream`` replays a fixed event script."""

    def __init__(self, events: list[StreamEvent]) -> None:
        self._events = events

    async def run_stream(self, *args, **kwargs) -> AsyncIterator[StreamEvent]:
        for event in self._events:
            yield event


@pytest.mark.asyncio
async def test_run_agent_stream_preserves_wire_type_strings() -> None:
    events = [
        StreamEvent(type="token", data={"token": "Hel"}),
        StreamEvent(type="token", data={"token": "lo"}),
        StreamEvent(type="thinking", data={"content": "pondering"}),
        StreamEvent(type="tool_call", data={"id": "c1", "name": "echo"}),
        StreamEvent(
            type="tool_result",
            data={"tool_call_id": "c1", "name": "echo", "success": True},
        ),
        StreamEvent(type="complete", data={"text": "Hello"}),
    ]
    agent = _FakeAgent(events)

    out = [
        (etype, data, acc)
        async for (etype, data, acc) in run_agent_stream(
            agent, "hi", uuid4(), uuid4()
        )
    ]

    types = [etype for etype, _, _ in out]
    assert types == [
        "token",
        "token",
        "thinking",
        "tool_call",
        "tool_result",
        "complete",
    ]

    # Token events accumulate text; complete reflects the running buffer.
    assert out[1][2] == "Hello"
    assert out[-1][0] == "complete"
    assert out[-1][2] == "Hello"


@pytest.mark.asyncio
async def test_run_agent_stream_derives_task_progress_from_todo_write() -> None:
    events = [
        StreamEvent(type="tool_call", data={"id": "t1", "name": "todo_write"}),
        StreamEvent(
            type="tool_result",
            data={
                "name": "todo_write",
                "success": True,
                "data": {
                    "todos": [
                        {"id": "a", "content": "Step A", "status": "in_progress"},
                        {"id": "b", "content": "Step B", "status": "pending"},
                    ]
                },
            },
        ),
    ]
    agent = _FakeAgent(events)

    out = [
        (etype, data)
        async for (etype, data, _acc) in run_agent_stream(
            agent, "hi", uuid4(), uuid4()
        )
    ]

    progress = [data for etype, data in out if etype == "task_progress"]
    # One progress event for the call (UI spinner) + one per derived todo item.
    assert any(p.get("label") == "Step A" and p["status"] == "in_progress" for p in progress)
    assert any(p.get("label") == "Step B" and p["status"] == "pending" for p in progress)


@pytest.mark.asyncio
async def test_complete_event_carries_terminal_reason_and_checkpoint_id() -> None:
    """The ``complete`` SSE event must surface ``terminal_reason`` and ``checkpoint_id``."""
    events = [
        StreamEvent(
            type="complete",
            data={
                "text": "Done",
                "success": True,
                "partial": False,
                "terminal_reason": "max_turns",
                "checkpoint_id": "cp-abc",
            },
        ),
    ]
    agent = _FakeAgent(events)

    out = [
        (etype, data)
        async for (etype, data, _acc) in run_agent_stream(
            agent, "hi", uuid4(), uuid4()
        )
    ]

    complete_data = next(d for t, d in out if t == "complete")
    assert complete_data.get("terminal_reason") == "max_turns"
    assert complete_data.get("checkpoint_id") == "cp-abc"


@pytest.mark.asyncio
async def test_error_event_carries_terminal_reason() -> None:
    """The ``error`` SSE event passes through ``terminal_reason`` when present."""
    events = [
        StreamEvent(
            type="error",
            data={
                "error": "context overflow",
                "terminal_reason": "prompt_too_long",
            },
        ),
    ]
    agent = _FakeAgent(events)

    out = [
        (etype, data)
        async for (etype, data, _acc) in run_agent_stream(
            agent, "hi", uuid4(), uuid4()
        )
    ]

    error_data = next(d for t, d in out if t == "error")
    assert error_data.get("error") == "context overflow"
    assert error_data.get("terminal_reason") == "prompt_too_long"


@pytest.mark.asyncio
async def test_run_agent_stream_surfaces_errors_without_crashing() -> None:
    class _Boom:
        async def run_stream(self, *args, **kwargs):
            raise RuntimeError("kaboom")
            yield  # pragma: no cover - generator marker

    out = [
        (etype, data)
        async for (etype, data, _acc) in run_agent_stream(
            _Boom(), "hi", uuid4(), uuid4()
        )
    ]

    assert out[-1][0] == "error"
    assert "kaboom" in out[-1][1]["error"]
