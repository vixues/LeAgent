"""``TaskHandler`` that fans out to a list of child tasks."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.db.models.task import (
    TaskContext,
    TaskStatus,
    TaskType,
    is_terminal_task_status,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from leagent.services.service_manager import ServiceManager

logger = logging.getLogger(__name__)


class BatchTaskHandler:
    """Spawn a sub-task per child entry and wait for all of them."""

    name = "batch_task_handler"
    task_type: TaskType = TaskType.BATCH

    def __init__(
        self,
        *,
        service_manager: "ServiceManager | None" = None,
        max_concurrency: int = 5,
    ) -> None:
        self._sm = service_manager
        self._max_concurrency = max_concurrency

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: "AsyncSession",
    ) -> dict[str, Any]:
        from leagent.db import get_database_service
        from leagent.db.models import Task
        from leagent.services.task_manager import get_task_manager

        children = params.get("children") or params.get("items") or []
        if not isinstance(children, list) or not children:
            raise ValueError("Batch task requires a non-empty 'children' list")

        mgr = get_task_manager()
        db = get_database_service()

        child_ids: list[str] = []
        sem = asyncio.Semaphore(
            int(params.get("max_concurrency") or self._max_concurrency)
        )

        async def _spawn_one(idx: int, child: dict[str, Any]) -> str:
            async with sem:
                child_type_str = child.get("task_type", "agent")
                try:
                    ctype = TaskType(child_type_str)
                except ValueError:
                    ctype = TaskType.AGENT
                async with db.session() as s:
                    child_task = await mgr.create_task(
                        s,
                        name=child.get("name") or f"{task_ctx.task_id}-child-{idx}",
                        task_type=ctype,
                        description=child.get("description", ""),
                        input_data=child.get("input_data") or child.get("params") or child,
                        timeout_seconds=int(child.get("timeout_seconds", 300)),
                    )
                    await mgr.start_task(s, child_task, params=child.get("input_data") or child)
                    await s.commit()
                    return str(child_task.id)

        launch_coros = [_spawn_one(i, c) for i, c in enumerate(children)]
        child_ids = await asyncio.gather(*launch_coros, return_exceptions=False)

        task_ctx.append_output(
            json.dumps({"event": "batch_spawned", "children": child_ids}) + "\n"
        )

        poll_interval = float(params.get("poll_interval_sec", 1.0))
        summary: list[dict[str, Any]] = []
        while True:
            if task_ctx.is_aborted:
                break
            async with db.session() as s:
                statuses: list[tuple[str, TaskStatus]] = []
                for cid in child_ids:
                    t = await s.get(Task, UUID(cid))
                    if t is None:
                        statuses.append((cid, TaskStatus.FAILED))
                    else:
                        statuses.append((cid, t.status))
                if all(is_terminal_task_status(s_) for _, s_ in statuses):
                    for cid, st in statuses:
                        summary.append({"task_id": cid, "status": st.value})
                    break
            await asyncio.sleep(poll_interval)

        task_ctx.append_output(
            json.dumps({"event": "batch_done", "results": summary}) + "\n"
        )
        failed = [s for s in summary if s["status"] not in {"completed"}]
        if failed:
            return {"children": summary, "failed_count": len(failed)}
        return {"children": summary, "failed_count": 0}

    async def kill(self, task_id: str, session: "AsyncSession") -> None:
        # Child kills are best-effort and handled by the top-level abort
        # propagation in ``TaskManager.kill_task``.
        return None
