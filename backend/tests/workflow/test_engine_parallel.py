"""Phase 1 engine hardening: parallel scheduling, retry/backoff, timeout, ParallelNode."""

from __future__ import annotations

import asyncio
import time

import pytest

from leagent.workflow.base import WorkflowStatus
from leagent.workflow.engine import WorkflowExecutor, build_cache_set
from leagent.workflow.io import IO, Hidden, NodeOutput, Schema
from leagent.workflow.nodes import bootstrap, get_registry
from leagent.workflow.nodes.base import WorkflowNode


# ---------------------------------------------------------------------------
# Test node fixtures
# ---------------------------------------------------------------------------


class _SourceNode(WorkflowNode):
    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="_SourceNode",
            display_name="Source",
            category="test",
            inputs=[],
            outputs=[IO.String.Output(id="seed")],
            not_idempotent=True,
        )

    async def execute(self, **kwargs) -> NodeOutput:
        return NodeOutput(values=("seed",))


class _SleepNode(WorkflowNode):
    """Sleeps ``delay`` seconds then echoes its input — used to detect concurrency."""

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="_SleepNode",
            display_name="Sleep",
            category="test",
            inputs=[IO.String.Input(id="value", optional=True)],
            outputs=[IO.String.Output(id="echo")],
            not_idempotent=True,
        )

    async def execute(self, *, value: str | None = None, **kwargs) -> NodeOutput:
        await asyncio.sleep(0.2)
        return NodeOutput(values=(value or "x",))


class _CollectNode(WorkflowNode):
    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="_CollectNode",
            display_name="Collect",
            category="test",
            inputs=[IO.Array.Input(id="items")],
            outputs=[IO.Array.Output(id="out")],
            not_idempotent=True,
        )

    async def execute(self, *, items=None, **kwargs) -> NodeOutput:
        return NodeOutput(values=(list(items or []),))


class _FlakyNode(WorkflowNode):
    """Raises a transient error ``fail_times`` times, then succeeds."""

    fail_times = 2
    attempts = 0

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="_FlakyNode",
            display_name="Flaky",
            category="test",
            inputs=[],
            outputs=[IO.String.Output(id="out")],
            not_idempotent=True,
        )

    async def execute(self, **kwargs) -> NodeOutput:
        type(self).attempts += 1
        if type(self).attempts <= type(self).fail_times:
            raise ConnectionError("temporarily unavailable")
        return NodeOutput(values=("recovered",))


class _HardFailNode(WorkflowNode):
    """Raises a non-transient error (should NOT be retried)."""

    attempts = 0

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="_HardFailNode",
            display_name="HardFail",
            category="test",
            inputs=[],
            outputs=[IO.String.Output(id="out")],
            not_idempotent=True,
        )

    async def execute(self, **kwargs) -> NodeOutput:
        type(self).attempts += 1
        raise ValueError("permanent")


class _SlowNode(WorkflowNode):
    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="_SlowNode",
            display_name="Slow",
            category="test",
            inputs=[],
            outputs=[IO.String.Output(id="out")],
            not_idempotent=True,
        )

    async def execute(self, **kwargs) -> NodeOutput:
        await asyncio.sleep(1.0)
        return NodeOutput(values=("done",))


class _SetVarNode(WorkflowNode):
    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="_SetVarNode",
            display_name="SetVar",
            category="test",
            inputs=[
                IO.String.Input(id="key"),
                IO.String.Input(id="value"),
            ],
            outputs=[IO.String.Output(id="out")],
            hidden=[Hidden.WORKFLOW_STATE],
            not_idempotent=True,
        )

    async def execute(self, *, hidden=None, key: str = "", value: str = "", **kwargs) -> NodeOutput:
        state = getattr(hidden, "workflow_state", None)
        if state is not None and key:
            state.set(key, value)
        return NodeOutput(values=(value,))


@pytest.fixture(autouse=True)
async def _register_test_nodes():
    await bootstrap()
    reg = get_registry()
    for cls in (_SourceNode, _SleepNode, _CollectNode, _FlakyNode,
                _HardFailNode, _SlowNode, _SetVarNode):
        reg.register(cls)
    _FlakyNode.attempts = 0
    _HardFailNode.attempts = 0
    yield


def _link(node_id: str, slot: int = 0):
    return [node_id, slot]


