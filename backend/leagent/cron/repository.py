"""Job repositories for cron job persistence.

Provides JSON file-based and PostgreSQL-backed implementations.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

import structlog

from .base import CronExecution, CronHeartbeat, CronJob, CronExecutionStatus

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService

logger = structlog.get_logger(__name__)

CURRENT_SCHEMA_VERSION = 1


class JobRepository(Protocol):
    """Protocol for job repository implementations."""

    async def save(self, job: CronJob) -> None:
        """Save a job."""
        ...

    async def delete(self, job_id: UUID) -> bool:
        """Delete a job."""
        ...

    async def get(self, job_id: UUID) -> CronJob | None:
        """Get a job by ID."""
        ...

    async def load_all(self) -> list[CronJob]:
        """Load all jobs."""
        ...

    async def save_heartbeat(self, heartbeat: CronHeartbeat) -> None:
        """Save a heartbeat record."""
        ...


class JsonJobRepository:
    """JSON file-based job repository.

    Persists job definitions to a JSON file with support for
    atomic saves, backup rotation, and schema migrations.
    """

    def __init__(
        self,
        file_path: str | Path,
        backup_count: int = 5,
        auto_save_interval: float = 0.0,
    ):
        """Initialize the repository.

        Args:
            file_path: Path to the JSON file.
            backup_count: Number of backup files to keep.
            auto_save_interval: Interval for auto-save (0 to disable).
        """
        self.file_path = Path(file_path)
        self.backup_count = backup_count
        self.auto_save_interval = auto_save_interval

        self._jobs: dict[UUID, CronJob] = {}
        self._executions: dict[UUID, list[CronExecution]] = {}
        self._heartbeats: list[CronHeartbeat] = []
        self._lock = asyncio.Lock()
        self._dirty = False
        self._auto_save_task: asyncio.Task[None] | None = None
        self._schema_version = CURRENT_SCHEMA_VERSION

    async def initialize(self) -> None:
        """Initialize the repository, loading existing data."""
        async with self._lock:
            await self._ensure_directory()
            await self._load()

            if self.auto_save_interval > 0:
                self._auto_save_task = asyncio.create_task(
                    self._auto_save_loop(),
                    name="json_repo_auto_save",
                )

            logger.info(
                "json_repository_initialized",
                file_path=str(self.file_path),
                job_count=len(self._jobs),
            )

    async def close(self) -> None:
        """Close the repository, saving any pending changes."""
        if self._auto_save_task:
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass

        if self._dirty:
            await self._save()

    async def save(self, job: CronJob) -> None:
        """Save a job to the repository.

        Args:
            job: The job to save.
        """
        async with self._lock:
            self._jobs[job.id] = job
            self._dirty = True

            if self.auto_save_interval == 0:
                await self._save()

    async def delete(self, job_id: UUID) -> bool:
        """Delete a job from the repository.

        Args:
            job_id: ID of the job to delete.

        Returns:
            True if deleted, False if not found.
        """
        async with self._lock:
            if job_id not in self._jobs:
                return False

            del self._jobs[job_id]
            self._executions.pop(job_id, None)
            self._dirty = True

            if self.auto_save_interval == 0:
                await self._save()

            return True

    async def get(self, job_id: UUID) -> CronJob | None:
        """Get a job by ID.

        Args:
            job_id: ID of the job.

        Returns:
            Job or None if not found.
        """
        return self._jobs.get(job_id)

    async def load_all(self) -> list[CronJob]:
        """Load all jobs from the repository.

        Returns:
            List of all jobs.
        """
        return list(self._jobs.values())

    async def save_execution(self, execution: CronExecution) -> None:
        """Save an execution record.

        Args:
            execution: The execution to save.
        """
        async with self._lock:
            if execution.job_id not in self._executions:
                self._executions[execution.job_id] = []

            executions = self._executions[execution.job_id]

            existing_idx = next(
                (i for i, e in enumerate(executions) if e.id == execution.id),
                None,
            )

            if existing_idx is not None:
                executions[existing_idx] = execution
            else:
                executions.append(execution)
                if len(executions) > 1000:
                    self._executions[execution.job_id] = executions[-1000:]

            self._dirty = True

    async def get_executions(
        self,
        job_id: UUID,
        limit: int = 100,
        status: str | None = None,
    ) -> list[CronExecution]:
        """Get execution history for a job.

        Args:
            job_id: ID of the job.
            limit: Maximum records to return.
            status: Optional status filter.

        Returns:
            List of execution records.
        """
        executions = self._executions.get(job_id, [])

        if status:
            executions = [e for e in executions if e.status.value == status]

        return list(reversed(executions[-limit:]))

    async def save_heartbeat(self, heartbeat: CronHeartbeat) -> None:
        """Save a heartbeat record.

        Args:
            heartbeat: The heartbeat to save.
        """
        async with self._lock:
            self._heartbeats.append(heartbeat)

            if len(self._heartbeats) > 100:
                self._heartbeats = self._heartbeats[-100:]

            self._dirty = True

    async def get_latest_heartbeat(self, instance_id: str | None = None) -> CronHeartbeat | None:
        """Get the latest heartbeat.

        Args:
            instance_id: Optional instance filter.

        Returns:
            Latest heartbeat or None.
        """
        if not self._heartbeats:
            return None

        if instance_id:
            matching = [h for h in self._heartbeats if h.instance_id == instance_id]
            return matching[-1] if matching else None

        return self._heartbeats[-1]

    async def _ensure_directory(self) -> None:
        """Ensure the parent directory exists."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    async def _load(self) -> None:
        """Load data from the JSON file."""
        if not self.file_path.exists():
            logger.debug("json_repository_file_not_found", path=str(self.file_path))
            return

        try:
            data = await asyncio.to_thread(self._read_file)

            schema_version = data.get("schema_version", 1)
            if schema_version < CURRENT_SCHEMA_VERSION:
                data = self._migrate_schema(data, schema_version)

            for job_data in data.get("jobs", []):
                try:
                    job = CronJob.from_dict(job_data)
                    self._jobs[job.id] = job
                except Exception as e:
                    logger.warning(
                        "json_repository_job_parse_error",
                        error=str(e),
                        job_data=job_data.get("id"),
                    )

            for job_id_str, exec_list in data.get("executions", {}).items():
                try:
                    job_id = UUID(job_id_str)
                    self._executions[job_id] = [
                        CronExecution.from_dict(e) for e in exec_list
                    ]
                except Exception as e:
                    logger.warning(
                        "json_repository_execution_parse_error",
                        error=str(e),
                        job_id=job_id_str,
                    )

            logger.info(
                "json_repository_loaded",
                job_count=len(self._jobs),
                execution_count=sum(len(e) for e in self._executions.values()),
            )

        except json.JSONDecodeError as e:
            logger.error(
                "json_repository_parse_error",
                error=str(e),
                path=str(self.file_path),
            )
            await self._recover_from_backup()

        except Exception as e:
            logger.error(
                "json_repository_load_error",
                error=str(e),
                path=str(self.file_path),
                exc_info=True,
            )

    def _read_file(self) -> dict[str, Any]:
        """Read and parse the JSON file (blocking)."""
        with open(self.file_path, encoding="utf-8") as f:
            return json.load(f)

    async def _save(self) -> None:
        """Save data to the JSON file atomically."""
        try:
            data = {
                "schema_version": CURRENT_SCHEMA_VERSION,
                "saved_at": datetime.utcnow().isoformat(),
                "jobs": [job.to_dict() for job in self._jobs.values()],
                "executions": {
                    str(job_id): [e.to_dict() for e in executions]
                    for job_id, executions in self._executions.items()
                },
                "heartbeats": [h.model_dump(mode="json") for h in self._heartbeats[-10:]],
            }

            await asyncio.to_thread(self._write_file_atomic, data)
            self._dirty = False

            logger.debug(
                "json_repository_saved",
                job_count=len(self._jobs),
                path=str(self.file_path),
            )

        except Exception as e:
            logger.error(
                "json_repository_save_error",
                error=str(e),
                path=str(self.file_path),
                exc_info=True,
            )
            raise

    def _write_file_atomic(self, data: dict[str, Any]) -> None:
        """Write to file atomically (blocking).

        Uses a temp file and rename for atomicity.
        """
        if self.file_path.exists():
            self._rotate_backups()

        fd, temp_path = tempfile.mkstemp(
            dir=self.file_path.parent,
            prefix=".tmp_jobs_",
            suffix=".json",
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())

            shutil.move(temp_path, self.file_path)

        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def _rotate_backups(self) -> None:
        """Rotate backup files."""
        if not self.file_path.exists():
            return

        for i in range(self.backup_count - 1, 0, -1):
            old_backup = self.file_path.with_suffix(f".json.{i}")
            new_backup = self.file_path.with_suffix(f".json.{i + 1}")

            if old_backup.exists():
                if i == self.backup_count - 1:
                    old_backup.unlink()
                else:
                    shutil.move(old_backup, new_backup)

        backup_1 = self.file_path.with_suffix(".json.1")
        shutil.copy2(self.file_path, backup_1)

    async def _recover_from_backup(self) -> None:
        """Attempt to recover from backup files."""
        for i in range(1, self.backup_count + 1):
            backup_path = self.file_path.with_suffix(f".json.{i}")

            if backup_path.exists():
                logger.info(
                    "json_repository_recovering",
                    backup_path=str(backup_path),
                )

                try:
                    self.file_path = backup_path
                    await self._load()
                    self.file_path = backup_path.with_suffix("")
                    return

                except Exception as e:
                    logger.warning(
                        "json_repository_backup_recovery_failed",
                        error=str(e),
                        backup_path=str(backup_path),
                    )

        logger.error("json_repository_no_valid_backup_found")

    def _migrate_schema(self, data: dict[str, Any], from_version: int) -> dict[str, Any]:
        """Migrate data from older schema versions.

        Args:
            data: The data to migrate.
            from_version: The source schema version.

        Returns:
            Migrated data.
        """
        logger.info(
            "json_repository_migrating",
            from_version=from_version,
            to_version=CURRENT_SCHEMA_VERSION,
        )

        return data

    async def _auto_save_loop(self) -> None:
        """Periodic auto-save loop."""
        while True:
            try:
                await asyncio.sleep(self.auto_save_interval)

                if self._dirty:
                    async with self._lock:
                        await self._save()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("json_repository_auto_save_error", error=str(e))

    async def compact(self) -> None:
        """Compact the repository by removing old executions."""
        async with self._lock:
            total_removed = 0

            for job_id in list(self._executions.keys()):
                executions = self._executions[job_id]

                if len(executions) > 100:
                    removed = len(executions) - 100
                    self._executions[job_id] = executions[-100:]
                    total_removed += removed

            if total_removed > 0:
                self._dirty = True
                await self._save()

                logger.info(
                    "json_repository_compacted",
                    executions_removed=total_removed,
                )

    async def export_jobs(self) -> list[dict[str, Any]]:
        """Export all jobs as dictionaries.

        Returns:
            List of job dictionaries.
        """
        return [job.to_dict() for job in self._jobs.values()]

    async def import_jobs(
        self,
        jobs_data: list[dict[str, Any]],
        overwrite: bool = False,
    ) -> tuple[int, int]:
        """Import jobs from dictionaries.

        Args:
            jobs_data: List of job dictionaries.
            overwrite: Whether to overwrite existing jobs.

        Returns:
            Tuple of (imported_count, skipped_count).
        """
        imported = 0
        skipped = 0

        async with self._lock:
            for job_data in jobs_data:
                try:
                    job = CronJob.from_dict(job_data)

                    if job.id in self._jobs and not overwrite:
                        skipped += 1
                        continue

                    self._jobs[job.id] = job
                    imported += 1

                except Exception as e:
                    logger.warning(
                        "json_repository_import_error",
                        error=str(e),
                        job_data=job_data.get("id"),
                    )
                    skipped += 1

            if imported > 0:
                self._dirty = True
                await self._save()

        logger.info(
            "json_repository_import_complete",
            imported=imported,
            skipped=skipped,
        )

        return imported, skipped


