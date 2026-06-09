"""Tests for the ``Agent.<name>`` workflow node factory.

The factory lifts every registered :class:`AgentDefinition` into a
generated :class:`WorkflowNode` that delegates to the unified
:class:`AgentRuntime` injected on the :class:`HiddenHolder`.
"""

from __future__ import annotations

import pytest

from leagent.runtime import AgentBuilder, AgentDefinition, AgentRegistry
from leagent.workflow.io import HiddenHolder
from leagent.workflow.nodes.agent_node_factory import (
    build_agent_node_class,
    clear_factory_cache,
    register_agent_nodes,
)
from leagent.workflow.nodes.registry import NodeRegistry


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_factory_cache()
    yield
    clear_factory_cache()


class _FakeController:
    """Stand-in for AgentController so isinstance-free delegate paths run."""


class _FakeRuntime:
    """Records the delegate/run call and returns a canned envelope."""

    def __init__(self, envelope: dict | None = None) -> None:
        self.delegate_calls: list[dict] = []
        self._envelope = envelope or {
            "text": "done",
            "success": True,
            "steps_count": 3,
            "partial": False,
        }

    def resolve(self, name: str) -> AgentDefinition:
        return AgentBuilder(name).build()

    async def delegate(self, parent, agent, prompt, **kwargs):
        self.delegate_calls.append(
            {"parent": parent, "agent": agent, "prompt": prompt, **kwargs}
        )
        return dict(self._envelope)


def _hidden(runtime, *, parent=None, **extra) -> HiddenHolder:
    class _Ctx:
        agent_controller = parent

    return HiddenHolder(
        unique_id="node-1",
        tool_context=_Ctx() if parent is not None else None,
        agent_runtime=runtime,
        **extra,
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_generated_node_schema_shape() -> None:
    definition = AgentBuilder("support_agent").describe("Support").build()
    cls = build_agent_node_class(definition)
    schema = cls.get_schema()

    assert cls.NODE_ID == "Agent.support_agent"
    assert schema.category == "agents"
    input_ids = {i.id for i in schema.inputs}
    assert {"prompt", "max_turns", "allowed_tools", "project_path", "read_only", "output"} <= input_ids
    assert schema.return_names() == ("text", "success", "steps_count")
    assert schema.metadata["agent_name"] == "support_agent"


def test_build_is_cached_per_agent() -> None:
    d = AgentBuilder("x").build()
    a = build_agent_node_class(d)
    b = build_agent_node_class(d)
    assert a is b


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_agent_nodes_registers_all() -> None:
    agent_reg = AgentRegistry()
    agent_reg.register(AgentBuilder("alpha").build())
    agent_reg.register(AgentBuilder("beta").build())
    node_reg = NodeRegistry()

    ids = register_agent_nodes(node_reg, agent_reg)
    assert set(ids) == {"Agent.alpha", "Agent.beta"}


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_delegates_through_runtime() -> None:
    cls = build_agent_node_class(AgentBuilder("script_agent").build())
    node = cls()
    runtime = _FakeRuntime()
    parent = _FakeController()

    out = await node.execute(
        hidden=_hidden(runtime, parent=parent),
        prompt="compute fibonacci",
        max_turns=7,
    )

    assert out.error is None
    assert out.as_tuple() == ("done", True, 3)
    assert len(runtime.delegate_calls) == 1
    call = runtime.delegate_calls[0]
    assert call["agent"] == "script_agent"
    assert call["prompt"] == "compute fibonacci"
    assert call["max_turns"] == 7


@pytest.mark.asyncio
async def test_execute_requires_runtime() -> None:
    cls = build_agent_node_class(AgentBuilder("x").build())
    node = cls()
    out = await node.execute(hidden=_hidden(None), prompt="hi")
    assert out.error is not None
    assert "runtime" in out.error.lower()


@pytest.mark.asyncio
async def test_execute_requires_prompt() -> None:
    cls = build_agent_node_class(AgentBuilder("x").build())
    node = cls()
    runtime = _FakeRuntime()
    out = await node.execute(hidden=_hidden(runtime, parent=_FakeController()), prompt="  ")
    assert out.error is not None
    assert "prompt" in out.error.lower()


@pytest.mark.asyncio
async def test_execute_rejects_relative_project_path() -> None:
    cls = build_agent_node_class(AgentBuilder("coding_agent").build())
    node = cls()
    runtime = _FakeRuntime()
    out = await node.execute(
        hidden=_hidden(runtime, parent=_FakeController()),
        prompt="fix bug",
        project_path="relative/dir",
    )
    assert out.error is not None
    assert "absolute" in out.error.lower()


@pytest.mark.asyncio
async def test_execute_passes_project_path_as_tool_extra(tmp_path) -> None:
    cls = build_agent_node_class(AgentBuilder("coding_agent").build())
    node = cls()
    runtime = _FakeRuntime()
    out = await node.execute(
        hidden=_hidden(runtime, parent=_FakeController()),
        prompt="implement feature",
        project_path=str(tmp_path),
        read_only=True,
    )
    assert out.error is None
    call = runtime.delegate_calls[0]
    assert call["cwd"] == str(tmp_path)
    assert call["tool_extra"] == {"project_roots": [str(tmp_path)]}
    # read_only restricts to investigation tools when no explicit allow-list
    assert call["allowed_tools"] == [
        "project_read",
        "project_grep",
        "project_glob",
        "project_tree",
    ]
