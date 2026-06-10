"""Editor-parity engine semantics: mute/bypass modes, human-review resume
payloads, and GenUI tree sanitization on emitted events."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.workflow.base import WorkflowStatus
from leagent.workflow.engine import WorkflowExecutor, build_cache_set
from leagent.workflow.engine.executor import _sanitize_ui
from leagent.workflow.io import load
from leagent.workflow.nodes import bootstrap


def _doc(nodes: dict, start: str = "start") -> dict:
    return {
        "id": "editor_parity",
        "name": "editor parity",
        "inputs": [],
        "outputs": [],
        "metadata": {},
        "nodes": nodes,
        "control": {
            "start": start,
            "end": "end",
            "edges": [],
            "timeout_sec": 3600,
            "max_retries": 0,
            "tags": [],
        },
    }


def _chain_doc(*, mid_mode: str) -> dict:
    """start → prep (emits "hello") → mid (mode under test) → end."""
    return _doc(
        {
            "start": {
                "class_type": "StartNode",
                "inputs": {},
                "meta": {},
                "control": {"next": "prep"},
            },
            "prep": {
                "class_type": "TransformNode",
                "inputs": {"transform": "hello"},
                "meta": {},
                "control": {"next": "mid"},
            },
            "mid": {
                "class_type": "TransformNode",
                "inputs": {"transform": ["prep", 0]},
                "meta": {"mode": mid_mode},
                "control": {"next": "end"},
            },
            "end": {
                "class_type": "EndNode",
                "inputs": {},
                "meta": {},
                "control": {},
            },
        }
    )


# ---------------------------------------------------------------------------
# Mute / bypass runner semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mute_node_is_skipped(progress_collector):
    await bootstrap()
    events, handler = progress_collector
    executor = WorkflowExecutor(
        cache_set=build_cache_set("none"), progress_handlers=[handler],
    )
    result = await executor.execute_async(
        load(_chain_doc(mid_mode="mute")), {}, prompt_id=str(uuid4()),
    )

    assert result.status == WorkflowStatus.COMPLETED
    mid_events = [e for e in events if e.type == "executed" and e.node_id == "mid"]
    assert len(mid_events) == 1
    assert mid_events[0].data["metadata"].get("mode") == "mute"
    # Muted nodes contribute no output values.
    assert mid_events[0].data["values"] == []


@pytest.mark.asyncio
async def test_bypass_node_passes_linked_input_through(progress_collector):
    await bootstrap()
    events, handler = progress_collector
    executor = WorkflowExecutor(
        cache_set=build_cache_set("none"), progress_handlers=[handler],
    )
    result = await executor.execute_async(
        load(_chain_doc(mid_mode="bypass")), {}, prompt_id=str(uuid4()),
    )

    assert result.status == WorkflowStatus.COMPLETED
    mid_events = [e for e in events if e.type == "executed" and e.node_id == "mid"]
    assert len(mid_events) == 1
    assert mid_events[0].data["metadata"].get("mode") == "bypass"
    # The type-compatible linked input ("hello" from prep) flows through.
    assert mid_events[0].data["values"] == ["hello"]


@pytest.mark.asyncio
async def test_normal_node_executes_without_mode_metadata(progress_collector):
    await bootstrap()
    events, handler = progress_collector
    executor = WorkflowExecutor(
        cache_set=build_cache_set("none"), progress_handlers=[handler],
    )
    doc = _chain_doc(mid_mode="")
    doc["nodes"]["mid"]["meta"] = {}
    result = await executor.execute_async(load(doc), {}, prompt_id=str(uuid4()))

    assert result.status == WorkflowStatus.COMPLETED
    mid_events = [e for e in events if e.type == "executed" and e.node_id == "mid"]
    assert len(mid_events) == 1
    assert "mode" not in (mid_events[0].data["metadata"] or {})
    assert mid_events[0].data["values"] == ["hello"]


# ---------------------------------------------------------------------------
# Human review resume payload
# ---------------------------------------------------------------------------


def _review_doc() -> dict:
    return _doc(
        {
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
                "inputs": {},
                "meta": {},
                "control": {},
            },
        }
    )


@pytest.mark.asyncio
async def test_human_review_consumes_resume_payload(progress_collector):
    await bootstrap()
    events, handler = progress_collector
    executor = WorkflowExecutor(
        cache_set=build_cache_set("none"), progress_handlers=[handler],
    )
    doc = load(_review_doc())
    prompt_id = str(uuid4())

    blocked = await executor.execute_async(doc, {}, prompt_id=prompt_id)
    assert blocked.status == WorkflowStatus.WAITING_HUMAN

    resumed = await executor.resume(
        doc,
        blocked.state_id,
        {"approved": True, "comments": "lgtm"},
        prompt_id=prompt_id,
    )
    assert resumed.status == WorkflowStatus.COMPLETED

    review_done = [
        e for e in events
        if e.type == "executed" and e.node_id == "review"
    ]
    assert len(review_done) == 1
    decision = review_done[0].data["values"][0]
    assert decision["approved"] is True
    assert decision["comments"] == "lgtm"
    # The resume payload was consumed — no second block was raised.
    blocked_events = [e for e in events if e.type == "execution_blocked"]
    assert len(blocked_events) == 1


@pytest.mark.asyncio
async def test_human_review_rejection_payload(progress_collector):
    await bootstrap()
    events, handler = progress_collector
    executor = WorkflowExecutor(
        cache_set=build_cache_set("none"), progress_handlers=[handler],
    )
    doc = load(_review_doc())
    prompt_id = str(uuid4())

    blocked = await executor.execute_async(doc, {}, prompt_id=prompt_id)
    resumed = await executor.resume(
        doc,
        blocked.state_id,
        {"approved": False, "comments": "needs changes"},
        prompt_id=prompt_id,
    )
    assert resumed.status == WorkflowStatus.COMPLETED
    review_done = [
        e for e in events if e.type == "executed" and e.node_id == "review"
    ]
    decision = review_done[0].data["values"][0]
    assert decision["approved"] is False
    assert decision["comments"] == "needs changes"


# ---------------------------------------------------------------------------
# GenUI tree sanitization on NodeOutput.ui
# ---------------------------------------------------------------------------


def _valid_tree() -> dict:
    return {
        "schemaVersion": "1",
        "root": {
            "nodeId": "r1",
            "kind": "Markdown",
            "props": {"content": "**hi**"},
        },
    }


def test_sanitize_ui_passes_valid_gen_ui_tree():
    ui = {"gen_ui": _valid_tree(), "other": 1}
    out = _sanitize_ui(ui)
    assert out is not None
    assert out["other"] == 1
    assert out["gen_ui"]["root"]["kind"] == "Markdown"


def test_sanitize_ui_drops_invalid_gen_ui_tree():
    ui = {"gen_ui": {"root": {"kind": "NotARealKind"}}, "review": {"id": "x"}}
    out = _sanitize_ui(ui)
    assert out is not None
    assert "gen_ui" not in out
    # The rest of the ui payload survives.
    assert out["review"] == {"id": "x"}


def test_sanitize_ui_drops_non_dict_gen_ui():
    out = _sanitize_ui({"gen_ui": "not-a-tree"})
    assert out is not None
    assert "gen_ui" not in out


def test_sanitize_ui_passthrough_without_gen_ui():
    ui = {"review": {"id": "x"}}
    assert _sanitize_ui(ui) == ui
    assert _sanitize_ui(None) is None