class DatabaseJobRepository:
    """PostgreSQL-backed job repository using SQLModel.

    Persists cron job definitions and execution records to the
    application's relational database for durability and queryability.
    """

    def __init__(self, db: "DatabaseService") -> None:
        self._db = db

    async def initialize(self) -> None:
        logger.info("database_job_repository_ready")

    async def save(self, job: CronJob) -> None:
        """Upsert a cron job to the database."""
        from sqlmodel import select
        from leagent.db.models.cron import CronJobModel

        async with self._db.session() as session:
            existing = await session.get(CronJobModel, job.id)
            data = self._job_to_model_fields(job)

            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
                existing.updated_at = datetime.utcnow()
                session.add(existing)
            else:
                model = CronJobModel(id=job.id, **data)
                session.add(model)

            await session.flush()

    async def delete(self, job_id: UUID) -> bool:
        """Delete a cron job from the database."""
        from leagent.db.models.cron import CronJobModel

        async with self._db.session() as session:
            obj = await session.get(CronJobModel, job_id)
            if not obj:
                return False
            await session.delete(obj)
            await session.flush()
            return True

    async def get(self, job_id: UUID) -> CronJob | None:
        """Get a cron job by ID."""
        from leagent.db.models.cron import CronJobModel

        async with self._db.session() as session:
            obj = await session.get(CronJobModel, job_id)
            if not obj:
                return None
            return self._model_to_job(obj)

    async def load_all(self) -> list[CronJob]:
        """Load all cron jobs from the database."""
        from sqlmodel import select
        from leagent.db.models.cron import CronJobModel

        async with self._db.session() as session:
            result = await session.exec(select(CronJobModel))
            return [self._model_to_job(m) for m in result.all()]

    async def save_heartbeat(self, heartbeat: CronHeartbeat) -> None:
        pass

    async def save_execution(self, execution: CronExecution) -> None:
        """Persist a cron execution record."""
        from leagent.db.models.cron import CronExecutionModel

        async with self._db.session() as session:
            existing = await session.get(CronExecutionModel, execution.id)
            fields = self._execution_to_fields(execution)

            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                session.add(existing)
            else:
                model = CronExecutionModel(id=execution.id, **fields)
                session.add(model)

            await session.flush()

    async def get_executions(
        self,
        job_id: UUID,
        limit: int = 100,
        status: str | None = None,
    ) -> list[CronExecution]:
        """Get execution history for a job."""
        from sqlmodel import col, select
        from leagent.db.models.cron import CronExecutionModel

        async with self._db.session() as session:
            q = select(CronExecutionModel).where(
                CronExecutionModel.job_id == job_id
            )
            if status:
                q = q.where(CronExecutionModel.status == status)
            q = q.order_by(col(CronExecutionModel.created_at).desc()).limit(limit)
            result = await session.exec(q)
            return [self._model_to_execution(m) for m in result.all()]

    def _job_to_model_fields(self, job: CronJob) -> dict[str, Any]:
        return {
            "name": job.name,
            "description": job.description,
            "schedule": job.schedule,
            "target_type": job.target_type.value,
            "target_id": job.target_id,
            "workflow_id": job.workflow_id,
            "enabled": job.enabled,
            "status": job.status.value,
            "payload": json.dumps(job.payload) if job.payload else None,
            "timeout_sec": job.timeout_sec,
            "max_retries": job.max_retries,
            "retry_delay_sec": job.retry_delay_sec,
            "timezone": job.timezone,
            "coalesce": job.coalesce,
            "max_instances": job.max_instances,
            "misfire_grace_sec": job.misfire_grace_sec,
            "channel_ids": json.dumps(job.channel_ids) if job.channel_ids else None,
            "notify_on_start": job.notify_on_start,
            "notify_on_complete": job.notify_on_complete,
            "notify_on_fail": job.notify_on_fail,
            "last_run_at": job.last_run_at,
            "next_run_at": job.next_run_at,
            "last_run_status": job.last_run_status.value if job.last_run_status else None,
            "last_error": job.last_error,
            "run_count": job.run_count,
            "success_count": job.success_count,
            "error_count": job.error_count,
            "consecutive_failures": job.consecutive_failures,
            "user_id": UUID(job.user_id) if job.user_id else None,
            "tags": json.dumps(job.tags) if job.tags else None,
            "meta": json.dumps(job.metadata) if job.metadata else None,
            "version": job.version,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    def _model_to_job(self, m: Any) -> CronJob:
        from leagent.cron.base import CronJobStatus, CronJobType

        return CronJob(
            id=m.id,
            name=m.name,
            description=m.description or "",
            schedule=m.schedule,
            target_type=CronJobType(m.target_type),
            target_id=m.target_id,
            workflow_id=m.workflow_id,
            enabled=m.enabled,
            status=CronJobStatus(m.status),
            payload=json.loads(m.payload) if m.payload else {},
            timeout_sec=m.timeout_sec,
            max_retries=m.max_retries,
            retry_delay_sec=m.retry_delay_sec,
            timezone=m.timezone,
            coalesce=m.coalesce,
            max_instances=m.max_instances,
            misfire_grace_sec=m.misfire_grace_sec,
            channel_ids=json.loads(m.channel_ids) if m.channel_ids else [],
            notify_on_start=m.notify_on_start,
            notify_on_complete=m.notify_on_complete,
            notify_on_fail=m.notify_on_fail,
            last_run_at=m.last_run_at,
            next_run_at=m.next_run_at,
            last_run_status=CronExecutionStatus(m.last_run_status) if m.last_run_status else None,
            last_error=m.last_error,
            run_count=m.run_count,
            success_count=m.success_count,
            error_count=m.error_count,
            consecutive_failures=m.consecutive_failures,
            user_id=str(m.user_id) if m.user_id else None,
            tags=json.loads(m.tags) if m.tags else [],
            metadata=json.loads(m.meta) if m.meta else {},
            version=m.version,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    def _execution_to_fields(self, e: CronExecution) -> dict[str, Any]:
        return {
            "job_id": e.job_id,
            "job_name": e.job_name,
            "execution_number": e.execution_number,
            "status": e.status.value,
            "trigger_type": e.trigger_type,
            "scheduled_at": e.scheduled_at,
            "started_at": e.started_at,
            "completed_at": e.completed_at,
            "workflow_id": e.workflow_id,
            "workflow_state_id": e.workflow_state_id,
            "inputs": json.dumps(e.inputs) if e.inputs else None,
            "outputs": json.dumps(e.outputs) if e.outputs else None,
            "error": e.error,
            "error_type": e.error_type,
            "stack_trace": e.stack_trace,
            "retry_count": e.retry_count,
            "max_retries": e.max_retries,
            "duration_ms": e.duration_ms,
            "node_count": e.node_count,
        }

    def _model_to_execution(self, m: Any) -> CronExecution:
        from leagent.cron.base import CronExecutionStatus

        return CronExecution(
            id=m.id,
            job_id=m.job_id,
            job_name=m.job_name or "",
            execution_number=m.execution_number,
            status=CronExecutionStatus(m.status),
            trigger_type=m.trigger_type,
            scheduled_at=m.scheduled_at,
            started_at=m.started_at,
            completed_at=m.completed_at,
            workflow_id=m.workflow_id,
            workflow_state_id=m.workflow_state_id,
            inputs=json.loads(m.inputs) if m.inputs else {},
            outputs=json.loads(m.outputs) if m.outputs else {},
            error=m.error,
            error_type=m.error_type,
            stack_trace=m.stack_trace,
            retry_count=m.retry_count,
            max_retries=m.max_retries,
            duration_ms=m.duration_ms,
            node_count=m.node_count,
        )
