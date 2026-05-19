"""Tests for multi-task agent session registry and cancellation."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from leagent.agent.controller import AgentController


@pytest.fixture(autouse=True)
def clear_agent_task_registry() -> None:
    AgentController._session_tasks.clear()
    AgentController._session_task_records.clear()
    yield
    AgentController._session_tasks.clear()
    AgentController._session_task_records.clear()


def test_cancel_session_signals_all_parallel_tasks() -> None:
    sid = uuid4()
    tid_a = uuid4()
    tid_b = uuid4()
    ev_a = asyncio.Event()
    ev_b = asyncio.Event()

    AgentController._register_session_task(sid, tid_a, ev_a, None)
    AgentController._register_session_task(sid, tid_b, ev_b, None)

    assert AgentController.is_session_active(sid)
    assert len(AgentController.list_agent_tasks_for_session(sid)) == 2

    ok = AgentController.cancel_session(sid)
    assert ok is True
    assert ev_a.is_set() and ev_b.is_set()
    assert not AgentController.is_session_active(sid)
    assert AgentController.list_agent_tasks_for_session(sid) == []


def test_cancel_task_removes_one_slot() -> None:
    sid = uuid4()
    tid_a = uuid4()
    tid_b = uuid4()
    ev_a = asyncio.Event()
    ev_b = asyncio.Event()

    AgentController._register_session_task(sid, tid_a, ev_a, None)
    AgentController._register_session_task(sid, tid_b, ev_b, None)

    assert AgentController.cancel_task(sid, tid_a) is True
    assert ev_a.is_set()
    assert not ev_b.is_set()
    assert AgentController.is_session_active(sid)
    assert len(AgentController.list_agent_tasks_for_session(sid)) == 1

    assert AgentController.cancel_session(sid) is True
    assert ev_b.is_set()


def test_cancel_session_returns_false_when_idle() -> None:
    assert AgentController.cancel_session(uuid4()) is False
