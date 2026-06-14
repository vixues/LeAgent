"""Tests for unified execution-plane run correlation."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.runtime.execution_factory import (
    begin_execution,
    end_execution,
    end_execution_unless_blocked,
)
from leagent.runtime.execution_registry import get_execution_run_registry
from leagent.runtime.execution_run import ExecutionScope


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use a fresh in-process registry for each test."""
    import leagent.runtime.execution_registry as reg_mod

    monkeypatch.setattr(reg_mod, "_registry", None)


def test_begin_execution_registers_run() -> None:
    run = begin_execution(
        scope=ExecutionScope.CHAT_TURN,
        session_id="sess-1",
        user_id="user-1",
    )
    registry = get_execution_run_registry()
    assert registry.get(run.run_id) is run
    assert run.scope == ExecutionScope.CHAT_TURN
    assert run.session_id == "sess-1"
    assert run.user_id == "user-1"


def test_end_execution_removes_run() -> None:
    run = begin_execution(scope=ExecutionScope.TASK, task_id="task-abc")
    registry = get_execution_run_registry()
    assert registry.get(run.run_id) is not None

    end_execution(run.run_id)
    assert registry.get(run.run_id) is None


def test_get_by_prompt_id() -> None:
    prompt_id = f"prompt-{uuid4().hex[:12]}"
    run = begin_execution(
        scope=ExecutionScope.WORKFLOW,
        session_id="sess-ws",
        prompt_id=prompt_id,
    )
    registry = get_execution_run_registry()
    found = registry.get_by_prompt_id(prompt_id)
    assert found is not None
    assert found.run_id == run.run_id
    assert registry.get_by_prompt_id("missing-prompt") is None


def test_parent_run_id_links_child_to_parent() -> None:
    parent = begin_execution(
        scope=ExecutionScope.CHAT_TURN,
        session_id="sess-parent",
    )
    child = begin_execution(
        scope=ExecutionScope.WORKFLOW,
        session_id="sess-parent",
        parent_run_id=parent.run_id,
        prompt_id=f"step-{uuid4().hex[:8]}",
    )
    registry = get_execution_run_registry()
    stored_child = registry.get(child.run_id)
    assert stored_child is not None
    assert stored_child.parent_run_id == parent.run_id

    session_runs = registry.list_for_session("sess-parent")
    run_ids = {r.run_id for r in session_runs}
    assert parent.run_id in run_ids
    assert child.run_id in run_ids


def test_end_execution_unless_blocked_retains_paused_run() -> None:
    run = begin_execution(
        scope=ExecutionScope.CHAT_TURN,
        session_id="sess-pause",
    )
    run.pause(reason="awaiting_user_input", checkpoint_id="cp-1")
    registry = get_execution_run_registry()

    removed = end_execution_unless_blocked(run.run_id)
    assert removed is False
    assert registry.get(run.run_id) is not None
    assert registry.get(run.run_id).pause_token is not None

    end_execution(run.run_id)
    assert registry.get(run.run_id) is None


def test_get_active_chat_turn_returns_most_recent() -> None:
    registry = get_execution_run_registry()
    older = begin_execution(scope=ExecutionScope.CHAT_TURN, session_id="sess-order")
    newer = begin_execution(scope=ExecutionScope.CHAT_TURN, session_id="sess-order")
    assert older.run_id != newer.run_id

    active = registry.get_active_chat_turn("sess-order")
    assert active is not None
    assert active.run_id == newer.run_id
