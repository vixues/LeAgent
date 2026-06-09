"""Durable enqueue helpers for background jobs.

These replace ad-hoc ``BackgroundTasks.add_task`` calls in the API layer: work
is persisted as a :class:`~leagent.db.models.task.Task` row and executed by the
:class:`~leagent.services.task_manager.TaskManager`, so it survives restarts
(recovered via :func:`recover_pending_jobs`) and retries on failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.db.models.task import Task, TaskStatus, TaskType

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService

logger = logging.getLogger(__name__)


async def enqueue_file_processing(
    db: "DatabaseService",
    *,
    file_id: str,
    storage_path: str,
    mime_type: str | None,
    original_name: str | None,
    user_id: UUID | None = None,
    session_id: UUID | None = None,
) -> str | None:
    """Persist and start a durable file-processing job.

    Falls back to a detached coroutine only if the :class:`TaskManager` is
    unavailable (e.g. minimal test contexts), preserving prior behavior.
    """
    payload: dict[str, Any] = {
        "file_id": file_id,
        "storage_path": storage_path,
        "mime_type": mime_type,
        "original_name": original_name,
    }

    try:
        from leagent.services.task_manager import get_task_manager

        tm = get_task_manager()
    except Exception:  # noqa: BLE001 - TaskManager not initialised
        tm = None

    if tm is None or tm.get_handler(TaskType.IMPORT) is None:
        return await _fallback_inline(payload)

    try:
        async with db.session() as session:
            task = await tm.create_task(
                session,
                name=f"process:{original_name or file_id}",
                task_type=TaskType.IMPORT,
                description="Uploaded file processing (extract / index)",
                user_id=user_id,
                session_id=session_id,
                input_data=payload,
            )
            await tm.start_task(session, task, params=payload)
        return str(task.id)
    except Exception as exc:  # noqa: BLE001 - never block the upload response
        logger.warning("enqueue_file_processing_failed file_id=%s err=%s", file_id, exc)
        return await _fallback_inline(payload)


async def _fallback_inline(payload: dict[str, Any]) -> str | None:
    import asyncio

    async def _run() -> None:
        try:
            from leagent.services.service_manager import get_service_manager

            sm = get_service_manager()
            processor = getattr(sm, "file_processing", None)
            if processor is not None:
                await processor.process_and_update_db(
                    file_id=payload["file_id"],
                    file_path=payload["storage_path"],
                    mime_type=payload.get("mime_type"),
                    original_name=payload.get("original_name"),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("inline_file_processing_failed: %s", exc)

    asyncio.ensure_future(_run())
    return None


async def recover_pending_jobs(db: "DatabaseService") -> int:
    """Re-enqueue durable jobs left non-terminal by a previous process.

    Tasks stuck in ``PENDING``/``QUEUED``/``RUNNING`` after a crash/restart are
    re-started so persisted work is not lost. Returns the number recovered.
    """
    from sqlmodel import col, select

    from leagent.services.task_manager import get_task_manager

    try:
        tm = get_task_manager()
    except Exception:  # noqa: BLE001
        return 0

    recovered = 0
    stale_states = [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.RUNNING]
    recoverable_types = [TaskType.IMPORT]

    try:
        async with db.session() as session:
            stmt = select(Task).where(
                col(Task.status).in_(stale_states),
                col(Task.task_type).in_(recoverable_types),
            )
            rows = list((await session.exec(stmt)).all())
    except Exception as exc:  # noqa: BLE001
        logger.warning("recover_pending_jobs_query_failed: %s", exc)
        return 0

    for task in rows:
        if tm.get_handler(task.task_type) is None:
            continue
        import json

        try:
            params = json.loads(task.input_data) if task.input_data else {}
        except (TypeError, ValueError):
            params = {}
        try:
            async with db.session() as session:
                fresh = await session.get(Task, task.id)
                if fresh is None:
                    continue
                fresh.status = TaskStatus.QUEUED
                session.add(fresh)
                await session.flush()
                await tm.start_task(session, fresh, params=params)
            recovered += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("recover_pending_job_failed task_id=%s err=%s", task.id, exc)

    if recovered:
        logger.info("Recovered %d pending background job(s)", recovered)
    return recovered
