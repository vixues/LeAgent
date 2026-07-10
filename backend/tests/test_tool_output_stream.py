"""Tests for the live tool-output bus and engine streaming integration."""

from __future__ import annotations

import asyncio
import sys

import pytest

from leagent.services.execution.output_stream import (
    ToolOutputBus,
    get_tool_output_bus,
    reset_tool_output_bus,
)


@pytest.fixture(autouse=True)
def _fresh_bus():
    reset_tool_output_bus()
    yield
    reset_tool_output_bus()


# ---------------------------------------------------------------------------
# Bus semantics
# ---------------------------------------------------------------------------


def test_publish_and_full_output():
    bus = ToolOutputBus()
    bus.publish("s1", "c1", "stdout", "hello ", tool_name="project_shell")
    bus.publish("s1", "c1", "stdout", "world\n")
    bus.publish("s1", "c1", "stderr", "warn\n")
    bus.publish("s1", "c1", "system", "", done=True, exit_code=0)

    out = bus.get_full_output("s1", "c1")
    assert out is not None
    assert out["stdout"] == "hello world\n"
    assert out["stderr"] == "warn\n"
    assert out["closed"] is True
    assert out["tool_name"] == "project_shell"


def test_missing_output_returns_none():
    bus = ToolOutputBus()
    assert bus.get_full_output("s1", "nope") is None


def test_backlog_is_bounded():
    bus = ToolOutputBus()
    big = "x" * 300_000
    for _ in range(10):  # 3 MB > 2 MB limit
        bus.publish("s1", "c1", "stdout", big)
    out = bus.get_full_output("s1", "c1")
    assert out is not None
    assert out["truncated_head"] is True
    assert out["total_bytes"] <= 2 * 1024 * 1024


def test_list_calls():
    bus = ToolOutputBus()
    bus.publish("s1", "c1", "stdout", "a")
    bus.publish("s1", "c2", "stdout", "b")
    calls = bus.list_calls("s1")
    assert [c["tool_call_id"] for c in calls] == ["c1", "c2"]


@pytest.mark.asyncio
async def test_subscribe_receives_live_chunks():
    bus = ToolOutputBus()
    received: list[str] = []

    async def _consume():
        async for chunk in bus.subscribe("s1"):
            received.append(chunk.data)
            if chunk.done:
                break

    task = asyncio.create_task(_consume())
    await asyncio.sleep(0.05)
    bus.publish("s1", "c1", "stdout", "line1\n")
    bus.publish("s1", "c1", "system", "", done=True, exit_code=0)
    await asyncio.wait_for(task, timeout=2.0)
    assert received[0] == "line1\n"


# ---------------------------------------------------------------------------
# Engine integration: incremental publish while a command runs
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX shell test")
@pytest.mark.asyncio
async def test_engine_streams_output_live():
    from leagent.services.execution.engine import ExecutionEngine
    from leagent.services.execution.policies import ExecutionPolicy

    engine = ExecutionEngine()
    bus = get_tool_output_bus()

    result = await engine.shell_command(
        ["/bin/echo", "streamed-hello"],
        policy=ExecutionPolicy(allowed_binaries=None),
        session_id="sess-stream",
        output_meta={
            "tool_call_id": "call-42",
            "tool_name": "project_shell",
            "source": "shell",
        },
    )
    assert result.status == "ok"
    assert "streamed-hello" in result.stdout

    retained = bus.get_full_output("sess-stream", "call-42")
    assert retained is not None
    assert "streamed-hello" in retained["stdout"]
    assert retained["closed"] is True


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX shell test")
@pytest.mark.asyncio
async def test_engine_without_meta_does_not_publish():
    from leagent.services.execution.engine import ExecutionEngine
    from leagent.services.execution.policies import ExecutionPolicy

    engine = ExecutionEngine()
    bus = get_tool_output_bus()

    result = await engine.shell_command(
        ["/bin/echo", "quiet"],
        policy=ExecutionPolicy(allowed_binaries=None),
        session_id="sess-quiet",
    )
    assert result.status == "ok"
    assert bus.list_calls("sess-quiet") == []


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX shell test")
@pytest.mark.asyncio
async def test_engine_streaming_with_stdin():
    from leagent.services.execution.engine import ExecutionEngine
    from leagent.services.execution.policies import ExecutionPolicy

    engine = ExecutionEngine()
    result = await engine.shell_command(
        ["/bin/cat"],
        policy=ExecutionPolicy(allowed_binaries=None),
        stdin_data=b"piped-input\n",
        session_id="sess-stdin",
        output_meta={
            "tool_call_id": "call-stdin",
            "tool_name": "project_shell",
            "source": "shell",
        },
    )
    assert result.status == "ok"
    assert "piped-input" in result.stdout
