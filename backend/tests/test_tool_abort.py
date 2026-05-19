"""Tests for cooperative tool cancellation."""

from __future__ import annotations

import asyncio

import pytest

from leagent.tools.base import (
    BaseTool,
    ToolAbortedError,
    ToolCategory,
    ToolContext,
    ToolResult,
    abortable_sleep,
)


class _SlowTool(BaseTool):
    name = "slow_tool_test"
    description = "test"
    category = ToolCategory.UTIL
    parameters: dict = {"type": "object", "properties": {}}

    async def execute(self, params: dict, context: ToolContext) -> str:
        await asyncio.sleep(5.0)
        return "done"


@pytest.mark.asyncio
async def test_abortable_sleep_raises_when_aborted() -> None:
    abort = asyncio.Event()
    ctx = ToolContext(user_id="u", session_id="s", abort_signal=abort)
    abort.set()
    with pytest.raises(ToolAbortedError):
        await abortable_sleep(2.0, ctx)


@pytest.mark.asyncio
async def test_base_tool_run_stops_on_abort_during_execute() -> None:
    abort = asyncio.Event()
    ctx = ToolContext(user_id="u", session_id="s", abort_signal=abort)
    tool = _SlowTool()
    tool.timeout_sec = 10.0

    async def _abort_soon() -> None:
        await asyncio.sleep(0.05)
        abort.set()

    asyncio.create_task(_abort_soon())
    started = asyncio.get_event_loop().time()
    result = await tool.run({}, ctx)
    elapsed = asyncio.get_event_loop().time() - started

    assert not result.success
    assert result.error == "Execution aborted"
    assert elapsed < 2.0
