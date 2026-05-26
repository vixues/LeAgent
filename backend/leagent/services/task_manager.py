"""Task lifecycle manager service.

Mirrors the reference tasks.ts / Task.ts architecture by providing:
- Polymorphic task dispatch (getTaskByType → get_handler)
- Abort-controller based cancellation per running task
- Output file streaming for live task logs
- Terminal-state guards preventing operations on dead tasks
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

from leagent.services.database.models.task import (
    Task,
    TaskContext,
    TaskStatus,
    TaskType,
    generate_task_id,
    is_terminal_task_status,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from leagent.config.settings import Settings

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Task handler protocol (mirrors reference Task interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class TaskHandler(Protocol):
    """Interface that every concrete task type must implement.

    Mirrors the reference ``Task`` interface which exposes ``kill()``
    and a ``type`` discriminant.
    """

    name: str
    task_type: TaskType

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> dict[str, Any]:
        """Execute the task and return a result dict."""
        ...

    async def kill(self, task_id: str, session: AsyncSession) -> None:
        """Forcefully terminate the task (best-effort)."""
        ...


# ---------------------------------------------------------------------------
# TaskManager
# ---------------------------------------------------------------------------


class TaskManager:
    """Orchestrates the full task lifecycle.

    Responsibilities:
    - Registry of task handlers by TaskType
    - Creating tasks (DB row + TaskContext)
    - Starting / running tasks with abort support
    - Killing running tasks
    - Reading streamed output from task log files
    - Querying active / completed tasks
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings
        self._handlers: dict[TaskType, TaskHandler] = {}
        self._active_contexts: dict[str, TaskContext] = {}
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}
        self._kill_owned_cancellations: set[str] = set()
        # Optional distributed registry (populated by service manager once
        # Redis is online). Remains None in single-process tests / dev.
        self._distributed: Any | None = None

    def attach_distributed_registry(self, registry: Any) -> None:
        """Enable cross-replica cancel + global active-task visibility."""
        self._distributed = registry

        async def _cancel_local(task_id: str) -> None:
            bg = self._running_tasks.get(task_id)
            ctx = self._active_contexts.get(task_id)
            if ctx is not None:
                ctx.abort()
            if bg is not None and not bg.done():
                bg.cancel()

        registry.register_cancel_handler("*", _cancel_local)

    # -- Handler registry ---------------------------------------------------

    def register_handler(self, handler: TaskHandler) -> None:
        """Register a handler for a task type."""
        self._handlers[handler.task_type] = handler
        logger.info("Registered task handler: %s → %s", handler.task_type.value, handler.name)

    def get_handler(self, task_type: TaskType) -> TaskHandler | None:
        """Get the handler for a task type (mirrors reference getTaskByType)."""
        return self._handlers.get(task_type)

    def get_all_handlers(self) -> list[TaskHandler]:
        """Return all registered handlers (mirrors reference getAllTasks)."""
        return list(self._handlers.values())

    # -- Lifecycle ----------------------------------------------------------

    async def create_task(
        self,
        session: AsyncSession,
        *,
        name: str,
        task_type: TaskType = TaskType.AGENT,
        description: str = "",
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        input_data: dict[str, Any] | None = None,
        priority: str = "normal",
        parent_id: UUID | None = None,
        timeout_seconds: int = 300,
    ) -> Task:
        """Create a task DB row and prepare its context."""
        from leagent.services.database.models.task import TaskPriority

        short_id = generate_task_id(task_type)
        output_dir = None
        if self._settings:
            output_dir = getattr(self._settings, "task_output_dir", None)

        ctx = TaskContext(short_id, task_type, output_dir=output_dir)

        priority_map = {
            "low": TaskPriority.LOW,
            "normal": TaskPriority.NORMAL,
            "high": TaskPriority.HIGH,
            "urgent": TaskPriority.URGENT,
        }

        task = Task(
            name=name,
            task_type=task_type,
            description=description,
            user_id=user_id,
            session_id=session_id,
            input_data=json.dumps(input_data) if input_data else None,
            priority=priority_map.get(priority, TaskPriority.NORMAL),
            parent_id=parent_id,
            timeout_seconds=timeout_seconds,
            output_file=ctx.output_file,
        )
        session.add(task)
        await session.flush()
        await session.refresh(task)

        self._active_contexts[str(task.id)] = ctx
        logger.info("task_created", task_id=str(task.id), short_id=short_id, task_type=task_type.value)
        return task

    async def start_task(
        self,
        session: AsyncSession,
        task: Task,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Transition a task to RUNNING and spawn its handler in the background."""
        if is_terminal_task_status(task.status):
            logger.warning("Cannot start terminal task %s (status=%s)", task.id, task.status.value)
            return

        handler = self.get_handler(task.task_type)
        if handler is None:
            task.status = TaskStatus.FAILED
            task.error = f"No handler registered for task type: {task.task_type.value}"
            session.add(task)
            return

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        session.add(task)
        await session.flush()

        ctx = self._active_contexts.get(str(task.id))
        if ctx is None:
            output_dir = None
            if self._settings:
                output_dir = getattr(self._settings, "task_output_dir", None)
            ctx = TaskContext(str(task.id), task.task_type, output_dir=output_dir)
            self._active_contexts[str(task.id)] = ctx

        bg = asyncio.create_task(self._run_task(str(task.id), handler, ctx, params or {}))
        self._running_tasks[str(task.id)] = bg

        if self._distributed is not None:
            try:
                await self._distributed.register(
                    str(task.id),
                    task_type=getattr(task.task_type, "value", str(task.task_type)),
                    user_id=str(task.user_id) if task.user_id else None,
                    tenant_id=getattr(task, "workspace_id", None),
                )
            except Exception:
                logger.debug("distributed task register failed", exc_info=True)

    async def _run_task(
        self,
        task_id: str,
        handler: TaskHandler,
        ctx: TaskContext,
        params: dict[str, Any],
    ) -> None:
        """Background coroutine wrapping the handler's spawn."""
        try:
            from leagent.services.database import get_database_service

            db = get_database_service()
            async with db.session() as session:
                task = await session.get(Task, UUID(task_id))
                if task is None:
                    await self._mark_failed(task_id, "Task row disappeared before execution")
                    return

                timeout = max(1, int(task.timeout_seconds or 300))
                handler_params = dict(params)
                handler_params.setdefault("__task_db_id", task_id)
                handler_params.setdefault("__task_short_id", ctx.task_id)
                if task.user_id:
                    handler_params.setdefault("user_id", str(task.user_id))
                if task.session_id:
                    handler_params.setdefault("session_id", str(task.session_id))

            # Do not hold the manager's task-row transaction while a handler
            # runs; SQLite readers can otherwise block kill/cancel commits.
            async with db.session() as handler_session:
                result = await asyncio.wait_for(
                    handler.spawn(ctx, handler_params, handler_session),
                    timeout=timeout,
                )

            async with db.session() as session:
                task = await session.get(Task, UUID(task_id))
                if task and not is_terminal_task_status(task.status):
                    if ctx.abort_event.is_set():
                        task.status = TaskStatus.KILLED
                        task.completed_at = datetime.utcnow()
                        if task.started_at:
                            task.duration_ms = int(
                                (task.completed_at - task.started_at).total_seconds() * 1000
                            )
                        task.output_offset = ctx.output_offset
                        session.add(task)
                        return
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.utcnow()
                    if task.started_at:
                        task.duration_ms = int((task.completed_at - task.started_at).total_seconds() * 1000)
                    task.progress = 100
                    task.output_data = json.dumps(result) if result else None
                    task.output_offset = ctx.output_offset
                    session.add(task)

        except asyncio.CancelledError:
            if task_id not in self._kill_owned_cancellations:
                await self._mark_killed(task_id)
        except asyncio.TimeoutError:
            ctx.abort()
            await self._mark_timeout(task_id)
        except Exception as e:
            logger.error("task_failed", task_id=task_id, error=str(e), exc_info=True)
            await self._mark_failed(task_id, str(e))
        finally:
            self._active_contexts.pop(task_id, None)
            self._running_tasks.pop(task_id, None)
            self._kill_owned_cancellations.discard(task_id)
            if self._distributed is not None:
                try:
                    await self._distributed.deregister(task_id)
                except Exception:
                    logger.debug("distributed task deregister failed", exc_info=True)

    async def cancel_task(self, session: AsyncSession, task_id: str) -> bool:
        """Request cooperative cancellation without force-cancelling immediately."""

        ctx = self._active_contexts.get(task_id)
        if ctx:
            ctx.abort()

        task = await session.get(Task, UUID(task_id))
        if task and not is_terminal_task_status(task.status):
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            task.output_offset = ctx.output_offset if ctx else task.output_offset
            if task.started_at:
                task.duration_ms = int((task.completed_at - task.started_at).total_seconds() * 1000)
            session.add(task)
            return True
        return False

    async def kill_task(self, session: AsyncSession, task_id: str) -> bool:
        """Kill a running task (mirrors reference Task.kill).

        If the task is running on a different replica, route the cancel
        through Redis Pub/Sub via the distributed registry.
        """
        ctx = self._active_contexts.get(task_id)
        if ctx:
            ctx.abort()

        bg = self._running_tasks.get(task_id)
        if bg and not bg.done():
            self._kill_owned_cancellations.add(task_id)
            bg.cancel()
            with suppress(asyncio.CancelledError):
                await bg
        elif self._distributed is not None:
            try:
                routed = await self._distributed.request_cancel(task_id)
                if routed:
                    logger.info("task_cancel_routed", task_id=task_id)
            except Exception:
                logger.debug("distributed cancel routing failed", exc_info=True)

        handler = None
        task = await session.get(Task, UUID(task_id))
        if task:
            handler = self.get_handler(task.task_type)
            try:
                from leagent.services.execution.engine import get_execution_engine

                await get_execution_engine().cancel_session(task_id)
                if task.session_id:
                    await get_execution_engine().cancel_session(str(task.session_id))
            except Exception:
                logger.debug("execution cancel during task kill failed", exc_info=True)

        if handler is not None:
            try:
                await handler.kill(task_id, session)
            except Exception as e:
                logger.warning("Handler kill failed for %s: %s", task_id, e)

        if task and not is_terminal_task_status(task.status):
            task.status = TaskStatus.KILLED
            task.completed_at = datetime.utcnow()
            if task.started_at:
                task.duration_ms = int((task.completed_at - task.started_at).total_seconds() * 1000)
            task.output_offset = ctx.output_offset if ctx else task.output_offset
            session.add(task)
            logger.info("task_killed", task_id=task_id)
            return True

        return False

    # -- Output streaming ---------------------------------------------------

    def read_output(self, task_id: str, *, offset: int = 0, output_file: str | None = None) -> str:
        """Read task output from its log file starting at the given byte offset."""
        ctx = self._active_contexts.get(task_id)
        output_file = ctx.output_file if ctx else output_file

        if output_file is None:
            return ""

        try:
            with open(output_file, "r", encoding="utf-8") as f:
                if offset > 0:
                    f.seek(offset)
                return f.read()
        except FileNotFoundError:
            return ""

    # -- Query helpers ------------------------------------------------------

    def is_running(self, task_id: str) -> bool:
        return task_id in self._running_tasks

    @property
    def active_task_count(self) -> int:
        return len(self._running_tasks)

    def get_active_task_ids(self) -> list[str]:
        return list(self._running_tasks.keys())

    # -- Internal helpers ---------------------------------------------------

    async def _mark_killed(self, task_id: str) -> None:
        try:
            from leagent.services.database import get_database_service

            db = get_database_service()
            async with db.session() as session:
                task = await session.get(Task, UUID(task_id))
                if task and not is_terminal_task_status(task.status):
                    task.status = TaskStatus.KILLED
                    task.completed_at = datetime.utcnow()
                    if task.started_at:
                        task.duration_ms = int((task.completed_at - task.started_at).total_seconds() * 1000)
                    ctx = self._active_contexts.get(task_id)
                    if ctx:
                        task.output_offset = ctx.output_offset
                    session.add(task)
        except Exception as e:
            logger.error("Failed to mark task killed: %s", e)

    async def _mark_timeout(self, task_id: str) -> None:
        try:
            from leagent.services.database import get_database_service
            from leagent.services.execution.engine import get_execution_engine

            await get_execution_engine().cancel_session(task_id)
            db = get_database_service()
            async with db.session() as session:
                task = await session.get(Task, UUID(task_id))
                if task and task.session_id:
                    await get_execution_engine().cancel_session(str(task.session_id))
                if task and not is_terminal_task_status(task.status):
                    task.status = TaskStatus.TIMEOUT
                    task.error = f"Task exceeded {task.timeout_seconds}s wall-clock budget"
                    task.completed_at = datetime.utcnow()
                    if task.started_at:
                        task.duration_ms = int((task.completed_at - task.started_at).total_seconds() * 1000)
                    ctx = self._active_contexts.get(task_id)
                    if ctx:
                        task.output_offset = ctx.output_offset
                    session.add(task)
        except Exception as e:
            logger.error("Failed to mark task timeout: %s", e)

    async def _mark_failed(self, task_id: str, error: str) -> None:
        try:
            from leagent.services.database import get_database_service

            db = get_database_service()
            async with db.session() as session:
                task = await session.get(Task, UUID(task_id))
                if task and not is_terminal_task_status(task.status):
                    task.status = TaskStatus.FAILED
                    task.error = error
                    task.completed_at = datetime.utcnow()
                    if task.started_at:
                        task.duration_ms = int((task.completed_at - task.started_at).total_seconds() * 1000)
                    ctx = self._active_contexts.get(task_id)
                    if ctx:
                        task.output_offset = ctx.output_offset
                    session.add(task)
        except Exception as e:
            logger.error("Failed to mark task failed: %s", e)

    async def shutdown(self) -> None:
        """Kill all running tasks during shutdown."""
        for task_id in list(self._running_tasks.keys()):
            ctx = self._active_contexts.get(task_id)
            if ctx:
                ctx.abort()
            bg = self._running_tasks.get(task_id)
            if bg and not bg.done():
                bg.cancel()

        if self._running_tasks:
            await asyncio.gather(
                *self._running_tasks.values(),
                return_exceptions=True,
            )

        self._running_tasks.clear()
        self._active_contexts.clear()
        logger.info("TaskManager shutdown complete")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    """Get the global TaskManager instance."""
    if _task_manager is None:
        raise RuntimeError("TaskManager not initialized. Call init_task_manager() first.")
    return _task_manager


def init_task_manager(settings: Any = None) -> TaskManager:
    """Initialize the global TaskManager singleton."""
    global _task_manager
    _task_manager = TaskManager(settings)
    return _task_manager
