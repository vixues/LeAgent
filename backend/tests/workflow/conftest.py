"""Shared fixtures for workflow tests."""

from __future__ import annotations

from typing import Any

import pytest

from leagent.runtime import AgentBuilder, AgentDefinition
from leagent.workflow.io import HiddenHolder


@pytest.fixture(autouse=True)
def _clean_registry():
    """Give every test a fresh node registry so side-effects don't leak."""
    from leagent.workflow.nodes.registry import reset_registry
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
async def registered_builtins():
    from leagent.workflow.nodes import bootstrap
    await bootstrap()


@pytest.fixture
def sample_canonical_document() -> dict:
    """Canonical workflow document used by multiple tests."""
    return {
        "id": "tst",
        "name": "test flow",
        "description": "",
        "inputs": [],
        "outputs": [],
        "metadata": {},
        "nodes": {
            "start": {
                "class_type": "StartNode",
                "inputs": {},
                "meta": {},
                "control": {"next": "xform"},
            },
            "xform": {
                "class_type": "TransformNode",
                "inputs": {"transform": {"name": "hello"}},
                "meta": {},
                "control": {"next": "end"},
            },
            "end": {
                "class_type": "EndNode",
                "inputs": {"result": "done"},
                "meta": {},
                "control": {},
            },
        },
        "control": {
            "start": "start",
            "end": "end",
            "edges": [],
            "timeout_sec": 3600,
            "max_retries": 3,
            "tags": [],
        },
    }


class FakeAgentRuntime:
    """Records delegate/run/resume calls for agent-backed workflow nodes."""

    def __init__(
        self,
        envelope: dict | None = None,
        *,
        stream_reason: str = "completed",
    ) -> None:
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
        self.stream_calls.append({"agent": agent, "prompt": prompt, **kwargs})
        from leagent.sdk.events import AgentEvent

        yield AgentEvent(type="tool_use", data={"name": "code_execution"})
        yield AgentEvent(type="assistant", data={"content": "standalone done"})
        yield AgentEvent(
            type="result",
            data={"reason": self._stream_reason, "checkpoint_id": "cp-123"},
        )

    async def resume(self, agent, checkpoint_id, prompt, **kwargs):
        self.resume_calls.append(
            {"agent": agent, "checkpoint_id": checkpoint_id, "prompt": prompt, **kwargs}
        )
        from leagent.sdk.events import AgentEvent

        yield AgentEvent(type="assistant", data={"content": "resumed done"})
        yield AgentEvent(
            type="result",
            data={"reason": "completed", "checkpoint_id": "cp-456"},
        )


class FakeWorkflowState:
    """Minimal WorkflowState stand-in (variables/metadata/set)."""

    def __init__(self) -> None:
        self.variables: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value

    def resolve_template(self, text: str) -> str:
        return text


@pytest.fixture
def fake_agent_runtime() -> FakeAgentRuntime:
    return FakeAgentRuntime()


@pytest.fixture
def fake_workflow_state() -> FakeWorkflowState:
    return FakeWorkflowState()


def make_hidden(
    runtime: FakeAgentRuntime | None,
    *,
    parent: Any = None,
    workflow_state: FakeWorkflowState | None = None,
    **extra: Any,
) -> HiddenHolder:
    class _Ctx:
        agent_controller = parent

    return HiddenHolder(
        unique_id="node-1",
        tool_context=_Ctx() if parent is not None else None,
        agent_runtime=runtime,
        workflow_state=workflow_state,
        **extra,
    )


@pytest.fixture
def progress_collector():
    events: list[Any] = []

    def handler(event: Any) -> None:
        events.append(event)

    return events, handler
