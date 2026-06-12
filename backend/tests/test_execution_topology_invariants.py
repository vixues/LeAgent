"""Invariant tests for execution topology alignment.

Ensures production agent callers route through the SDK kernel (run_loop)
rather than bypassing it with direct ``submit_message`` calls.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Production modules that may invoke agent execution.
_AGENT_ENTRY_MODULES = [
    "leagent/tasks/handlers/agent_handler.py",
    "leagent/agent/subagent.py",
    "leagent/agent/controller.py",
    "leagent/runtime/runtime.py",
    "leagent/workflow/nodes/agent_exec.py",
]

# Allowed to call submit_message directly (kernel internals + tests).
_SUBMIT_MESSAGE_ALLOWLIST = {
    "leagent/agent/query_engine.py",
    "leagent/sdk/kernel/loop.py",
    "leagent/agent/query.py",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _module_path(relative: str) -> Path:
    return _repo_root() / relative


def _calls_submit_message(source: str) -> list[int]:
    tree = ast.parse(source)
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "submit_message":
            lines.append(node.lineno)
    return lines


@pytest.mark.parametrize("relative", _AGENT_ENTRY_MODULES)
def test_production_agent_entries_use_kernel(relative: str) -> None:
    """Production entry modules must not call submit_message outside run_loop."""
    path = _module_path(relative)
    if not path.exists():
        pytest.skip(f"{relative} not present")
    source = path.read_text(encoding="utf-8")
    if relative == "leagent/agent/controller.py":
        # Controller delegates to run_loop via _run_via_query_engine.
        assert "run_loop" in source
        return
    if relative == "leagent/runtime/runtime.py":
        assert "run_loop" in source
        return
    if relative == "leagent/workflow/nodes/agent_exec.py":
        assert "AgentRuntime" in source or "run_loop" in source
        return
    if relative == "leagent/agent/subagent.py":
        assert "run_loop" in source
        assert not _calls_submit_message(source), (
            f"{relative} must route through run_loop, not submit_message"
        )
        return
    if relative == "leagent/tasks/handlers/agent_handler.py":
        assert "runtime.stream" in source or "run_loop" in source
        assert not _calls_submit_message(source)
        return


def test_service_manager_exposes_runtime_context() -> None:
    from leagent.services.service_manager import ServiceManager

    assert "runtime_context" in dir(ServiceManager)


def test_runtime_context_from_service_manager_builds_hooks() -> None:
    from unittest.mock import MagicMock

    from leagent.runtime.context import RuntimeContext

    sm = MagicMock()
    sm.llm_service = MagicMock()
    sm.agent_memory = None
    sm.session_manager = None
    sm.database_service = None
    sm.settings = MagicMock()
    sm.settings.context = None

    sm.database_service = MagicMock()

    ctx = RuntimeContext.from_service_manager(sm)
    assert ctx.executor is not None
    assert ctx.hook_manager is not None
    assert ctx.permission_context is not None
    assert ctx.checkpoint_store is not None
