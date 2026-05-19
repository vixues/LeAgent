"""Tests for cron system: CronJob base models, scheduler utilities, repository, manager."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from leagent.cron.base import (
    CronExecution,
    CronExecutionStatus,
    CronJob,
    CronJobStatus,
    CronJobType,
)


# ===========================================================================
# CronJob base model
# ===========================================================================


class TestCronJob:
    def _job(self, schedule: str = "0 * * * *") -> CronJob:
        return CronJob(
            name="hourly_report",
            schedule=schedule,
            target_type=CronJobType.WORKFLOW,
            target_id="wf-001",
        )

    def test_creation_defaults(self) -> None:
        job = self._job()
        assert job.name == "hourly_report"
        assert job.status == CronJobStatus.ACTIVE
        assert job.enabled is True
        assert job.run_count == 0

    def test_should_run_when_active(self) -> None:
        job = self._job()
        assert job.should_run() is True

    def test_should_not_run_when_disabled(self) -> None:
        job = self._job()
        job.enabled = False
        assert job.should_run() is False

    def test_should_not_run_when_paused(self) -> None:
        job = self._job()
        job.status = CronJobStatus.PAUSED
        assert job.should_run() is False

    def test_record_success(self) -> None:
        job = self._job()
        job.record_success()
        assert job.run_count == 1
        assert job.success_count == 1
        assert job.consecutive_failures == 0
        assert job.last_run_at is not None

    def test_record_failure_increments(self) -> None:
        job = self._job()
        job.record_failure("timeout error")
        assert job.run_count == 1
        assert job.error_count == 1
        assert job.consecutive_failures == 1
        assert job.last_error == "timeout error"

    def test_max_failures_disables_job(self) -> None:
        job = self._job()
        for _ in range(job.max_retries + 1):
            job.record_failure("repeated error")
        assert job.status == CronJobStatus.FAILED

    def test_invalid_schedule_raises(self) -> None:
        with pytest.raises(ValueError):
            CronJob(name="bad_job", schedule="invalid schedule here!!!")

    def test_valid_cron_expressions(self) -> None:
        valid_schedules = [
            "* * * * *",       # every minute
            "0 * * * *",       # every hour
            "0 9 * * 1-5",     # weekdays at 9am
            "30 8 1 * *",      # 1st of each month at 8:30
        ]
        for schedule in valid_schedules:
            job = CronJob(name="test", schedule=schedule)
            assert job.schedule == schedule

    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        job = self._job()
        job.record_success()
        d = job.to_dict()
        restored = CronJob.from_dict(d)
        assert restored.name == job.name
        assert restored.run_count == job.run_count

    def test_payload_stored(self) -> None:
        job = CronJob(
            name="webhook_trigger",
            schedule="*/5 * * * *",
            target_type=CronJobType.WEBHOOK,
            payload={"url": "https://example.com/hook", "method": "POST"},
        )
        assert job.payload["url"] == "https://example.com/hook"


# ===========================================================================
# CronExecution
# ===========================================================================


class TestCronExecution:
    def test_creation(self) -> None:
        job_id = uuid4()
        execution = CronExecution(job_id=job_id, job_name="hourly_report")
        assert execution.status == CronExecutionStatus.PENDING
        assert execution.job_id == job_id

    def test_status_transitions(self) -> None:
        execution = CronExecution(job_id=uuid4())
        execution.status = CronExecutionStatus.RUNNING
        assert execution.status == CronExecutionStatus.RUNNING
        execution.status = CronExecutionStatus.COMPLETED
        assert execution.status == CronExecutionStatus.COMPLETED


# ===========================================================================
# CronScheduler
# ===========================================================================


class TestCronScheduler:
    def test_get_next_run(self) -> None:
        from leagent.cron.scheduler import CronScheduler
        scheduler = CronScheduler()
        now = datetime(2024, 1, 15, 10, 0, 0)
        next_runs = scheduler.get_next_run("0 * * * *", after=now)
        assert isinstance(next_runs, list)
        assert len(next_runs) >= 1
        assert next_runs[0] > now

    def test_get_next_run_every_minute(self) -> None:
        from leagent.cron.scheduler import CronScheduler
        scheduler = CronScheduler()
        now = datetime(2024, 1, 15, 10, 30, 0)
        next_runs = scheduler.get_next_run("* * * * *", after=now)
        assert next_runs[0] > now
        diff_seconds = (next_runs[0] - now).total_seconds()
        assert diff_seconds <= 60

    def test_resolve_alias(self) -> None:
        from leagent.cron.scheduler import CRON_ALIASES
        resolved = CRON_ALIASES.get("@hourly")
        assert resolved == "0 * * * *"

    def test_resolve_non_alias(self) -> None:
        from leagent.cron.scheduler import CRON_ALIASES
        expr = "30 8 * * *"
        resolved = CRON_ALIASES.get(expr, expr)
        assert resolved == expr

    def test_is_valid_expression(self) -> None:
        from leagent.cron.scheduler import CronExpressionParser
        assert CronExpressionParser.validate("* * * * *")[0] is True
        assert CronExpressionParser.validate("0 9 * * 1-5")[0] is True
        assert CronExpressionParser.validate("not valid!!")[0] is False


# ===========================================================================
# JSON CronRepository
# ===========================================================================


@pytest.mark.asyncio
class TestCronRepository:
    async def test_create_and_get(self, tmp_path: Path) -> None:
        from leagent.cron.repository import JsonJobRepository
        repo = JsonJobRepository(str(tmp_path / "cron_jobs.json"))
        await repo.initialize()
        job = CronJob(name="test_job", schedule="0 * * * *")
        await repo.save(job)
        retrieved = await repo.get(job.id)
        assert retrieved is not None
        assert retrieved.name == "test_job"

    async def test_list_all(self, tmp_path: Path) -> None:
        from leagent.cron.repository import JsonJobRepository
        repo = JsonJobRepository(str(tmp_path / "cron_jobs.json"))
        await repo.initialize()
        for i in range(3):
            await repo.save(CronJob(name=f"job_{i}", schedule="0 * * * *"))
        jobs = await repo.load_all()
        assert len(jobs) == 3

    async def test_delete(self, tmp_path: Path) -> None:
        from leagent.cron.repository import JsonJobRepository
        repo = JsonJobRepository(str(tmp_path / "cron_jobs.json"))
        await repo.initialize()
        job = CronJob(name="delete_me", schedule="0 * * * *")
        await repo.save(job)
        await repo.delete(job.id)
        assert await repo.get(job.id) is None

    async def test_persistence_across_instances(self, tmp_path: Path) -> None:
        from leagent.cron.repository import JsonJobRepository
        path = str(tmp_path / "cron_jobs.json")
        repo1 = JsonJobRepository(path)
        await repo1.initialize()
        job = CronJob(name="persistent_job", schedule="30 * * * *")
        await repo1.save(job)

        repo2 = JsonJobRepository(path)
        await repo2.initialize()
        retrieved = await repo2.get(job.id)
        assert retrieved is not None
        assert retrieved.name == "persistent_job"
