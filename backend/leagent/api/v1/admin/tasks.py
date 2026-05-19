"""Admin-facing task management endpoints.

Mirror of the per-user :mod:`leagent.api.v1.tasks` router but without
the ownership checks — admins can list, inspect, cancel, kill, and retry
any task in the system. All routes are guarded by the ``tasks:read:any``
permission (the same scope used by the workflow task admin views).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import col, func, select

from leagent.schema.api import PaginatedResponse
from leagent.services.auth import PermissionChecker
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.sqlite_compat import load_entity_by_id
from leagent.services.database.models import (
    Task,
    TaskPriority,
    TaskRead,
    TaskStatus,
    TaskType,
    is_terminal_task_status,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_ADMIN_DEP = Depends(PermissionChecker("tasks:read:any"))


@router.get(
    "",
    response_model=PaginatedResponse[TaskRead],
    dependencies=[_ADMIN_DEP],
)
async def list_tasks_admin(
    db: Annotated[DatabaseService, Depends(get_database_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status_filter: Annotated[Optional[TaskStatus], Query(alias="status")] = None,
    task_type: Optional[TaskType] = Query(default=None),
    priority: Optional[TaskPriority] = Query(default=None),
    user_id: Optional[UUID] = Query(default=None),
    flow_id: Optional[UUID] = Query(default=None),
    search: Optional[str] = Query(default=None),
) -> PaginatedResponse[TaskRead]:
    """Cross-user task listing with the standard filters."""
    async with db.session() as session:
        clauses = []
        if status_filter is not None:
            clauses.append(Task.status == status_filter)
        if task_type is not None:
            clauses.append(Task.task_type == task_type)
        if priority is not None:
            clauses.append(Task.priority == priority)
        if user_id is not None:
            clauses.append(Task.user_id == user_id)
        if flow_id is not None:
            clauses.append(Task.flow_id == flow_id)
        if search:
            clauses.append(col(Task.name).ilike(f"%{search.strip()}%"))

        base = select(Task)
        for c in clauses:
            base = base.where(c)

        count_stmt = select(func.count()).select_from(base.subquery())
        total = int((await session.exec(count_stmt)).one() or 0)

        stmt = (
            base.order_by(col(Task.created_at).desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list((await session.exec(stmt)).all())

        return PaginatedResponse[TaskRead](
            items=[TaskRead.model_validate(t) for t in rows],
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
            has_prev=page > 1,
        )


@router.get(
    "/{task_id}",
    response_model=TaskRead,
    dependencies=[_ADMIN_DEP],
)
async def get_task_admin(
    task_id: UUID,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> TaskRead:
    """Fetch any task by id, bypassing ownership checks."""
    async with db.session() as session:
        task = await load_entity_by_id(session, Task, task_id, parent_table="tasks")
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )
        return TaskRead.model_validate(task)


class AdminTaskActionResponse(BaseModel):
    """Uniform response body for admin-side mutations."""

    task_id: str
    ok: bool
    previous_status: str
    new_status: Optional[str] = None
    message: str


@router.post(
    "/{task_id}/cancel",
    response_model=AdminTaskActionResponse,
    dependencies=[_ADMIN_DEP],
)
async def cancel_task_admin(
    task_id: UUID,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> AdminTaskActionResponse:
    """Soft-cancel a task (flip the DB status without touching the runner).

    Use :func:`kill_task_admin` when the task is actively executing.
    """
    async with db.session() as session:
        task = await load_entity_by_id(session, Task, task_id, parent_table="tasks")
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        previous = task.status.value
        if is_terminal_task_status(task.status):
            return AdminTaskActionResponse(
                task_id=str(task_id),
                ok=False,
                previous_status=previous,
                new_status=previous,
                message=f"Task already in terminal state: {previous}",
            )

        task.status = TaskStatus.CANCELLED
        now = datetime.utcnow()
        task.completed_at = now
        task.updated_at = now
        session.add(task)
        await session.commit()

        return AdminTaskActionResponse(
            task_id=str(task_id),
            ok=True,
            previous_status=previous,
            new_status=TaskStatus.CANCELLED.value,
            message="Task cancelled",
        )


@router.post(
    "/{task_id}/kill",
    response_model=AdminTaskActionResponse,
    dependencies=[_ADMIN_DEP],
)
async def kill_task_admin(
    task_id: UUID,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> AdminTaskActionResponse:
    """Force-abort a running task through the :class:`TaskManager`."""
    from leagent.services.task_manager import get_task_manager

    async with db.session() as session:
        task = await load_entity_by_id(session, Task, task_id, parent_table="tasks")
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        previous = task.status.value
        if is_terminal_task_status(task.status):
            return AdminTaskActionResponse(
                task_id=str(task_id),
                ok=False,
                previous_status=previous,
                new_status=previous,
                message=f"Task already in terminal state: {previous}",
            )

        try:
            mgr = get_task_manager()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"TaskManager unavailable: {exc}",
            ) from exc

        killed = await mgr.kill_task(session, str(task_id))
        await session.commit()

        return AdminTaskActionResponse(
            task_id=str(task_id),
            ok=killed,
            previous_status=previous,
            new_status=TaskStatus.KILLED.value if killed else previous,
            message="Kill signal delivered" if killed else "Kill attempted",
        )


class AdminTaskRetryResponse(BaseModel):
    """Response for an admin retry action (returns the new task)."""

    original_task_id: str
    new_task: TaskRead
    message: str


@router.post(
    "/{task_id}/retry",
    response_model=AdminTaskRetryResponse,
    dependencies=[_ADMIN_DEP],
)
async def retry_task_admin(
    task_id: UUID,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> AdminTaskRetryResponse:
    """Clone an existing task and run it again via :class:`TaskManager`.

    The new task shares the name/type/description/input of the original
    but gets a fresh status and timestamps. The original row is left
    untouched so its audit history stays intact.
    """
    from leagent.services.task_manager import get_task_manager

    async with db.session() as session:
        original = await load_entity_by_id(session, Task, task_id, parent_table="tasks")
        if not original:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        try:
            mgr = get_task_manager()
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"TaskManager unavailable: {exc}",
            ) from exc

        input_data: Optional[dict[str, Any]] = None
        try:
            import json

            if original.input_data:
                raw = json.loads(original.input_data)
                if isinstance(raw, dict):
                    input_data = raw
        except Exception:  # noqa: BLE001
            input_data = None

        priority_value = (
            original.priority.value
            if hasattr(original.priority, "value")
            else str(original.priority or "normal")
        )
        clone = await mgr.create_task(
            session,
            name=f"retry:{original.name}",
            task_type=original.task_type,
            description=original.description or "",
            user_id=original.user_id,
            session_id=original.session_id,
            input_data=input_data,
            priority=priority_value,
            timeout_seconds=int(original.timeout_seconds)
            if original.timeout_seconds
            else 300,
        )
        clone.flow_id = original.flow_id
        session.add(clone)
        await session.flush()

        try:
            await mgr.start_task(session, clone, params=input_data or {})
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Retry failed to start: {exc}",
            ) from exc

        await session.commit()
        await session.refresh(clone)

        return AdminTaskRetryResponse(
            original_task_id=str(task_id),
            new_task=TaskRead.model_validate(clone),
            message="Retry started",
        )
