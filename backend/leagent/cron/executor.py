"""Cron job executor for running scheduled workflows.

This module provides the CronExecutor class that handles the actual
execution of scheduled jobs, including workflow invocation, channel
notifications, and result logging.
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

import structlog

from .base import CronExecution, CronExecutionStatus, CronJob, CronJobType

if TYPE_CHECKING:
    from uuid import UUID

    from leagent.channels.manager import ChannelManager
    from leagent.workflow import WorkflowDocument, WorkflowExecutor, WorkflowResult

logger = structlog.get_logger(__name__)


class ExecutionLogger(Protocol):
    """Protocol for logging execution results."""

    async def log_execution(self, execution: CronExecution) -> None:
        """Log an execution record."""
        ...

    async def get_executions(
        self,
        job_id: UUID,
        limit: int = 100,
    ) -> list[CronExecution]:
        """Get execution history for a job."""
        ...


class InMemoryExecutionLogger:
    """In-memory implementation of execution logging."""

    def __init__(self, max_per_job: int = 1000) -> None:
        self._executions: dict[UUID, list[CronExecution]] = {}
        self._max_per_job = max_per_job
        self._lock = asyncio.Lock()

    async def log_execution(self, execution: CronExecution) -> None:
        """Log an execution record."""
        async with self._lock:
            if execution.job_id not in self._executions:
                self._executions[execution.job_id] = []

            executions = self._executions[execution.job_id]
            executions.append(execution)

            if len(executions) > self._max_per_job:
                self._executions[execution.job_id] = executions[-self._max_per_job :]

    async def get_executions(
        self,
        job_id: UUID,
        limit: int = 100,
    ) -> list[CronExecution]:
        """Get execution history for a job."""
        async with self._lock:
            executions = self._executions.get(job_id, [])
            return list(reversed(executions[-limit:]))


class CronExecutor:
    """Executor for cron job payloads.

    Handles workflow execution, channel notifications,
    result logging, and error handling with retry support.
    """

    def __init__(
        self,
        workflow_executor: WorkflowExecutor | None = None,
        workflow_registry: Any = None,
        channel_manager: ChannelManager | None = None,
        execution_logger: ExecutionLogger | None = None,
        default_timeout_sec: int = 3600,
        max_concurrent_executions: int = 10,
    ):
        """Initialize the cron executor.

        Args:
            workflow_executor: Executor for running workflows.
            workflow_registry: Registry for loading workflow definitions.
            channel_manager: Manager for sending notifications.
            execution_logger: Logger for execution records.
            default_timeout_sec: Default execution timeout.
            max_concurrent_executions: Maximum concurrent executions.
        """
        self.workflow_executor = workflow_executor
        self.workflow_registry = workflow_registry
        self.channel_manager = channel_manager
        self.execution_logger = execution_logger or InMemoryExecutionLogger()
        self.default_timeout_sec = default_timeout_sec
        self.max_concurrent_executions = max_concurrent_executions

        self._semaphore = asyncio.Semaphore(max_concurrent_executions)
        self._running_tasks: dict[UUID, asyncio.Task[Any]] = {}

    async def execute(self, job: CronJob, execution: CronExecution) -> CronExecution:
        """Execute a cron job.

        Args:
            job: The job definition.
            execution: The execution record to track progress.

        Returns:
            Updated execution record.

        Raises:
            Exception: If execution fails after all retries.
        """
        async with self._semaphore:
            execution.start()

            if job.notify_on_start:
                await self._notify_start(job, execution)

            try:
                result = await self._execute_with_retry(job, execution)

                if result:
                    execution.complete(result)
                else:
                    execution.complete({})

                if job.notify_on_complete:
                    await self._notify_complete(job, execution)

            except asyncio.TimeoutError:
                execution.timeout()
                if job.notify_on_fail:
                    await self._notify_timeout(job, execution)
                raise

            except Exception as e:
                tb = traceback.format_exc()
                execution.fail(str(e), type(e).__name__, tb)

                if job.notify_on_fail:
                    await self._notify_failure(job, execution)

                raise

            finally:
                await self.execution_logger.log_execution(execution)

            return execution

    async def _execute_with_retry(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> dict[str, Any] | None:
        """Execute with retry logic.

        Args:
            job: The job definition.
            execution: The execution record.

        Returns:
            Execution result or None.
        """
        last_error: Exception | None = None

        for attempt in range(job.max_retries + 1):
            execution.retry_count = attempt

            try:
                timeout = job.timeout_sec or self.default_timeout_sec

                result = await asyncio.wait_for(
                    self._execute_target(job, execution),
                    timeout=timeout,
                )

                return result

            except asyncio.TimeoutError:
                logger.warning(
                    "cron_execution_timeout",
                    job_id=str(job.id),
                    attempt=attempt,
                    timeout_sec=job.timeout_sec,
                )
                raise

            except Exception as e:
                last_error = e
                logger.warning(
                    "cron_execution_attempt_failed",
                    job_id=str(job.id),
                    attempt=attempt,
                    error=str(e),
                )

                if attempt < job.max_retries:
                    await asyncio.sleep(job.retry_delay_sec)

        if last_error:
            raise last_error

        return None

    async def _execute_target(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> dict[str, Any] | None:
        """Execute the job target based on type.

        Args:
            job: The job definition.
            execution: The execution record.

        Returns:
            Execution result.
        """
        match job.target_type:
            case CronJobType.WORKFLOW:
                return await self._execute_workflow(job, execution)
            case CronJobType.TASK:
                return await self._execute_task(job, execution)
            case CronJobType.WEBHOOK:
                return await self._execute_webhook(job, execution)
            case CronJobType.SCRIPT:
                return await self._execute_script(job, execution)
            case _:
                raise ValueError(f"Unknown job type: {job.target_type}")

    async def _execute_workflow(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> dict[str, Any]:
        """Execute a workflow job.

        Args:
            job: The job definition.
            execution: The execution record.

        Returns:
            Workflow outputs.
        """
        if not self.workflow_executor:
            raise RuntimeError("Workflow executor not configured")

        workflow_id = job.workflow_id or job.target_id
        if not workflow_id:
            raise ValueError("No workflow ID specified for job")

        execution.workflow_id = workflow_id

        definition = await self._load_workflow_definition(workflow_id)
        if not definition:
            raise ValueError(f"Workflow not found: {workflow_id}")

        inputs = {**job.payload, **(execution.inputs or {})}

        logger.info(
            "cron_workflow_start",
            job_id=str(job.id),
            workflow_id=workflow_id,
            execution_id=str(execution.id),
        )

        result = await self.workflow_executor.execute(definition, inputs)

        execution.workflow_state_id = result.state_id
        execution.node_count = len(result.execution_history)

        if not result.success:
            error_msg = "; ".join(result.errors) if result.errors else "Workflow failed"
            raise RuntimeError(error_msg)

        return result.outputs

    async def _execute_task(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> dict[str, Any]:
        """Create and run a :class:`Task` via :class:`TaskManager`.

        The cron payload decides which :class:`TaskType` to instantiate
        (``payload.task_type``) and the rest of ``payload`` is handed to
        the handler as ``input_data``. The method polls for terminal
        status so cron stats reflect the task outcome.
        """
        from uuid import UUID

        from leagent.db import get_database_service
        from leagent.db.models import (
            Task,
            TaskStatus,
            TaskType,
            is_terminal_task_status,
        )
        from leagent.services.task_manager import get_task_manager

        mgr = get_task_manager()
        db = get_database_service()

        task_type_str = job.payload.get("task_type", "agent")
        try:
            task_type = TaskType(task_type_str)
        except ValueError:
            task_type = TaskType.AGENT

        user_uuid = None
        if job.user_id:
            try:
                user_uuid = UUID(str(job.user_id))
            except (TypeError, ValueError):
                user_uuid = None

        timeout_sec = int(job.timeout_sec or self.default_timeout_sec)
        input_data = job.payload.get("input_data") or job.payload

        logger.info(
            "cron_task_start",
            job_id=str(job.id),
            task_type=task_type.value,
            execution_id=str(execution.id),
        )

        async with db.session() as session:
            task = await mgr.create_task(
                session,
                name=f"cron:{job.name}",
                task_type=task_type,
                description=f"Cron job {job.id}",
                user_id=user_uuid,
                input_data=input_data if isinstance(input_data, dict) else None,
                timeout_seconds=timeout_sec,
            )
            await mgr.start_task(
                session,
                task,
                params=input_data if isinstance(input_data, dict) else {},
            )
            task_id = str(task.id)
            await session.commit()

        execution.workflow_id = task_id
        execution.inputs = dict(execution.inputs or {})
        execution.inputs["task_id"] = task_id

        poll_interval = float(job.payload.get("poll_interval_sec", 1.0))
        deadline = asyncio.get_event_loop().time() + timeout_sec
        final_status: TaskStatus = TaskStatus.PENDING
        output_data: Any = None
        error: str | None = None

        while True:
            async with db.session() as s:
                t = await s.get(Task, UUID(task_id))
                if t is None:
                    raise RuntimeError(f"Task {task_id} disappeared during execution")
                final_status = t.status
                output_data = t.output_data
                error = t.error

            if is_terminal_task_status(final_status):
                break
            if asyncio.get_event_loop().time() > deadline:
                async with db.session() as s:
                    await mgr.kill_task(s, task_id)
                    await s.commit()
                raise asyncio.TimeoutError(
                    f"Cron task {task_id} exceeded {timeout_sec}s"
                )
            await asyncio.sleep(poll_interval)

        try:
            import json as _json

            parsed_output = _json.loads(output_data) if output_data else None
        except Exception:
            parsed_output = output_data

        if final_status != TaskStatus.COMPLETED:
            raise RuntimeError(
                f"Cron task {task_id} ended in {final_status.value}: {error or ''}"
            )

        # Record the last task id back into the job payload so the
        # frontend / admin can link execution history -> task output.
        try:
            job.payload["last_task_id"] = task_id
        except Exception:
            pass

        return {
            "task_id": task_id,
            "status": final_status.value,
            "output": parsed_output,
        }

    async def _execute_webhook(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> dict[str, Any]:
        """Execute a webhook job.

        Args:
            job: The job definition.
            execution: The execution record.

        Returns:
            Webhook response.
        """
        import aiohttp

        webhook_url = job.payload.get("url") or job.target_id
        if not webhook_url:
            raise ValueError("No webhook URL specified")

        method = job.payload.get("method", "POST").upper()
        headers = job.payload.get("headers", {})
        body = job.payload.get("body", {})
        timeout = job.payload.get("timeout", 30)

        logger.info(
            "cron_webhook_start",
            job_id=str(job.id),
            url=webhook_url,
            method=method,
        )

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=webhook_url,
                headers=headers,
                json=body if method in ("POST", "PUT", "PATCH") else None,
                params=body if method == "GET" else None,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                response_body = await response.text()

                if response.status >= 400:
                    raise RuntimeError(
                        f"Webhook failed with status {response.status}: {response_body[:500]}"
                    )

                return {
                    "status_code": response.status,
                    "body": response_body[:10000],
                    "headers": dict(response.headers),
                }

    async def _execute_script(
        self,
        job: CronJob,
        execution: CronExecution,
    ) -> dict[str, Any]:
        """Execute a script job with a safe default of ``shell=False``.

        Callers should provide ``script_path`` and an optional ``args``
        list in the payload; the legacy ``script`` string is only
        honoured when the site opts in by setting
        ``settings.cron_allow_shell=True``.
        """
        import os

        script_path = job.payload.get("script_path")
        args = job.payload.get("args") or []
        legacy_script = job.payload.get("script")

        env_extra = job.payload.get("env", {}) or {}
        timeout = int(job.payload.get("timeout", 300))

        allow_shell = False
        try:
            from leagent.config.settings import get_settings

            allow_shell = bool(getattr(get_settings(), "cron_allow_shell", False))
        except Exception:
            allow_shell = False

        logger.info(
            "cron_script_start",
            job_id=str(job.id),
            execution_id=str(execution.id),
            mode="exec" if script_path else ("shell" if legacy_script and allow_shell else "invalid"),
        )

        env = {**os.environ, **{str(k): str(v) for k, v in env_extra.items()}}

        if script_path:
            if not isinstance(args, list):
                raise ValueError("'args' must be a list when using 'script_path'")
            argv = [str(script_path), *(str(a) for a in args)]
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        elif legacy_script and allow_shell:
            process = await asyncio.create_subprocess_shell(
                legacy_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        else:
            raise ValueError(
                "Script cron jobs require 'script_path' (+ optional 'args'). "
                "The unsafe 'script' string requires cron_allow_shell=True in settings."
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            raise

        if process.returncode != 0:
            raise RuntimeError(
                f"Script failed with exit code {process.returncode}: {stderr.decode()[:1000]}"
            )

        return {
            "exit_code": process.returncode,
            "stdout": stdout.decode()[:10000],
            "stderr": stderr.decode()[:10000],
        }

    async def _load_workflow_definition(self, workflow_id: str) -> WorkflowDocument | None:
        """Load a canonical workflow document by ID.

        Args:
            workflow_id: The workflow ID.

        Returns:
            Workflow document or None.
        """
        if self.workflow_registry:
            return await self.workflow_registry.get(workflow_id)
        return None

    async def _notify_start(self, job: CronJob, execution: CronExecution) -> None:
        """Send notification on job start.

        Args:
            job: The job definition.
            execution: The execution record.
        """
        await self._send_notification(
            job,
            execution,
            "Job Started",
            f"Cron job '{job.name}' has started execution.",
        )

    async def _notify_complete(self, job: CronJob, execution: CronExecution) -> None:
        """Send notification on job completion.

        Args:
            job: The job definition.
            execution: The execution record.
        """
        await self._send_notification(
            job,
            execution,
            "Job Completed",
            f"Cron job '{job.name}' completed successfully in {execution.duration_ms}ms.",
        )

    async def _notify_failure(self, job: CronJob, execution: CronExecution) -> None:
        """Send notification on job failure.

        Args:
            job: The job definition.
            execution: The execution record.
        """
        await self._send_notification(
            job,
            execution,
            "Job Failed",
            f"Cron job '{job.name}' failed: {execution.error}",
        )

    async def _notify_timeout(self, job: CronJob, execution: CronExecution) -> None:
        """Send notification on job timeout.

        Args:
            job: The job definition.
            execution: The execution record.
        """
        await self._send_notification(
            job,
            execution,
            "Job Timeout",
            f"Cron job '{job.name}' timed out after {job.timeout_sec}s.",
        )

    async def _send_notification(
        self,
        job: CronJob,
        execution: CronExecution,
        title: str,
        message: str,
    ) -> None:
        """Send notification to configured channels.

        Args:
            job: The job definition.
            execution: The execution record.
            title: Notification title.
            message: Notification message.
        """
        await self._emit_user_notification(job, execution, title, message)

        if not self.channel_manager or not job.channel_ids:
            return

        notification_text = f"[{title}] {message}"

        for channel_id in job.channel_ids:
            try:
                await self.channel_manager.broadcast(
                    notification_text,
                    channels=[channel_id],
                    meta={
                        "job_id": str(job.id),
                        "execution_id": str(execution.id),
                        "type": "cron_notification",
                    },
                )
                execution.channel_notifications.append(channel_id)

            except Exception as e:
                logger.warning(
                    "cron_notification_failed",
                    job_id=str(job.id),
                    channel_id=channel_id,
                    error=str(e),
                )

    async def _emit_user_notification(
        self,
        job: CronJob,
        execution: CronExecution,
        title: str,
        message: str,
    ) -> None:
        pass

    async def cancel_execution(self, execution_id: UUID) -> bool:
        """Cancel a running execution.

        Args:
            execution_id: ID of the execution to cancel.

        Returns:
            True if cancelled, False if not found.
        """
        task = self._running_tasks.get(execution_id)
        if task:
            task.cancel()
            return True
        return False

    async def get_execution_history(
        self,
        job_id: UUID,
        limit: int = 100,
    ) -> list[CronExecution]:
        """Get execution history for a job.

        Args:
            job_id: The job ID.
            limit: Maximum records to return.

        Returns:
            List of execution records.
        """
        return await self.execution_logger.get_executions(job_id, limit)
