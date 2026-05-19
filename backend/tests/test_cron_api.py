"""Contract tests for ``/api/v1/cron`` with a fake :class:`CronManager`."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from leagent.cron.base import CronExecution, CronExecutionStatus, CronJob, CronJobStatus


class FakeCronManager:
    """Minimal stand-in for dependency-injected :class:`CronManager`."""

    def __init__(self) -> None:
        self._jobs: dict[UUID, CronJob] = {}
        self._started = True
        self.executor = MagicMock()
        self.executor.get_execution_history = MagicMock(return_value=[])

    async def get_health_status(self) -> dict[str, Any]:
        return {
            "running": self._started,
            "scheduler_running": True,
            "instance_id": "fake",
            "total_jobs": len(self._jobs),
            "active_jobs": sum(1 for j in self._jobs.values() if j.status == CronJobStatus.ACTIVE),
            "paused_jobs": sum(1 for j in self._jobs.values() if j.status == CronJobStatus.PAUSED),
            "failed_jobs": sum(1 for j in self._jobs.values() if j.status == CronJobStatus.FAILED),
            "running_executions": 0,
            "next_runs": [],
        }

    def get_running_executions(self) -> list[Any]:
        return []

    def get_next_run_times(self, limit: int = 10) -> list[tuple[CronJob, Any]]:
        upcoming: list[tuple[CronJob, Any]] = []
        for job in self._jobs.values():
            if job.next_run_at and job.enabled:
                upcoming.append((job, job.next_run_at))
        upcoming.sort(key=lambda x: x[1])
        return upcoming[:limit]

    def list_jobs(
        self,
        status: CronJobStatus | None = None,
        enabled: bool | None = None,
        user_id: UUID | str | None = None,
    ) -> list[CronJob]:
        jobs = list(self._jobs.values())
        if user_id is not None:
            uid_str = str(user_id)
            jobs = [j for j in jobs if j.user_id == uid_str]
        if status is not None:
            jobs = [j for j in jobs if j.status == status]
        if enabled is not None:
            jobs = [j for j in jobs if j.enabled == enabled]
        return sorted(jobs, key=lambda j: j.name)

    def get_job(self, job_id: UUID) -> CronJob | None:
        return self._jobs.get(job_id)

    async def add_job(self, job: CronJob) -> CronJob:
        self._jobs[job.id] = job
        return job

    async def remove_job(self, job_id: UUID) -> bool:
        return self._jobs.pop(job_id, None) is not None

    async def pause_job(self, job_id: UUID) -> CronJob | None:
        j = self._jobs.get(job_id)
        if j is None:
            return None
        j.status = CronJobStatus.PAUSED
        j.enabled = False
        return j

    async def resume_job(self, job_id: UUID) -> CronJob | None:
        j = self._jobs.get(job_id)
        if j is None:
            return None
        j.status = CronJobStatus.ACTIVE
        j.enabled = True
        return j

    async def trigger_job(self, job_id: UUID) -> CronExecution | None:
        j = self._jobs.get(job_id)
        if j is None:
            return None
        ex = CronExecution(job_id=j.id, job_name=j.name)
        ex.status = CronExecutionStatus.RUNNING
        return ex


@pytest.fixture
def fake_cron() -> FakeCronManager:
    return FakeCronManager()


def _override_cron(app: Any, fake: FakeCronManager) -> None:
    from leagent.api.v1.cron import get_cron_manager

    app.dependency_overrides[get_cron_manager] = lambda: fake


def _clear_overrides(app: Any) -> None:
    from leagent.api.v1.cron import get_cron_manager

    app.dependency_overrides.pop(get_cron_manager, None)


class TestCronAPIWithFakeManager:
    def test_create_flow_job_and_get_detail(
        self, client: TestClient, app: Any, fake_cron: FakeCronManager
    ) -> None:
        _override_cron(app, fake_cron)
        try:
            flow_id = str(uuid4())
            resp = client.post(
                "/api/v1/cron",
                json={
                    "name": "hourly-flow",
                    "job_type": "flow",
                    "cron_expression": "0 * * * *",
                    "target_id": flow_id,
                    "enabled": True,
                },
            )
            assert resp.status_code == 201, resp.text
            body = resp.json()
            assert body["name"] == "hourly-flow"
            assert body["job_type"] == "flow"
            assert body["cron_expression"] == "0 * * * *"
            job_id = body["id"]

            detail = client.get(f"/api/v1/cron/{job_id}")
            assert detail.status_code == 200, detail.text
            djson = detail.json()
            assert djson["target_id"] == flow_id
        finally:
            _clear_overrides(app)

    def test_list_jobs_after_create(
        self, client: TestClient, app: Any, fake_cron: FakeCronManager
    ) -> None:
        _override_cron(app, fake_cron)
        try:
            flow_id = str(uuid4())
            c = client.post(
                "/api/v1/cron",
                json={
                    "name": "listed-job",
                    "job_type": "flow",
                    "cron_expression": "0 0 * * *",
                    "target_id": flow_id,
                },
            )
            assert c.status_code == 201
            listed = client.get("/api/v1/cron")
            assert listed.status_code == 200
            data = listed.json()
            assert data["total"] >= 1
            names = {j["name"] for j in data["jobs"]}
            assert "listed-job" in names
        finally:
            _clear_overrides(app)

    def test_stats_and_health_use_fake(
        self, client: TestClient, app: Any, fake_cron: FakeCronManager
    ) -> None:
        _override_cron(app, fake_cron)
        try:
            h = client.get("/api/v1/cron/health")
            assert h.status_code == 200
            assert h.json().get("running") is True

            s = client.get("/api/v1/cron/stats")
            assert s.status_code == 200
            sj = s.json()
            assert "scheduler_running" in sj
            assert "total_jobs" in sj
        finally:
            _clear_overrides(app)


class TestCronPreviewNextRuns:
    def test_preview_next_runs_ok(self, client: TestClient) -> None:
        resp = client.get(
            "/api/v1/cron/preview-next-runs",
            params={"cron_expression": "0 0 * * *", "count": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cron_expression"] == "0 0 * * *"
        assert len(data["next_runs"]) == 3
