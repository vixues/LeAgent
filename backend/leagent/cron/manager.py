"""Cron job manager with APScheduler integration.

This module provides the main CronManager class that orchestrates
job scheduling, execution, and lifecycle management using APScheduler.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable
from uuid import UUID

import structlog
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MISSED,
    JobEvent,
    JobExecutionEvent,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone as pytz_timezone

from .base import CronExecution, CronHeartbeat, CronJob, CronJobStatus, CronExecutionStatus

if TYPE_CHECKING:
    from .executor import CronExecutor
    from .hooks import CronHookManager
    from .repository import JobRepository

logger = structlog.get_logger(__name__)

DEFAULT_MISFIRE_GRACE_TIME = 300
HEARTBEAT_INTERVAL_SEC = 30
JOB_CHECK_INTERVAL_SEC = 60


class CronManager:
    """Manager for cron job scheduling and lifecycle.

    Handles job registration, scheduling via APScheduler,
    state tracking, and coordination with the executor.
    """

    def __init__(
        self,
        repository: JobRepository | None = None,
        executor: CronExecutor | None = None,
        hook_manager: CronHookManager | None = None,
        instance_id: str = "default",
        timezone: str = "UTC",
        *,
        redis_client: Any | None = None,
    ):
        """Initialize the cron manager.

        Args:
            repository: Repository for persisting job definitions.
            executor: Executor for running scheduled jobs.
            hook_manager: Manager for lifecycle hooks.
            instance_id: Unique identifier for this manager instance.
            timezone: Default timezone for scheduling.
            redis_client: Unused, kept for call-site compatibility.
        """
        self.repository = repository
        self.executor = executor
        self.hook_manager = hook_manager
        self.instance_id = instance_id
        self.timezone = pytz_timezone(timezone)

        self._scheduler: AsyncIOScheduler | None = None
        self._jobs: dict[UUID, CronJob] = {}
        self._running_executions: dict[UUID, CronExecution] = {}
        self._lock = asyncio.Lock()
        self._started = False
        self._heartbeat_task: asyncio.Task[None] | None = None

        self._job_callbacks: dict[str, list[Callable[..., Any]]] = {
            "executed": [],
            "error": [],
            "missed": [],
        }

    async def start(self) -> None:
        """Start the cron manager and scheduler."""
        async with self._lock:
            if self._started:
                logger.warning("cron_manager_already_started", instance_id=self.instance_id)
                return

            self._scheduler = AsyncIOScheduler(timezone=self.timezone)
            self._scheduler.add_listener(self._on_job_executed, EVENT_JOB_EXECUTED)
            self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
            self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)

            if self.repository:
                await self._load_jobs_from_repository()

            self._scheduler.start()
            self._started = True

            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_loop(),
                name="cron_heartbeat",
            )

            logger.info(
                "cron_manager_started",
                instance_id=self.instance_id,
                job_count=len(self._jobs),
            )

    async def stop(self, wait: bool = True) -> None:
        """Stop the cron manager and scheduler.

        Args:
            wait: Whether to wait for running jobs to complete.
        """
        if not self._started:
            return

        async with self._lock:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

            if self._scheduler:
                self._scheduler.shutdown(wait=wait)
                self._scheduler = None

            self._started = False

            logger.info(
                "cron_manager_stopped",
                instance_id=self.instance_id,
                running_jobs=len(self._running_executions),
            )

    async def add_job(self, job: CronJob) -> CronJob:
        """Add a new cron job to the scheduler.

        Args:
            job: The job to add.

        Returns:
            The added job with updated next_run_at.

        Raises:
            ValueError: If job with same ID already exists.
        """
        async with self._lock:
            if job.id in self._jobs:
                raise ValueError(f"Job with ID {job.id} already exists")

            self._jobs[job.id] = job

            if job.enabled and job.status == CronJobStatus.ACTIVE:
                self._schedule_job(job)

            if self.repository:
                await self.repository.save(job)

            logger.info(
                "cron_job_added",
                job_id=str(job.id),
                name=job.name,
                schedule=job.schedule,
            )

            return job

    async def remove_job(self, job_id: UUID) -> bool:
        """Remove a job from the scheduler.

        Args:
            job_id: ID of the job to remove.

        Returns:
            True if job was removed, False if not found.
        """
        async with self._lock:
            job = self._jobs.pop(job_id, None)
            if not job:
                return False

            self._unschedule_job(job_id)

            if self.repository:
                await self.repository.delete(job_id)

            logger.info("cron_job_removed", job_id=str(job_id), name=job.name)
            return True

    async def update_job(self, job_id: UUID, updates: dict[str, Any]) -> CronJob | None:
        """Update a job's configuration.

        Args:
            job_id: ID of the job to update.
            updates: Dictionary of fields to update.

        Returns:
            Updated job or None if not found.
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            schedule_changed = "schedule" in updates and updates["schedule"] != job.schedule
            enabled_changed = "enabled" in updates and updates["enabled"] != job.enabled

            for key, value in updates.items():
                if hasattr(job, key):
                    setattr(job, key, value)

            job.updated_at = datetime.utcnow()
            job.version += 1

            if schedule_changed or enabled_changed:
                self._unschedule_job(job_id)
                if job.enabled and job.status == CronJobStatus.ACTIVE:
                    self._schedule_job(job)

            if self.repository:
                await self.repository.save(job)

            logger.info(
                "cron_job_updated",
                job_id=str(job_id),
                updates=list(updates.keys()),
            )

            return job

    async def pause_job(self, job_id: UUID) -> CronJob | None:
        """Pause a job, preventing future executions.

        Args:
            job_id: ID of the job to pause.

        Returns:
            Updated job or None if not found.
        """
        return await self.update_job(
            job_id,
            {
                "enabled": False,
                "status": CronJobStatus.PAUSED,
            },
        )

    async def resume_job(self, job_id: UUID) -> CronJob | None:
        """Resume a paused job.

        Args:
            job_id: ID of the job to resume.

        Returns:
            Updated job or None if not found.
        """
        job = self._jobs.get(job_id)
        if not job:
            return None

        return await self.update_job(
            job_id,
            {
                "enabled": True,
                "status": CronJobStatus.ACTIVE,
                "consecutive_failures": 0,
            },
        )

    async def trigger_job(self, job_id: UUID, payload: dict[str, Any] | None = None) -> CronExecution | None:
        """Manually trigger a job execution.

        Args:
            job_id: ID of the job to trigger.
            payload: Optional payload override.

        Returns:
            Execution record or None if job not found.
        """
        job = self._jobs.get(job_id)
        if not job:
            return None

        execution = CronExecution(
            job_id=job_id,
            job_name=job.name,
            execution_number=job.run_count + 1,
            trigger_type="manual",
            scheduled_at=datetime.utcnow(),
            inputs=payload or job.payload,
            max_retries=job.max_retries,
        )

        if self.executor:
            asyncio.create_task(
                self._execute_job(job, execution),
                name=f"manual_job_{job_id}",
            )

        return execution

    def get_job(self, job_id: UUID) -> CronJob | None:
        """Get a job by ID.

        Args:
            job_id: ID of the job.

        Returns:
            Job or None if not found.
        """
        return self._jobs.get(job_id)

    def list_jobs(
        self,
        status: CronJobStatus | None = None,
        enabled: bool | None = None,
        user_id: UUID | str | None = None,
    ) -> list[CronJob]:
        """List all jobs with optional filtering.

        Args:
            status: Filter by status.
            enabled: Filter by enabled state.
            user_id: Filter by owning user ID.

        Returns:
            List of matching jobs.
        """
        jobs = list(self._jobs.values())

        if user_id is not None:
            uid_str = str(user_id)
            jobs = [j for j in jobs if j.user_id == uid_str]

        if status is not None:
            jobs = [j for j in jobs if j.status == status]

        if enabled is not None:
            jobs = [j for j in jobs if j.enabled == enabled]

        return sorted(jobs, key=lambda j: j.name)

    async def pause_all(self, user_id: UUID | str | None = None) -> int:
        """Pause all active jobs, optionally filtered by user.

        Returns:
            Number of jobs paused.
        """
        jobs = self.list_jobs(status=CronJobStatus.ACTIVE, user_id=user_id)
        count = 0
        for job in jobs:
            result = await self.pause_job(job.id)
            if result:
                count += 1
        return count

    async def resume_all(self, user_id: UUID | str | None = None) -> int:
        """Resume all paused jobs, optionally filtered by user.

        Returns:
            Number of jobs resumed.
        """
        jobs = self.list_jobs(status=CronJobStatus.PAUSED, user_id=user_id)
        count = 0
        for job in jobs:
            result = await self.resume_job(job.id)
            if result:
                count += 1
        return count

    def get_running_executions(self) -> list[CronExecution]:
        """Get all currently running executions.

        Returns:
            List of running executions.
        """
        return list(self._running_executions.values())

    def get_next_run_times(self, limit: int = 10) -> list[tuple[CronJob, datetime]]:
        """Get upcoming scheduled run times.

        Args:
            limit: Maximum number of results.

        Returns:
            List of (job, next_run_time) tuples.
        """
        upcoming: list[tuple[CronJob, datetime]] = []

        for job in self._jobs.values():
            if job.next_run_at and job.enabled:
                upcoming.append((job, job.next_run_at))

        upcoming.sort(key=lambda x: x[1])
        return upcoming[:limit]

    async def get_health_status(self) -> dict[str, Any]:
        """Get health status of the cron manager.

        Returns:
            Health status dictionary.
        """
        active_jobs = sum(1 for j in self._jobs.values() if j.status == CronJobStatus.ACTIVE)
        paused_jobs = sum(1 for j in self._jobs.values() if j.status == CronJobStatus.PAUSED)
        failed_jobs = sum(1 for j in self._jobs.values() if j.status == CronJobStatus.FAILED)

        next_runs = self.get_next_run_times(5)

        return {
            "running": self._started,
            "instance_id": self.instance_id,
            "total_jobs": len(self._jobs),
            "active_jobs": active_jobs,
            "paused_jobs": paused_jobs,
            "failed_jobs": failed_jobs,
            "running_executions": len(self._running_executions),
            "scheduler_running": self._scheduler.running if self._scheduler else False,
            "next_runs": [
                {"job_id": str(j.id), "name": j.name, "next_run": t.isoformat()}
                for j, t in next_runs
            ],
        }

    def _schedule_job(self, job: CronJob) -> None:
        """Add job to APScheduler."""
        if not self._scheduler:
            return

        try:
            trigger = CronTrigger.from_crontab(
                job.schedule,
                timezone=pytz_timezone(job.timezone),
            )

            self._scheduler.add_job(
                self._job_wrapper,
                trigger=trigger,
                id=str(job.id),
                args=[job.id],
                coalesce=job.coalesce,
                max_instances=job.max_instances,
                misfire_grace_time=job.misfire_grace_sec or DEFAULT_MISFIRE_GRACE_TIME,
                replace_existing=True,
            )

            scheduled_job = self._scheduler.get_job(str(job.id))
            if scheduled_job and scheduled_job.next_run_time:
                job.next_run_at = scheduled_job.next_run_time.replace(tzinfo=None)

            logger.debug(
                "cron_job_scheduled",
                job_id=str(job.id),
                next_run=job.next_run_at.isoformat() if job.next_run_at else None,
            )

        except Exception as e:
            logger.error(
                "cron_job_schedule_failed",
                job_id=str(job.id),
                error=str(e),
                exc_info=True,
            )

    def _unschedule_job(self, job_id: UUID) -> None:
        """Remove job from APScheduler."""
        if not self._scheduler:
            return

        try:
            self._scheduler.remove_job(str(job_id))
            logger.debug("cron_job_unscheduled", job_id=str(job_id))
        except Exception:
            pass

    async def _job_wrapper(self, job_id: UUID) -> None:
        """Wrapper for scheduled job execution."""
        job = self._jobs.get(job_id)
        if not job:
            logger.warning("cron_job_not_found", job_id=str(job_id))
            return

        if not job.should_run():
            logger.debug(
                "cron_job_skip",
                job_id=str(job_id),
                status=job.status.value,
                enabled=job.enabled,
            )
            return

        if job.max_instances == 1 and job_id in self._running_executions:
            logger.debug(
                "cron_job_skip_running",
                job_id=str(job_id),
            )
            return

        execution = CronExecution(
            job_id=job_id,
            job_name=job.name,
            execution_number=job.run_count + 1,
            trigger_type="scheduled",
            scheduled_at=datetime.utcnow(),
            inputs=job.payload,
            max_retries=job.max_retries,
        )

        await self._execute_job(job, execution)

    async def _execute_job(self, job: CronJob, execution: CronExecution) -> None:
        """Execute a job with the executor."""
        self._running_executions[execution.id] = execution
        job.status = CronJobStatus.RUNNING

        try:
            if self.hook_manager:
                await self.hook_manager.on_job_start(job, execution)

            if self.executor:
                await self.executor.execute(job, execution)
            else:
                execution.complete({})

            job.record_success()

            if self.hook_manager:
                await self.hook_manager.on_job_complete(job, execution)

            logger.info(
                "cron_job_executed",
                job_id=str(job.id),
                execution_id=str(execution.id),
                duration_ms=execution.duration_ms,
            )

        except Exception as e:
            error_msg = str(e)
            job.record_failure(error_msg)
            execution.fail(error_msg, type(e).__name__)

            if self.hook_manager:
                await self.hook_manager.on_job_fail(job, execution, e)

            logger.error(
                "cron_job_failed",
                job_id=str(job.id),
                execution_id=str(execution.id),
                error=error_msg,
                exc_info=True,
            )

        finally:
            self._running_executions.pop(execution.id, None)
            job.status = CronJobStatus.ACTIVE if job.enabled else CronJobStatus.PAUSED

            if job.consecutive_failures > job.max_retries:
                job.status = CronJobStatus.FAILED

            if self._scheduler:
                scheduled_job = self._scheduler.get_job(str(job.id))
                if scheduled_job and scheduled_job.next_run_time:
                    job.next_run_at = scheduled_job.next_run_time.replace(tzinfo=None)

            if self.repository:
                await self.repository.save(job)

    def _on_job_executed(self, event: JobExecutionEvent) -> None:
        """Handle APScheduler job executed event."""
        for callback in self._job_callbacks["executed"]:
            try:
                callback(event)
            except Exception as e:
                logger.error("callback_error", event="executed", error=str(e))

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """Handle APScheduler job error event."""
        logger.error(
            "apscheduler_job_error",
            job_id=event.job_id,
            exception=str(event.exception) if event.exception else None,
        )

        for callback in self._job_callbacks["error"]:
            try:
                callback(event)
            except Exception as e:
                logger.error("callback_error", event="error", error=str(e))

    def _on_job_missed(self, event: JobEvent) -> None:
        """Handle APScheduler job missed event."""
        logger.warning("apscheduler_job_missed", job_id=event.job_id)

        for callback in self._job_callbacks["missed"]:
            try:
                callback(event)
            except Exception as e:
                logger.error("callback_error", event="missed", error=str(e))

    def add_listener(self, event_type: str, callback: Callable[..., Any]) -> None:
        """Add a listener for scheduler events.

        Args:
            event_type: Type of event ('executed', 'error', 'missed').
            callback: Callback function.
        """
        if event_type in self._job_callbacks:
            self._job_callbacks[event_type].append(callback)

    async def _load_jobs_from_repository(self) -> None:
        """Load jobs from repository on startup."""
        if not self.repository:
            return

        try:
            jobs = await self.repository.load_all()

            for job in jobs:
                self._jobs[job.id] = job
                if job.enabled and job.status == CronJobStatus.ACTIVE:
                    self._schedule_job(job)

            logger.info("cron_jobs_loaded", count=len(jobs))

        except Exception as e:
            logger.error("cron_jobs_load_failed", error=str(e), exc_info=True)

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat for health monitoring."""
        while self._started:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
                await self._send_heartbeat()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))

    async def _send_heartbeat(self) -> None:
        """Send heartbeat to repository."""
        heartbeat = CronHeartbeat(
            instance_id=self.instance_id,
            active_jobs=sum(1 for j in self._jobs.values() if j.enabled),
            running_jobs=len(self._running_executions),
            scheduler_running=self._scheduler.running if self._scheduler else False,
        )

        next_runs = self.get_next_run_times(1)
        if next_runs:
            heartbeat.next_execution_at = next_runs[0][1]

        if self.repository:
            await self.repository.save_heartbeat(heartbeat)
