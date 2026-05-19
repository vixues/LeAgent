"""Tests for :mod:`leagent.agent.subagent` (fork_subagent + AgentTool).

These tests validate the refactor where ``fork_subagent`` sits on top of
``QueryEngine.fork()`` instead of owning its own think-act loop. We stub
a minimal ``QueryEngine`` so the tests run without an LLM and without
exercising the real network-bound engine.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from uuid import UUID, uuid4

import pytest

from leagent.agent.query_engine import QueryEngine
from leagent.agent.subagent import (
    AgentTool,
    fork_subagent,
    _filter_registry,
    _paths_from_unified_diff,
    _run_engine,
)
from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Tool stubs used to probe allow/deny filtering.
# ---------------------------------------------------------------------------


class _StubTool(BaseTool):
    def __init__(self, name: str) -> None:
        self._name = name
        super().__init__()

    name = "stub"  # overwritten in __init__
    description = "stub"
    category = ToolCategory.UTIL
    is_concurrency_safe = True
    is_read_only = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(
        self, params: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        return {"ok": True, "name": self._name}


def _tool(name: str) -> _StubTool:
    t = _StubTool(name)
    t.name = name
    return t


def _registry_with(*names: str) -> ToolRegistry:
    reg = ToolRegistry()
    for n in names:
        reg.register(_tool(n))
    return reg


# ---------------------------------------------------------------------------
# Minimal QueryEngine stub.
# ---------------------------------------------------------------------------


@dataclass
class _StubSDKMessage:
    type: str
    data: dict[str, Any]


@dataclass
class _StubConfig:
    tools: ToolRegistry
    max_turns: int = 10
    prompt_variant: str | None = None


class _StubEngine(QueryEngine):  # type: ignore[misc]
    """A tiny stand-in for :class:`QueryEngine` for subagent tests.

    We subclass ``QueryEngine`` (skipping ``super().__init__``) so the
    ``isinstance(parent, QueryEngine)`` gate inside ``fork_subagent``
    accepts the stub without us having to wire up a real engine.
    """

    def __init__(
        self,
        tools: ToolRegistry,
        *,
        script: list[_StubSDKMessage] | None = None,
        session_id: UUID | None = None,
        abort_event: asyncio.Event | None = None,
    ) -> None:
        # Intentionally skip QueryEngine.__init__ — we override every
        # attribute / method that ``fork_subagent`` actually touches.
        self.config = _StubConfig(tools=tools)  # type: ignore[assignment]
        self.session_id = session_id or uuid4()
        self.abort_event = abort_event or asyncio.Event()
        self._script = script or [
            _StubSDKMessage(type="assistant", data={"content": "hello from child"}),
            _StubSDKMessage(type="result", data={"reason": "completed"}),
        ]
        self.last_prompt: str | None = None
        self.fork_calls: list[dict[str, Any]] = []

    def fork(
        self,
        *,
        system_prompt: str | None = None,
        tools: ToolRegistry | None = None,
        prompt_variant: str | None = None,
        executor: Any = None,
    ) -> "_StubEngine":
        self.fork_calls.append(
            {
                "system_prompt": system_prompt,
                "tools": tools,
                "prompt_variant": prompt_variant,
                "executor": executor,
            }
        )
        child = _StubEngine(
            tools=tools or self.config.tools,
            script=list(self._script),
            abort_event=asyncio.Event(),
        )
        child.config.max_turns = self.config.max_turns
        return child

    def abort(self) -> None:
        self.abort_event.set()

    async def submit_message(self, prompt: str) -> AsyncIterator[_StubSDKMessage]:  # type: ignore[override]
        self.last_prompt = prompt
        for msg in self._script:
            yield msg


# ---------------------------------------------------------------------------
# _filter_registry
# ---------------------------------------------------------------------------


class TestSubagentPathHelpers:
    def test_paths_from_unified_diff_normalises_prefixes(self) -> None:
        diff = "--- a/pkg/mod.py\n+++ b/pkg/mod.py\n@@\n-a\n+b\n"
        paths = _paths_from_unified_diff(diff)
        assert "pkg/mod.py" in paths


@pytest.mark.asyncio
class TestRunEngineActivity:
    async def test_collects_activity_and_changed_files(self) -> None:
        script = [
            _StubSDKMessage(
                type="tool_use",
                data={
                    "id": "tc1",
                    "name": "project_edit",
                    "input": {"path": "src/a.ts"},
                },
            ),
            _StubSDKMessage(
                type="tool_result",
                data={
                    "tool_use_id": "tc1",
                    "name": "project_edit",
                    "success": True,
                    "content": "replaced",
                },
            ),
            _StubSDKMessage(
                type="tool_use",
                data={
                    "id": "tc2",
                    "name": "project_apply_patch",
                    "input": {"diff": "--- a/x.py\n+++ b/x.py\n"},
                },
            ),
            _StubSDKMessage(
                type="tool_result",
                data={
                    "tool_use_id": "tc2",
                    "name": "project_apply_patch",
                    "success": True,
                    "content": "ok",
                },
            ),
            _StubSDKMessage(type="result", data={"reason": "completed"}),
        ]
        eng = _StubEngine(tools=_registry_with("a"), script=script)
        out = await _run_engine(eng, "task")  # type: ignore[arg-type]
        assert out["success"] is True
        assert "src/a.ts" in out["changed_files"]
        assert "x.py" in out["changed_files"]
        assert len(out["activity"]) == 2
        assert out["activity"][0]["tool"] == "project_edit"
        assert out["activity"][0]["path"] == "src/a.ts"
        assert out["activity"][0].get("summary")
        assert out["activity"][1]["tool"] == "project_apply_patch"

    async def test_verification_gap_when_coding_agent_skips_shell(self) -> None:
        script = [
            _StubSDKMessage(
                type="tool_use",
                data={
                    "id": "tc1",
                    "name": "project_edit",
                    "input": {"path": "src/a.ts"},
                },
            ),
            _StubSDKMessage(
                type="tool_result",
                data={
                    "tool_use_id": "tc1",
                    "name": "project_edit",
                    "success": True,
                    "content": "replaced",
                },
            ),
            _StubSDKMessage(type="result", data={"reason": "completed"}),
        ]
        eng = _StubEngine(tools=_registry_with("a"), script=script)
        eng.config.prompt_variant = "coding_agent"  # type: ignore[attr-defined]
        out = await _run_engine(eng, "task")  # type: ignore[arg-type]
        assert out["partial"] is True
        assert out.get("verification_gap")
        assert out["success"] is False


class TestFilterRegistry:
    def test_no_lists_inherits_everything(self) -> None:
        source = _registry_with("a", "b", "c")
        child = _filter_registry(source, allowed_tools=None, denied_tools=None)
        names = {t.name for t in child.list_tools()}
        assert names == {"a", "b", "c"}

    def test_allowed_whitelist(self) -> None:
        source = _registry_with("a", "b", "c")
        child = _filter_registry(source, allowed_tools=["a", "c"], denied_tools=None)
        names = {t.name for t in child.list_tools()}
        assert names == {"a", "c"}

    def test_denied_applies_over_allowed(self) -> None:
        source = _registry_with("a", "b", "c")
        child = _filter_registry(
            source, allowed_tools=["a", "b", "c"], denied_tools=["b"]
        )
        names = {t.name for t in child.list_tools()}
        assert names == {"a", "c"}

    def test_unknown_allowed_name_is_skipped(self) -> None:
        source = _registry_with("a")
        child = _filter_registry(
            source, allowed_tools=["a", "ghost"], denied_tools=None
        )
        names = {t.name for t in child.list_tools()}
        assert names == {"a"}


# ---------------------------------------------------------------------------
# fork_subagent (with stub QueryEngine)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestForkSubagent:
    async def test_happy_path_returns_flat_result(self) -> None:
        parent = _StubEngine(tools=_registry_with("a", "b"))
        result = await fork_subagent(parent, "do thing", max_turns=4)  # type: ignore[arg-type]
        assert result["success"] is True
        assert result["partial"] is False
        assert result["error"] is None
        assert "hello from child" in result["text"]
        assert parent.fork_calls, "fork() should have been invoked on the parent"

    async def test_allow_deny_reaches_fork_call(self) -> None:
        parent = _StubEngine(tools=_registry_with("a", "b", "c"))
        await fork_subagent(
            parent,  # type: ignore[arg-type]
            "scoped subtask",
            allowed_tools=["a", "b"],
            denied_tools=["b"],
        )
        assert len(parent.fork_calls) == 1
        child_tools: ToolRegistry = parent.fork_calls[0]["tools"]
        names = {t.name for t in child_tools.list_tools()}
        assert names == {"a"}

    async def test_max_turns_override_on_child(self) -> None:
        parent = _StubEngine(tools=_registry_with("a"))
        parent.config.max_turns = 20  # parent has a big budget

        # Capture the forked child via monkey-patch.
        captured: dict[str, _StubEngine] = {}
        original_fork = parent.fork

        def _capturing_fork(
            *,
            system_prompt: str | None = None,
            tools: ToolRegistry | None = None,
            prompt_variant: str | None = None,
            executor: Any = None,
        ) -> _StubEngine:
            child = original_fork(
                system_prompt=system_prompt,
                tools=tools,
                prompt_variant=prompt_variant,
                executor=executor,
            )
            captured["child"] = child
            return child

        parent.fork = _capturing_fork  # type: ignore[assignment]

        await fork_subagent(parent, "subtask", max_turns=3)  # type: ignore[arg-type]
        assert captured["child"].config.max_turns == 3

    async def test_non_completed_reason_marks_partial(self) -> None:
        parent = _StubEngine(
            tools=_registry_with("a"),
            script=[
                _StubSDKMessage(
                    type="result",
                    data={"reason": "max_turns", "error": "hit cap"},
                ),
            ],
        )
        result = await fork_subagent(parent, "subtask")  # type: ignore[arg-type]
        assert result["success"] is False
        assert result["partial"] is True
        assert result["error"] == "hit cap"

    async def test_stream_deltas_accumulate(self) -> None:
        parent = _StubEngine(
            tools=_registry_with("a"),
            script=[
                _StubSDKMessage(type="stream_delta", data={"content": "hel"}),
                _StubSDKMessage(type="stream_delta", data={"content": "lo"}),
                _StubSDKMessage(type="result", data={"reason": "completed"}),
            ],
        )
        result = await fork_subagent(parent, "stream it")  # type: ignore[arg-type]
        assert result["success"] is True
        assert result["text"] == "hello"

    async def test_tool_use_counts_as_step(self) -> None:
        parent = _StubEngine(
            tools=_registry_with("a"),
            script=[
                _StubSDKMessage(type="tool_use", data={"name": "a"}),
                _StubSDKMessage(type="tool_use", data={"name": "a"}),
                _StubSDKMessage(type="assistant", data={"content": "done"}),
                _StubSDKMessage(type="result", data={"reason": "completed"}),
            ],
        )
        result = await fork_subagent(parent, "multi-step")  # type: ignore[arg-type]
        assert result["steps_count"] == 2
        assert result["success"] is True

    async def test_parent_abort_cascades_to_child(self) -> None:
        """When ``inherit_abort`` is true, tripping the parent's abort
        event should fire ``child.abort()`` via the bridge task."""
        parent_abort = asyncio.Event()
        parent = _StubEngine(tools=_registry_with("a"), abort_event=parent_abort)

        captured: dict[str, _StubEngine] = {}
        original_fork = parent.fork

        # Stream that blocks until abort fires, then yields a terminal.
        async def _blocking_stream(
            self: _StubEngine, prompt: str,
        ) -> AsyncIterator[_StubSDKMessage]:
            await self.abort_event.wait()
            yield _StubSDKMessage(
                type="result", data={"reason": "aborted", "error": "cancelled"},
            )

        def _capturing_fork(
            *,
            system_prompt: str | None = None,
            tools: ToolRegistry | None = None,
            prompt_variant: str | None = None,
            executor: Any = None,
        ) -> _StubEngine:
            child = original_fork(
                system_prompt=system_prompt,
                tools=tools,
                prompt_variant=prompt_variant,
                executor=executor,
            )
            # Patch this specific child's submit_message so the fork
            # coroutine parks until abort_event is set.
            child.submit_message = _blocking_stream.__get__(child, _StubEngine)  # type: ignore[method-assign]
            captured["child"] = child
            return child

        parent.fork = _capturing_fork  # type: ignore[assignment]

        async def _trip() -> None:
            # Wait until the fork has had a chance to install the bridge.
            for _ in range(50):
                if "child" in captured:
                    break
                await asyncio.sleep(0.01)
            parent_abort.set()

        fork_task = asyncio.create_task(
            fork_subagent(parent, "slow", inherit_abort=True)  # type: ignore[arg-type]
        )
        trip_task = asyncio.create_task(_trip())
        result = await asyncio.wait_for(fork_task, timeout=2.0)
        await trip_task

        child = captured.get("child")
        assert child is not None
        assert child.abort_event.is_set()
        assert result["partial"] is True


# ---------------------------------------------------------------------------
# AgentTool
# ---------------------------------------------------------------------------


class TestAgentToolConstruction:
    def test_requires_at_least_one_parent(self) -> None:
        with pytest.raises(ValueError):
            AgentTool()

    def test_parameters_expose_controls(self) -> None:
        tool = AgentTool(parent_engine=_StubEngine(tools=_registry_with("a")))  # type: ignore[arg-type]
        params = tool.parameters
        required = set(params["required"])
        props = set(params["properties"].keys())
        assert required == {"prompt"}
        assert {"prompt", "max_turns", "allowed_tools", "denied_tools"}.issubset(props)
        assert "system_prompt" not in props

    def test_metadata_flags(self) -> None:
        tool = AgentTool(parent_engine=_StubEngine(tools=_registry_with("a")))  # type: ignore[arg-type]
        assert tool.is_concurrency_safe is False
        assert tool.interrupt_behavior == "cancel"
        assert tool.max_result_size_chars == 200_000
        assert tool.name == "agent"


@pytest.mark.asyncio
class TestAgentToolExecute:
    async def test_invokes_fork_subagent(self) -> None:
        parent = _StubEngine(tools=_registry_with("a", "b"))
        tool = AgentTool(parent_engine=parent)  # type: ignore[arg-type]
        ctx = ToolContext(user_id=None, session_id=None)
        result = await tool.execute(
            {"prompt": "hello", "max_turns": 2}, ctx
        )
        assert result["success"] is True
        assert "hello from child" in result["text"]

    async def test_empty_prompt_rejected(self) -> None:
        parent = _StubEngine(tools=_registry_with("a"))
        tool = AgentTool(parent_engine=parent)  # type: ignore[arg-type]
        ctx = ToolContext(user_id=None, session_id=None)
        with pytest.raises(ValueError):
            await tool.execute({"prompt": "   "}, ctx)

    async def test_passes_tool_filters_through(self) -> None:
        parent = _StubEngine(tools=_registry_with("a", "b", "c"))
        tool = AgentTool(parent_engine=parent)  # type: ignore[arg-type]
        ctx = ToolContext(user_id=None, session_id=None)
        await tool.execute(
            {
                "prompt": "subtask",
                "allowed_tools": ["a", "b"],
                "denied_tools": ["b"],
            },
            ctx,
        )
        assert parent.fork_calls, "fork() should have been invoked"
        child_tools: ToolRegistry = parent.fork_calls[0]["tools"]
        names = {t.name for t in child_tools.list_tools()}
        assert names == {"a"}

    async def test_agent_tool_denies_destructive_tools_by_default(self) -> None:
        parent = _StubEngine(tools=_registry_with("project_read", "project_write"))
        tool = AgentTool(parent_engine=parent)  # type: ignore[arg-type]
        ctx = ToolContext(user_id=None, session_id=None)

        await tool.execute({"prompt": "subtask"}, ctx)

        child_tools: ToolRegistry = parent.fork_calls[0]["tools"]
        names = {t.name for t in child_tools.list_tools()}
        assert names == {"project_read"}
