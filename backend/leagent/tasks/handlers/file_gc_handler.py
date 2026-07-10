"""Durable task handler for catalog blob garbage collection."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from leagent.db.models.task import TaskContext, TaskType
from leagent.library.gc import run_file_gc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from leagent.services.service_manager import ServiceManager

logger = logging.getLogger(__name__)


class FileGcTaskHandler:
    """Run :func:`leagent.library.gc.run_file_gc` as a persisted task."""

    name = "file_gc_handler"
    task_type: TaskType = TaskType.MONITOR

    def __init__(self, service_manager: "ServiceManager | None" = None) -> None:
        self._sm = service_manager

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: "AsyncSession",
    ) -> dict[str, Any]:
        del session, task_ctx
        sm = self._sm
        if sm is None:
            from leagent.services.service_manager import get_service_manager

            sm = get_service_manager()
        if sm.db is None:
            return {"skipped": True, "reason": "no_database"}
        grace_hours = int(params.get("grace_hours") or 168)
        dry_run = bool(params.get("dry_run"))
        summary = await run_file_gc(sm.db, grace_hours=grace_hours, dry_run=dry_run)
        logger.info("file_gc_complete %s", summary)
        return summary
