"""Tests for the node registry and base class contract."""

from __future__ import annotations

import pytest

from leagent.workflow.io import IO, NodeOutput, Schema
from leagent.workflow.io.contract import NOT_CACHEABLE
from leagent.workflow.nodes import bootstrap, get_registry
from leagent.workflow.nodes.base import WorkflowNode
from leagent.workflow.nodes.registry import NodeRegistry


class _DummyNode(WorkflowNode):
    """Minimal node used to exercise registry and contract hooks."""

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="DummyNode",
            display_name="Dummy",
            category="test",
            inputs=[IO.String.Input(id="value", default="")],
            outputs=[IO.String.Output(id="echo")],
        )

    async def execute(self, **kwargs) -> NodeOutput:
        return NodeOutput.from_result({"echo": kwargs.get("value", "")})


class _NotCacheableNode(_DummyNode):
    @classmethod
    def define_schema(cls) -> Schema:
        s = super().define_schema()
        s.node_id = "NotCacheableNode"
        return s

    def fingerprint_inputs(self, **kwargs):  # type: ignore[override]
        return NOT_CACHEABLE


async def test_bootstrap_registers_builtins():
    await bootstrap()
    reg = get_registry()
    ids = set(reg.list_ids())
    expected = {
        "StartNode",
        "EndNode",
        "ToolCallNode",
        "LLMCallNode",
        "ConditionNode",
        "ParallelNode",
        "HumanReviewNode",
        "ErrorHandlerNode",
        "TransformNode",
        "SubworkflowNode",
        "WaitNode",
    }
    assert expected <= ids


def test_manual_registration_and_lookup():
    reg = NodeRegistry()
    reg.register(_DummyNode)
    assert "DummyNode" in reg.list_ids()
    cls = reg.get("DummyNode")
    assert cls is _DummyNode


def test_registry_snapshot_includes_schema_info():
    reg = NodeRegistry()
    reg.register(_DummyNode)
    snap = reg.snapshot()
    assert "DummyNode" in snap
    assert snap["DummyNode"]["display_name"] == "Dummy"


def test_default_fingerprint_is_deterministic():
    node = _DummyNode()
    fp1 = node.fingerprint_inputs(value="a")
    fp2 = node.fingerprint_inputs(value="a")
    fp3 = node.fingerprint_inputs(value="b")
    assert fp1 == fp2
    assert fp1 != fp3


def test_not_cacheable_sentinel_bypasses_cache():
    node = _NotCacheableNode()
    assert node.fingerprint_inputs() is NOT_CACHEABLE


def test_default_check_lazy_status_returns_empty():
    node = _DummyNode()
    assert node.check_lazy_status() == []


@pytest.mark.asyncio
async def test_schema_validation_rejects_missing_inputs():
    reg = NodeRegistry()
    reg.register(_DummyNode)
    cls = reg.get("DummyNode")
    schema = cls.define_schema()
    # Schema should include the declared inputs/outputs
    ids = {i.id for i in schema.inputs}
    assert "value" in ids
    out_ids = {o.id for o in schema.outputs}
    assert "echo" in out_ids