@pytest.mark.asyncio
async def test_independent_branches_run_concurrently():
    """Two ready sleep nodes in the same batch should run in parallel."""
    raw = {
        "id": "par", "name": "par", "inputs": [], "outputs": [], "metadata": {},
        "nodes": {
            "source": {"class_type": "_SourceNode", "inputs": {}, "control": {}},
            "s1": {"class_type": "_SleepNode", "inputs": {"value": _link("source")}, "control": {}},
            "s2": {"class_type": "_SleepNode", "inputs": {"value": _link("source")}, "control": {}},
            "collect": {
                "class_type": "_CollectNode",
                "inputs": {"items": [_link("s1"), _link("s2")]},
                "control": {},
            },
        },
        "control": {"start": "source", "end": "collect"},
    }
    executor = WorkflowExecutor(cache_set=build_cache_set("none"), max_parallelism=8)
    start = time.monotonic()
    result = await executor.execute(raw, inputs={})
    elapsed = time.monotonic() - start

    assert result.status == WorkflowStatus.COMPLETED
    # Two 0.2s sleeps run concurrently => well under the 0.4s sequential floor.
    assert elapsed < 0.35, f"branches did not run concurrently (took {elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_sequential_when_parallelism_is_one():
    """max_parallelism=1 forces serial execution (sanity floor)."""
    raw = {
        "id": "seq", "name": "seq", "inputs": [], "outputs": [], "metadata": {},
        "nodes": {
            "source": {"class_type": "_SourceNode", "inputs": {}, "control": {}},
            "s1": {"class_type": "_SleepNode", "inputs": {"value": _link("source")}, "control": {}},
            "s2": {"class_type": "_SleepNode", "inputs": {"value": _link("source")}, "control": {}},
            "collect": {
                "class_type": "_CollectNode",
                "inputs": {"items": [_link("s1"), _link("s2")]},
                "control": {},
            },
        },
        "control": {"start": "source", "end": "collect"},
    }
    executor = WorkflowExecutor(cache_set=build_cache_set("none"), max_parallelism=1)
    start = time.monotonic()
    result = await executor.execute(raw, inputs={})
    elapsed = time.monotonic() - start

    assert result.status == WorkflowStatus.COMPLETED
    assert elapsed >= 0.4, f"expected serial execution (took {elapsed:.3f}s)"


@pytest.mark.asyncio
async def test_transient_error_is_retried():
    raw = {
        "id": "retry", "name": "retry", "inputs": [], "outputs": [], "metadata": {},
        "nodes": {
            "flaky": {
                "class_type": "_FlakyNode",
                "inputs": {},
                "control": {"max_retries": 3, "retry_delay_sec": 0.01},
            },
        },
        "control": {"start": "flaky", "end": "flaky"},
    }
    _FlakyNode.fail_times = 2
    executor = WorkflowExecutor(cache_set=build_cache_set("none"))
    result = await executor.execute(raw, inputs={})
    assert result.status == WorkflowStatus.COMPLETED
    assert _FlakyNode.attempts == 3  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_transient_error_exhausts_retries():
    raw = {
        "id": "retry2", "name": "retry2", "inputs": [], "outputs": [], "metadata": {},
        "nodes": {
            "flaky": {
                "class_type": "_FlakyNode",
                "inputs": {},
                "control": {"max_retries": 1, "retry_delay_sec": 0.01},
            },
        },
        "control": {"start": "flaky", "end": "flaky"},
    }
    _FlakyNode.fail_times = 5  # always fails within the retry budget
    executor = WorkflowExecutor(cache_set=build_cache_set("none"))
    result = await executor.execute(raw, inputs={})
    assert result.status == WorkflowStatus.FAILED
    assert _FlakyNode.attempts == 2  # initial + 1 retry


@pytest.mark.asyncio
async def test_non_transient_error_not_retried():
    raw = {
        "id": "hard", "name": "hard", "inputs": [], "outputs": [], "metadata": {},
        "nodes": {
            "boom": {
                "class_type": "_HardFailNode",
                "inputs": {},
                "control": {"max_retries": 5, "retry_delay_sec": 0.01},
            },
        },
        "control": {"start": "boom", "end": "boom"},
    }
    executor = WorkflowExecutor(cache_set=build_cache_set("none"))
    result = await executor.execute(raw, inputs={})
    assert result.status == WorkflowStatus.FAILED
    assert _HardFailNode.attempts == 1  # never retried


@pytest.mark.asyncio
async def test_workflow_timeout():
    raw = {
        "id": "timeout", "name": "timeout", "inputs": [], "outputs": [], "metadata": {},
        "nodes": {
            "slow": {"class_type": "_SlowNode", "inputs": {}, "control": {}},
        },
        "control": {"start": "slow", "end": "slow", "timeout_sec": 0.1},
    }
    executor = WorkflowExecutor(cache_set=build_cache_set("none"))
    result = await executor.execute(raw, inputs={})
    assert result.status == WorkflowStatus.TIMEOUT


@pytest.mark.asyncio
async def test_parallel_node_fan_out_and_merge():
    raw = {
        "id": "fanout", "name": "fanout", "inputs": [], "outputs": [], "metadata": {},
        "nodes": {
            "par": {
                "class_type": "ParallelNode",
                "inputs": {"merge_strategy": "collect", "output": "merged"},
                "control": {
                    "branches": [
                        {"id": "b1", "nodes": ["n1"]},
                        {"id": "b2", "nodes": ["n2"]},
                    ],
                },
            },
            "n1": {"class_type": "_SetVarNode", "inputs": {"key": "a", "value": "1"}, "control": {}},
            "n2": {"class_type": "_SetVarNode", "inputs": {"key": "b", "value": "2"}, "control": {}},
        },
        "control": {"start": "par", "end": "par"},
    }
    executor = WorkflowExecutor(cache_set=build_cache_set("none"))
    result = await executor.execute(raw, inputs={})
    assert result.status == WorkflowStatus.COMPLETED
    # The two branch nodes each ran on a forked state and produced one output.
    history = {r.node_id: r for r in result.execution_history}
    assert "par" in history
    par_meta = history["par"].metadata
    assert par_meta.get("branch_count") == 2
    assert par_meta.get("failed_count") == 0
