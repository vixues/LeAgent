"""Scoped ToolExecutor for sub-agents matches filtered tool registry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
from leagent.agent.subagent import (
    _run_subagent_core,
    fork_scoped_engine,
    make_child_executor,
)
from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.executor import ToolExecutor
from leagent.tools.registry import ToolRegistry


class _DummyTool(BaseTool):
    name = "dummy_tool"
    description = "Test dummy tool for registry assertions."
    category = ToolCategory.UTIL

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, params: dict, context: ToolContext) -> dict:
        return {}


def test_make_child_executor_uses_child_registry() -> None:
    parent_reg = ToolRegistry()
    t = _DummyTool()
    parent_reg.register(t)

    child_reg = ToolRegistry()
    child_reg.register(t)

    parent_ex = ToolExecutor(registry=parent_reg)
    child_ex = make_child_executor(parent_ex, child_reg)

    assert child_ex.registry is child_reg
    assert child_ex.registry.get("dummy_tool") is t


def test_fork_scoped_engine_executor_matches_tools() -> None:
    reg = ToolRegistry()
    reg.register(_DummyTool())

    parent_ex = ToolExecutor(registry=reg)
    child_reg = ToolRegistry()
    child_reg.register(_DummyTool())

    engine = QueryEngine(
        QueryEngineConfig(
            llm=MagicMock(),
            tools=reg,
            executor=parent_ex,
        )
    )
    child = fork_scoped_engine(
        engine,
        child_registry=child_reg,
        prompt_variant="test_variant",
    )
    assert child.config.tools is child_reg
    assert child.config.executor is not None
    assert child.config.executor.registry is child_reg


def test_fork_scoped_engine_syncs_context_variant() -> None:
    reg = ToolRegistry()
    reg.register(_DummyTool())

    parent_ex = ToolExecutor(registry=reg)
    engine = QueryEngine(
        QueryEngineConfig(
            llm=MagicMock(),
            tools=reg,
            executor=parent_ex,
            prompt_variant="default_agent",
        )
    )
    child = fork_scoped_engine(
        engine,
        child_registry=reg,
        prompt_variant="coding_agent",
    )
    assert child.config.prompt_variant == "coding_agent"
    if hasattr(child, "_context") and hasattr(child._context, "variant"):
        assert child._context.variant == "coding_agent"


def test_coding_agent_tool_timeout_and_retries() -> None:
    from leagent.agent.coding_agent import CODING_AGENT_DEFAULT_PROFILE, CodingAgentTool
    from leagent.agent.runtime_profile import resolve_runtime_budget

    budget = resolve_runtime_budget(CODING_AGENT_DEFAULT_PROFILE)
    assert CodingAgentTool.timeout_sec == budget.task_timeout_sec
    assert CodingAgentTool.max_retries == 0


def test_import_tier_defaults_unrestricted() -> None:
    from leagent.config.settings import get_settings

    assert get_settings().code_execution_import_tier == "unrestricted"


@pytest.mark.asyncio
async def test_run_subagent_core_with_coding_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reg = ToolRegistry()
    reg.register(_DummyTool())
    parent_ex = ToolExecutor(registry=reg)
    parent = QueryEngine(
        QueryEngineConfig(
            llm=MagicMock(),
            tools=reg,
            executor=parent_ex,
            tool_extra={"authorized_roots": ["/tmp/allowed"]},
        )
    )
    captured: dict[str, object] = {}

    async def fake_run_engine(engine: QueryEngine, prompt: str) -> dict:
        captured["prompt"] = prompt
        captured["prompt_variant"] = engine.config.prompt_variant
        captured["cwd"] = engine.config.cwd
        captured["tool_extra"] = engine.config.tool_extra
        return {"text": "ok", "success": True, "steps_count": 0}

    monkeypatch.setattr(
        "leagent.agent.subagent._run_engine",
        fake_run_engine,
    )

    result = await _run_subagent_core(
        parent_controller=None,
        parent_engine=parent,
        prompt="implement feature",
        prompt_variant="coding_agent",
        allowed_tools=["dummy_tool"],
        max_turns=5,
        tool_extra={"project_roots": ["/tmp/project"]},
        cwd="/tmp/project",
    )

    assert result["success"] is True
    assert captured["prompt_variant"] == "coding_agent"
    assert captured["cwd"] == "/tmp/project"
    assert captured["tool_extra"] == {
        "project_roots": ["/tmp/project"],
        "authorized_roots": ["/tmp/allowed"],
    }


@pytest.mark.asyncio
async def test_run_subagent_core_with_script_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reg = ToolRegistry()
    reg.register(_DummyTool())
    parent = QueryEngine(
        QueryEngineConfig(
            llm=MagicMock(),
            tools=reg,
            executor=ToolExecutor(registry=reg),
        )
    )

    async def fake_run_engine(engine: QueryEngine, prompt: str) -> dict:
        return {
            "text": f"{engine.config.prompt_variant}:{prompt}",
            "success": True,
            "steps_count": 0,
        }

    monkeypatch.setattr(
        "leagent.agent.subagent._run_engine",
        fake_run_engine,
    )

    result = await _run_subagent_core(
        parent_controller=None,
        parent_engine=parent,
        prompt="calculate",
        prompt_variant="script_agent",
        allowed_tools=["dummy_tool"],
        max_turns=3,
    )

    assert result["text"] == "script_agent:calculate"
    assert result["success"] is True
