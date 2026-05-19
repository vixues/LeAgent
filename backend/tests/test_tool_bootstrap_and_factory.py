"""Tests for the unified tool bootstrap and the workflow tool factory.

These cover the integration surface that was added as part of the
tool-system upgrade:

* ``leagent.bootstrap.tools.bootstrap_tools`` wires up the tool
  registry + workflow node registry from a cold start.
* ``leagent.workflow.io.schema_bridge.json_schema_to_inputs``
  correctly turns a tool's JSON schema into typed workflow inputs.
* ``leagent.workflow.nodes.tool_factory.build_node_class`` produces
  a runnable ``WorkflowNode`` subclass from an arbitrary tool.
"""

from __future__ import annotations

import pytest

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.registry import ToolRegistry


class _EchoTool(BaseTool):
    """Minimal in-test tool used to exercise the bridge/factory."""

    name = "echo_dummy"
    description = "Return the input text unchanged — used in tests only."
    category = ToolCategory.UTIL
    is_read_only = True

    @property
    def parameters(self) -> dict[str, object]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Payload."},
                "count": {"type": "integer", "default": 1, "minimum": 1},
                "upper": {"type": "boolean", "default": False},
            },
            "required": ["text"],
        }

    async def execute(
        self, params: dict[str, object], context: ToolContext
    ) -> dict[str, object]:
        text = str(params.get("text", ""))
        count = int(params.get("count", 1) or 1)
        if params.get("upper"):
            text = text.upper()
        return {"echoed": text * count}


def test_schema_bridge_maps_primitive_types() -> None:
    from leagent.workflow.io import IO, json_schema_to_inputs

    tool = _EchoTool()
    inputs = json_schema_to_inputs(tool.parameters)
    by_id = {inp.id: inp for inp in inputs}

    assert set(by_id) == {"text", "count", "upper"}
    assert isinstance(by_id["text"], IO.String.Input)
    assert isinstance(by_id["count"], IO.Int.Input)
    assert isinstance(by_id["upper"], IO.Boolean.Input)

    # Required flag round-trips.
    assert by_id["text"].optional is False
    assert by_id["count"].optional is True
    # min/default survived the conversion.
    assert by_id["count"].min == 1
    assert by_id["count"].default == 1


def test_tool_factory_builds_runnable_node() -> None:
    from leagent.workflow.nodes.tool_factory import (
        build_node_class,
        clear_factory_cache,
    )

    clear_factory_cache()
    node_cls = build_node_class(_EchoTool())
    assert node_cls.NODE_ID == "Tool.echo_dummy"

    schema = node_cls.get_schema()
    # The schema must include every parameter *plus* at least one output.
    input_ids = {inp.id for inp in schema.inputs}
    assert {"text", "count", "upper"} <= input_ids
    assert len(schema.outputs) >= 1


@pytest.mark.asyncio
async def test_bootstrap_registers_tool_nodes() -> None:
    from leagent.bootstrap import bootstrap_tools
    from leagent.tools.registry import get_registry
    from leagent.workflow.nodes.registry import get_registry as get_node_registry

    summary = await bootstrap_tools()
    reg = get_registry()
    nodes = get_node_registry()

    # Essentials that every deployment ships with.
    tool_names = {tool.name for tool in reg.list_tools()}
    for must in {"code_execution", "uv_pip_install", "data_clean", "data_transform"}:
        assert must in tool_names, f"expected '{must}' in bootstrapped tools"

    # Factory-generated workflow nodes exist for those tools.
    for must in {"code_execution", "data_clean"}:
        assert f"Tool.{must}" in nodes.list_ids()

    # Builtin workflow nodes registered alongside tool nodes.
    assert "ScriptNode" in nodes.list_ids()
    assert "ScriptAgentNode" in nodes.list_ids()

    # Summary shape is stable for callers that log it.
    assert summary["tools"] > 0
    assert summary["node_summary"]["builtin"]
