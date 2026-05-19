"""Tests for :class:`CronExecutor` script hardening and task dispatch.

The script path must reject shell strings unless explicitly opted in,
and the task dispatch path should route through :class:`TaskManager`
instead of the old stub.
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
import tempfile
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leagent.cron.base import (
    CronExecution,
    CronJob,
    CronJobType,
)
from leagent.cron.executor import CronExecutor


# ---------------------------------------------------------------------------
# Cron workflow target (WorkflowExecutor + registry)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_workflow_loads_definition_and_returns_outputs() -> None:
    """CronExecutor._execute_workflow delegates to WorkflowExecutor.execute."""
    from uuid import uuid4

    from leagent.workflow.base import WorkflowResult, WorkflowStatus
    from leagent.workflow.io import load

    minimal = {
        "id": "cron-mini",
        "name": "cron-mini",
        "inputs": [],
        "outputs": [],
        "metadata": {},
        "nodes": {
            "start": {
                "class_type": "StartNode",
                "inputs": {},
                "meta": {},
                "control": {"next": "end"},
            },
            "end": {
                "class_type": "EndNode",
                "inputs": {},
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
    doc = load(minimal)
    wf_id = str(uuid4())

    wf_ex = AsyncMock()
    wf_ex.execute = AsyncMock(
        return_value=WorkflowResult(
            workflow_id="cron-mini",
            state_id=uuid4(),
            status=WorkflowStatus.COMPLETED,
            outputs={"ok": True},
            errors=[],
            execution_history=[],
            duration_ms=1,
        )
    )

    registry = AsyncMock()
    registry.get = AsyncMock(return_value=doc)

    executor = CronExecutor(workflow_executor=wf_ex, workflow_registry=registry)
    job = CronJob(
        name="wf-job",
        schedule="* * * * *",
        target_type=CronJobType.WORKFLOW,
        workflow_id=wf_id,
        payload={"extra": 1},
    )
    execution = CronExecution(job_id=job.id, scheduled_at=None)

    out = await executor._execute_workflow(job, execution)

    assert out == {"ok": True}
    registry.get.assert_awaited_once_with(wf_id)
    wf_ex.execute.assert_awaited_once()
    call_kw = wf_ex.execute.await_args
    assert call_kw.args[0] is doc
    assert call_kw.args[1] == {"extra": 1}


# ---------------------------------------------------------------------------
# _execute_script hardening
# ---------------------------------------------------------------------------


def _make_job(payload: dict[str, Any], target: CronJobType = CronJobType.SCRIPT) -> CronJob:
    return CronJob(
        name="unit",
        schedule="* * * * *",
        target_type=target,
        payload=payload,
    )


def _make_execution(job: CronJob) -> CronExecution:
    return CronExecution(job_id=job.id, scheduled_at=None)


@pytest.mark.asyncio
async def test_script_without_path_rejected_when_shell_disallowed() -> None:
    """With ``cron_allow_shell=False`` a bare ``script`` string must 400."""
    executor = CronExecutor()

    with patch(
        "leagent.config.settings.get_settings",
        return_value=MagicMock(cron_allow_shell=False),
    ):
        job = _make_job({"script": "echo hi"})
        with pytest.raises(ValueError, match="script_path"):
            await executor._execute_script(job, _make_execution(job))


@pytest.mark.asyncio
async def test_script_with_args_runs_via_exec() -> None:
    """The safe path: ``script_path`` + ``args`` runs via ``create_subprocess_exec``."""
    executor = CronExecutor()
    job = _make_job({"script_path": sys.executable, "args": ["-c", "print('hi')"]})

    result = await executor._execute_script(job, _make_execution(job))

    assert result["exit_code"] == 0
    assert "hi" in result["stdout"]


@pytest.mark.asyncio
async def test_script_with_shell_string_needs_opt_in() -> None:
    """``script`` string works only when settings allow it."""
    executor = CronExecutor()
    job = _make_job({"script": "echo cron-allowed"})

    with patch(
        "leagent.config.settings.get_settings",
        return_value=MagicMock(cron_allow_shell=True),
    ):
        result = await executor._execute_script(job, _make_execution(job))

    assert result["exit_code"] == 0
    assert "cron-allowed" in result["stdout"]


@pytest.mark.asyncio
async def test_script_args_must_be_list() -> None:
    executor = CronExecutor()
    job = _make_job({"script_path": "/bin/true", "args": "not-a-list"})
    with pytest.raises(ValueError, match="'args' must be a list"):
        await executor._execute_script(job, _make_execution(job))


# ---------------------------------------------------------------------------
# _execute_task dispatch
# ---------------------------------------------------------------------------


class _FakeTask:
    def __init__(self) -> None:
        from uuid import uuid4 as _uuid

        self.id = _uuid()
        self.status = None  # filled in by the fake DB below
        self.output_data = None
        self.error = None


class _FakeSession:
    """The bare minimum ``AsyncSession`` facade the executor relies on."""

    def __init__(self, task: _FakeTask) -> None:
        self._task = task

    async def get(self, _model, _pk):  # noqa: ANN001
        return self._task

    async def commit(self) -> None:
        return None


class _FakeDB:
    def __init__(self, task: _FakeTask) -> None:
        self._task = task

    def session(self):
        task = self._task

        class _Ctx:
            async def __aenter__(self_inner) -> _FakeSession:
                return _FakeSession(task)

            async def __aexit__(self_inner, exc_type, exc, tb) -> None:
                return None

        return _Ctx()


@pytest.mark.asyncio
async def test_execute_task_routes_through_task_manager() -> None:
    """Cron ``task`` jobs must invoke ``TaskManager.create_task + start_task``."""
    from leagent.services.database.models.task import TaskStatus

    fake_task = _FakeTask()
    fake_task.status = TaskStatus.COMPLETED
    fake_task.output_data = '{"ok": true}'

    mgr = MagicMock()
    mgr.create_task = AsyncMock(return_value=fake_task)
    mgr.start_task = AsyncMock(return_value=None)

    fake_db = _FakeDB(fake_task)

    job = CronJob(
        name="cron-task",
        schedule="* * * * *",
        target_type=CronJobType.TASK,
        payload={"task_type": "shell", "input_data": {"cmd": ["true"]}},
    )
    execution = _make_execution(job)

    executor = CronExecutor(default_timeout_sec=30)

    with patch(
        "leagent.services.task_manager.get_task_manager", return_value=mgr
    ), patch(
        "leagent.services.database.get_database_service", return_value=fake_db
    ):
        result = await executor._execute_task(job, execution)

    mgr.create_task.assert_awaited_once()
    create_kwargs = mgr.create_task.await_args.kwargs
    assert create_kwargs["task_type"].value == "shell"
    assert create_kwargs["input_data"] == {"cmd": ["true"]}

    mgr.start_task.assert_awaited_once()
    assert result["status"] == TaskStatus.COMPLETED.value
    assert result["task_id"] == str(fake_task.id)
    assert result["output"] == {"ok": True}
    # Back-reference is stored on the job payload so the UI can link to it.
    assert job.payload.get("last_task_id") == str(fake_task.id)


@pytest.mark.asyncio
async def test_execute_task_propagates_failure() -> None:
    from leagent.services.database.models.task import TaskStatus

    fake_task = _FakeTask()
    fake_task.status = TaskStatus.FAILED
    fake_task.error = "handler exploded"

    mgr = MagicMock()
    mgr.create_task = AsyncMock(return_value=fake_task)
    mgr.start_task = AsyncMock(return_value=None)

    fake_db = _FakeDB(fake_task)
    job = CronJob(
        name="cron-task",
        schedule="* * * * *",
        target_type=CronJobType.TASK,
        payload={"task_type": "agent"},
    )
    execution = _make_execution(job)

    executor = CronExecutor(default_timeout_sec=30)

    with patch(
        "leagent.services.task_manager.get_task_manager", return_value=mgr
    ), patch(
        "leagent.services.database.get_database_service", return_value=fake_db
    ):
        with pytest.raises(RuntimeError, match="failed"):
            await executor._execute_task(job, execution)
