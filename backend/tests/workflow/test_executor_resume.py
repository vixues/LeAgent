"""Executor-level pause/resume tests for agent and human-review workflows."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.workflow.base import WorkflowStatus
from leagent.workflow.engine import WorkflowExecutor, build_cache_set
from leagent.workflow.io import load
from leagent.workflow.nodes import bootstrap

from .conftest import FakeAgentRuntime


def _agent_pause_workflow(*, include_transform: bool = False) -> dict:
    start_next = "prep" if include_transform else "agent"
    nodes = {
        "start": {
            "class_type": "StartNode",
            "inputs": {},
            "meta": {},
            "control": {"next": start_next},
        },
        "agent": {
            "class_type": "ScriptAgentNode",
            "inputs": {
                "prompt": "Ask the user a question before finishing.",
                "max_iterations": 5,
                "output": "answer",
            },
            "meta": {},
            "control": {"next": "end"},
        },
        "end": {
            "class_type": "EndNode",
            "inputs": {"result": "ok"},
            "meta": {},
            "control": {},
        },
    }
    if include_transform:
        nodes["prep"] = {
            "class_type": "TransformNode",
            "inputs": {"transform": {"seed": "cache-me"}},
            "meta": {},
            "control": {"next": "agent"},
        }

    return {
        "id": "agent_pause",
        "name": "agent pause",
        "inputs": [],
        "outputs": [],
        "metadata": {},
        "nodes": nodes,
        "control": {
            "start": "start",
            "end": "end",
            "edges": [],
            "timeout_sec": 3600,
            "max_retries": 0,
            "tags": [],
        },
    }


def _human_review_workflow() -> dict:
    return {
        "id": "human_review",
        "name": "human review",
        "inputs": [],
        "outputs": [],
        "metadata": {},
        "nodes": {
            "start": {
                "class_type": "StartNode",
                "inputs": {},
                "meta": {},
                "control": {"next": "review"},
            },
            "review": {
                "class_type": "HumanReviewNode",
                "inputs": {"reviewer": "alice@example.com", "review_prompt": "Approve?"},
                "meta": {},
                "control": {"next": "end"},
            },
            "end": {
                "class_type": "EndNode",
                "inputs": {"result": "ok"},
                "meta": {},
                "control": {},
            },
        },
        "control": {
            "start": "start",
            "end": "end",
            "edges": [],
            "timeout_sec": 3600,
            "max_retries": 0,
            "tags": [],
        },
    }


@pytest.mark.asyncio
async def test_human_review_blocks_on_first_run(progress_collector):
    await bootstrap()
    events, handler = progress_collector
    executor = WorkflowExecutor(
        cache_set=build_cache_set("none"),
        progress_handlers=[handler],
    )
    doc = load(_human_review_workflow())
    prompt_id = str(uuid4())

    result = await executor.execute_async(doc, {}, prompt_id=prompt_id)

    assert result.status == WorkflowStatus.WAITING_HUMAN
    blocked = [e for e in events if e.type == "execution_blocked"]
    assert blocked
    assert blocked[-1].node_id == "review"
    assert blocked[-1].data.get("tag") == "awaiting_review"


@pytest.mark.asyncio
async def test_agent_node_pauses_and_resumes_at_executor_level(progress_collector):
    await bootstrap()
    events, handler = progress_collector
    runtime = FakeAgentRuntime(stream_reason="awaiting_user_input")
    executor = WorkflowExecutor(
        agent_runtime=runtime,
        cache_set=build_cache_set("none"),
        progress_handlers=[handler],
    )
    doc = load(_agent_pause_workflow())
    prompt_id = str(uuid4())

    paused = await executor.execute_async(doc, {}, prompt_id=prompt_id)
    assert paused.status == WorkflowStatus.PAUSED
    assert any(e.type == "execution_blocked" for e in events)

    resumed = await executor.resume(
        doc,
        paused.state_id,
        {"answer": "yes, proceed"},
        prompt_id=prompt_id,
    )
    assert resumed.status == WorkflowStatus.COMPLETED
    assert len(runtime.resume_calls) == 1
    assert runtime.resume_calls[0]["prompt"] == "yes, proceed"
    assert len(runtime.stream_calls) == 1  # initial pause run only


@pytest.mark.asyncio
async def test_resume_injects_resume_variables():
    await bootstrap()
    runtime = FakeAgentRuntime(stream_reason="awaiting_user_input")
    executor = WorkflowExecutor(
        agent_runtime=runtime,
        cache_set=build_cache_set("none"),
    )
    doc = load(_agent_pause_workflow())
    prompt_id = str(uuid4())

    paused = await executor.execute_async(doc, {}, prompt_id=prompt_id)
    state = executor._states[str(paused.state_id)]
    assert "__resume__agent" not in state.variables

    await executor.resume(
        doc,
        paused.state_id,
        {"answer": "go"},
        prompt_id=prompt_id,
    )
    assert "__resume__agent" not in state.variables


@pytest.mark.asyncio
async def test_cache_hits_transform_before_blocked_agent(progress_collector):
    await bootstrap()
    events, handler = progress_collector
    runtime = FakeAgentRuntime(stream_reason="awaiting_user_input")
    executor = WorkflowExecutor(
        agent_runtime=runtime,
        cache_set=build_cache_set("classic"),
        progress_handlers=[handler],
    )
    doc = load(_agent_pause_workflow(include_transform=True))
    prompt_id = str(uuid4())

    paused = await executor.execute_async(doc, {}, prompt_id=prompt_id)
    assert paused.status == WorkflowStatus.PAUSED
    prep_first = [
        e for e in events
        if e.type == "executed" and e.node_id == "prep"
    ]
    assert len(prep_first) == 1
    assert prep_first[0].data.get("cached") is not True

    await executor.resume(
        doc,
        paused.state_id,
        {"answer": "ok"},
        prompt_id=prompt_id,
    )
    prep_all = [
        e for e in events
        if e.type == "executed" and e.node_id == "prep"
    ]
    assert len(prep_all) == 2
    assert prep_all[1].data.get("cached") is True
