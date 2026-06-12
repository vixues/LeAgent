"""Tests for durable workflow state snapshots."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.workflow.base import WorkflowState, WorkflowStatus
from leagent.workflow.engine.caching import BasicCache, CacheEntry
from leagent.workflow.state_store import (
    InMemoryWorkflowStateStore,
    WorkflowRunSnapshot,
)


@pytest.mark.asyncio
async def test_inmemory_store_roundtrip() -> None:
    store = InMemoryWorkflowStateStore()
    state = WorkflowState(
        workflow_id="wf-1",
        status=WorkflowStatus.PAUSED,
        variables={"answer": "yes"},
    )
    snap = WorkflowRunSnapshot(
        state=state,
        output_cache={"node1": {"value": [1, 2], "metadata": {}}},
        blocked_nodes=["agent_node"],
        prompt_id="prompt-abc",
    )
    await store.save(snap)
    loaded = await store.load(state.id)
    assert loaded is not None
    assert loaded.state.status == WorkflowStatus.PAUSED
    assert loaded.state.variables["answer"] == "yes"
    assert loaded.blocked_nodes == ["agent_node"]
    by_prompt = await store.load_by_prompt_id("prompt-abc")
    assert by_prompt is not None
    assert by_prompt.state.id == state.id


def test_basic_cache_snapshot_restore() -> None:
    cache = BasicCache()
    cache.set("k1", CacheEntry(value={"x": 1}))
    snap = cache.snapshot_entries()
    cache.clear()
    assert cache.get("k1") is None
    cache.restore_entries(snap)
    entry = cache.get("k1")
    assert entry is not None
    assert entry.value == {"x": 1}


@pytest.mark.asyncio
async def test_executor_resume_rehydrates_from_store() -> None:
    from leagent.workflow.engine.executor import WorkflowExecutor

    store = InMemoryWorkflowStateStore()
    state = WorkflowState(
        workflow_id="linear",
        status=WorkflowStatus.PAUSED,
        inputs={"q": "hello"},
        variables={"q": "hello"},
        current_node="step1",
    )
    await store.save(
        WorkflowRunSnapshot(
            state=state,
            output_cache={"cache-key": {"value": [1], "metadata": {}}},
            blocked_nodes=["step1"],
            prompt_id="p1",
        )
    )

    executor = WorkflowExecutor(state_store=store)
    assert str(state.id) not in executor._states

    snap = await executor.state_store.load(state.id)
    assert snap is not None
    executor._states[str(snap.state.id)] = snap.state
    executor._restore_output_cache(snap.output_cache)

    assert executor._states[str(state.id)].variables["q"] == "hello"
    assert executor.cache_set.outputs.get("cache-key") is not None
