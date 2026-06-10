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

    def __init__(self, envelope: dict | None = None, *, stream_reason: str = "completed") -> None:
        self.delegate_calls: list[dict] = []
        self.stream_calls: list[dict] = []
        self.resume_calls: list[dict] = []
        self._stream_reason = stream_reason
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

    async def stream(self, agent, prompt, **kwargs):
        """Yield a minimal standalone event stream."""
        self.stream_calls.append({"agent": agent, "prompt": prompt, **kwargs})
        from leagent.sdk.events import AgentEvent

        yield AgentEvent(type="tool_use", data={"name": "code_execution"})
        yield AgentEvent(type="assistant", data={"content": "standalone done"})
        yield AgentEvent(
            type="result",
            data={"reason": self._stream_reason, "checkpoint_id": "cp-123"},
        )

    async def resume(self, agent, checkpoint_id, prompt, **kwargs):
        """Yield a resumed-turn event stream."""
        self.resume_calls.append(
            {"agent": agent, "checkpoint_id": checkpoint_id, "prompt": prompt, **kwargs}
        )
        from leagent.sdk.events import AgentEvent

        yield AgentEvent(type="assistant", data={"content": "resumed done"})
        yield AgentEvent(
            type="result",
            data={"reason": "completed", "checkpoint_id": "cp-456"},
        )


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
    assert schema.return_names() == (
        "text",
        "success",
        "steps_count",
        "checkpoint_id",
        "activity",
        "produced_files",
    )
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
    assert out.as_tuple() == ("done", True, 3, "", [], [])
    assert len(runtime.delegate_calls) == 1
    call = runtime.delegate_calls[0]
    assert call["agent"] == "script_agent"
    assert call["prompt"] == "compute fibonacci"
    assert call["max_turns"] == 7


@pytest.mark.asyncio
async def test_execute_falls_back_to_standalone_run() -> None:
    """Without a parent controller the node streams a standalone run."""
    cls = build_agent_node_class(AgentBuilder("script_agent").build())
    node = cls()
    runtime = _FakeRuntime()

    out = await node.execute(hidden=_hidden(runtime), prompt="compute fibonacci")

    assert out.error is None
    text, success, steps, checkpoint_id, activity, produced = out.as_tuple()
    assert text == "standalone done"
    assert success is True
    assert steps == 1
    assert checkpoint_id == "cp-123"
    assert any(row.get("type") == "tool_use" for row in activity)
    # delegated path must NOT have been taken
    assert runtime.delegate_calls == []
    assert len(runtime.stream_calls) == 1
    assert out.metadata.get("mode") == "standalone"


class _FakeState:
    """Minimal WorkflowState stand-in (variables/metadata/set)."""

    def __init__(self) -> None:
        self.variables: dict = {}
        self.metadata: dict = {}

    def set(self, key, value) -> None:
        self.variables[key] = value

    def resolve_template(self, text):
        return text


@pytest.mark.asyncio
async def test_standalone_awaiting_user_input_pauses_workflow() -> None:
    """An agent turn that pauses for user input blocks the run and stashes
    its kernel checkpoint for the resume path."""
    cls = build_agent_node_class(AgentBuilder("script_agent").build())
    node = cls()
    runtime = _FakeRuntime(stream_reason="awaiting_user_input")
    state = _FakeState()

    out = await node.execute(
        hidden=_hidden(runtime, workflow_state=state),
        prompt="do something interactive",
    )

    assert out.error is None
    assert out.block_execution == "awaiting_user_input"
    assert out.ui["checkpoint_id"] == "cp-123"
    assert out.ui["question"] == "standalone done"
    assert state.metadata["agent_checkpoints"]["node-1"] == "cp-123"


@pytest.mark.asyncio
async def test_resume_continues_from_checkpoint() -> None:
    """When the executor re-runs a paused node with resume data, the node
    resumes the turn from its checkpoint instead of starting over."""
    cls = build_agent_node_class(AgentBuilder("script_agent").build())
    node = cls()
    runtime = _FakeRuntime()
    state = _FakeState()
    state.variables["__resume__node-1"] = {"answer": "yes, proceed"}
    state.metadata["agent_checkpoints"] = {"node-1": "cp-123"}

    out = await node.execute(
        hidden=_hidden(runtime, workflow_state=state),
        prompt="original prompt",
    )

    assert out.error is None
    assert len(runtime.resume_calls) == 1
    call = runtime.resume_calls[0]
    assert call["checkpoint_id"] == "cp-123"
    assert call["prompt"] == "yes, proceed"
    # No fresh stream/delegate run was started.
    assert runtime.stream_calls == []
    assert runtime.delegate_calls == []

    text, success, _steps, checkpoint_id, _activity, _produced = out.as_tuple()
    assert text == "resumed done"
    assert success is True
    assert checkpoint_id == "cp-456"
    assert out.metadata["mode"] == "resume"
    assert out.metadata["resumed_from"] == "cp-123"
    # Resume payload is consumed so a later re-run starts fresh.
    assert "__resume__node-1" not in state.variables


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
