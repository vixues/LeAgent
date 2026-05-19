"""In-memory prompt queue tests."""

from __future__ import annotations

import asyncio

import pytest

from leagent.workflow.queue import InMemoryPromptQueue, PromptHistoryEntry, PromptItem


@pytest.mark.asyncio
async def test_fifo_order_within_same_priority():
    queue = InMemoryPromptQueue()
    items = [
        PromptItem.new(flow_id="a", user_id=None, inputs={}, priority=5)
        for _ in range(3)
    ]
    for item in items:
        await queue.put(item)

    received = []
    for _ in range(3):
        it = await queue.get(timeout=1.0)
        assert it is not None
        received.append(it.prompt_id)

    assert received == [i.prompt_id for i in items]


@pytest.mark.asyncio
async def test_higher_priority_preempts_lower():
    queue = InMemoryPromptQueue()
    low = PromptItem.new(flow_id="a", user_id=None, inputs={}, priority=9)
    high = PromptItem.new(flow_id="b", user_id=None, inputs={}, priority=1)
    await queue.put(low)
    await queue.put(high)

    first = await queue.get(timeout=1.0)
    second = await queue.get(timeout=1.0)
    assert first is not None and second is not None
    assert first.prompt_id == high.prompt_id
    assert second.prompt_id == low.prompt_id


@pytest.mark.asyncio
async def test_history_roundtrip():
    queue = InMemoryPromptQueue()
    item = PromptItem.new(flow_id="a", user_id=None, inputs={})
    await queue.put(item)
    got = await queue.get(timeout=1.0)
    assert got is not None

    await queue.task_done(
        got,
        PromptHistoryEntry(
            prompt_id=got.prompt_id,
            status="completed",
            outputs={"answer": 42},
            duration_ms=10,
        ),
    )
    hist = await queue.history(got.prompt_id)
    assert hist is not None
    assert hist.status == "completed"
    assert hist.outputs == {"answer": 42}


@pytest.mark.asyncio
async def test_get_times_out():
    queue = InMemoryPromptQueue()
    result = await queue.get(timeout=0.05)
    assert result is None


@pytest.mark.asyncio
async def test_queue_position_reports_offset():
    queue = InMemoryPromptQueue()
    items = [
        PromptItem.new(flow_id="a", user_id=None, inputs={}, priority=5)
        for _ in range(3)
    ]
    for item in items:
        await queue.put(item)

    pos = await queue.queue_position(items[1].prompt_id)
    assert pos is not None
    assert pos >= 1


@pytest.mark.asyncio
async def test_wipe_clears_queue():
    queue = InMemoryPromptQueue()
    await queue.put(PromptItem.new(flow_id="a", user_id=None, inputs={}))
    await queue.wipe()
    assert await queue.size() == 0
