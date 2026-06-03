"""Task management API endpoints.

Upgraded to match reference Task.ts patterns:
- Kill endpoint via TaskManager abort controller
- Output streaming endpoint for live task logs
- Terminal-state guards on mutations
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import col, func, select

from leagent.schema.api import PaginatedResponse
from leagent.services.auth import CurrentUserId
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.sqlite_compat import load_entity_by_id
from leagent.services.database.models import (
    File,
    FileRead,
    Task,
    TaskCreate,
    TaskPriority,
    TaskRead,
    TaskStatus,
    TaskType,
    is_terminal_task_status,
)

router = APIRouter()


class TaskCreateRequest(BaseModel):
    """Request schema for creating a task."""

    name: str = Field(..., min_length=1, max_length=200)
    task_type: TaskType = Field(default=TaskType.AGENT)
    priority: TaskPriority = Field(default=TaskPriority.NORMAL)
    description: Optional[str] = Field(default=None, max_length=2000)
    flow_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    input_data: Optional[dict[str, Any]] = None
    scheduled_at: Optional[datetime] = None
    timeout_seconds: int = Field(default=300, ge=1, le=86400)


class AgentRunRequest(BaseModel):
    """Create a long-running agent task from a chat/coding request."""

    message: str = Field(..., min_length=1)
    session_id: Optional[UUID] = None
    name: str = Field(default="Coding agent run", min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    runtime_profile: str = Field(default="coding_long")
    prompt_variant: str = Field(default="coding_agent")
    project_roots: list[str] = Field(default_factory=list)
    authorized_roots: list[str] = Field(default_factory=list)
    max_turns: Optional[int] = Field(default=None, ge=1)
    max_tool_calls_per_turn: Optional[int] = Field(default=None, ge=1)
    priority: TaskPriority = Field(default=TaskPriority.HIGH)
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=86400)


class AgentRunResponse(BaseModel):
    """Response returned after enqueuing a background agent run."""

    task_id: str
    session_id: str | None
    status: str
    runtime_profile: str
    output_offset: int


class TaskListParams(BaseModel):
    """Query parameters for listing tasks."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Optional[TaskStatus] = None
    task_type: Optional[TaskType] = None
    priority: Optional[TaskPriority] = None
    flow_id: Optional[UUID] = None


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreateRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> TaskRead:
    """Create a new task and start it immediately via :class:`TaskManager`.

    Going through the manager (as opposed to inserting a raw :class:`Task`
    row) makes sure a handler is picked, an output file is wired, and the
    task actually runs. Scheduled tasks (``scheduled_at`` in the future)
    stay ``pending`` for a downstream scheduler to pick up.
    """
    from leagent.services.task_manager import get_task_manager

    try:
        mgr = get_task_manager()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"TaskManager unavailable: {exc}",
        ) from exc

    async with db.session() as session:
        task = await mgr.create_task(
            session,
            name=data.name,
            task_type=data.task_type,
            description=data.description or "",
            user_id=user_id,
            session_id=data.session_id,
            input_data=data.input_data,
            priority=data.priority.value,
            timeout_seconds=data.timeout_seconds,
        )
        task.flow_id = data.flow_id
        task.scheduled_at = data.scheduled_at
        session.add(task)
        await session.flush()

        is_scheduled_future = bool(
            data.scheduled_at and data.scheduled_at > datetime.utcnow()
        )
        if not is_scheduled_future:
            try:
                await mgr.start_task(session, task, params=data.input_data or {})
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Task failed to start: {exc}",
                ) from exc
        else:
            task.status = TaskStatus.QUEUED
            session.add(task)

        await session.flush()
        await session.refresh(task)
        await session.commit()

        return TaskRead.model_validate(task)


@router.post("/agent-runs", response_model=AgentRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_agent_run(
    data: AgentRunRequest,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> AgentRunResponse:
    """Start a long-running coding agent as a background task."""

    from leagent.agent.runtime_profile import resolve_runtime_budget
    from leagent.config.settings import get_settings
    from leagent.services.task_manager import get_task_manager

    try:
        mgr = get_task_manager()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"TaskManager unavailable: {exc}",
        ) from exc

    settings = get_settings()
    budget = resolve_runtime_budget(data.runtime_profile, settings=settings)
    timeout = int(data.timeout_seconds or budget.task_timeout_sec)
    timeout = min(timeout, 86400)

    input_data: dict[str, Any] = {
        "message": data.message,
        "runtime_profile": budget.name,
        "prompt_variant": data.prompt_variant,
        "project_roots": data.project_roots,
        "authorized_roots": data.authorized_roots,
    }
    if data.max_turns is not None:
        input_data["max_turns"] = data.max_turns
    if data.max_tool_calls_per_turn is not None:
        input_data["max_tool_calls_per_turn"] = data.max_tool_calls_per_turn

    async with db.session() as session:
        task = await mgr.create_task(
            session,
            name=data.name,
            task_type=TaskType.AGENT,
            description=data.description or "",
            user_id=user_id,
            session_id=data.session_id,
            input_data=input_data,
            priority=data.priority.value,
            timeout_seconds=timeout,
        )
        await mgr.start_task(session, task, params=input_data)
        await session.flush()
        await session.refresh(task)
        await session.commit()

        return AgentRunResponse(
            task_id=str(task.id),
            session_id=str(task.session_id) if task.session_id else None,
            status=task.status.value,
            runtime_profile=budget.name,
            output_offset=task.output_offset,
        )


@router.get("", response_model=PaginatedResponse[TaskRead])
async def list_tasks(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: Optional[TaskStatus] = Query(default=None),
    task_type: Optional[TaskType] = Query(default=None),
    priority: Optional[TaskPriority] = Query(default=None),
    flow_id: Optional[UUID] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
) -> PaginatedResponse[TaskRead]:
    """List tasks for the current user with pagination and filters.

    Also surfaces workflow executions as virtual task rows (type=workflow)
    so the dashboard task monitor table is never empty after running a flow.
    """
    from leagent.services.database.models.workflow_execution import WorkflowExecution

    # Map workflow execution status strings to TaskStatus
    _WF_STATUS_MAP: dict[str, TaskStatus] = {
        "pending": TaskStatus.PENDING,
        "queued": TaskStatus.QUEUED,
        "running": TaskStatus.RUNNING,
        "completed": TaskStatus.COMPLETED,
        "failed": TaskStatus.FAILED,
        "cancelled": TaskStatus.CANCELLED,
        "paused": TaskStatus.PENDING,
    }

    items: list[TaskRead] = []

    async with db.session() as session:
        # ---- Real tasks ----
        skip_tasks = task_type == TaskType.WORKFLOW
        if not skip_tasks:
            query = select(Task).where(Task.user_id == user_id)
            if status is not None:
                query = query.where(Task.status == status)
            if task_type is not None:
                query = query.where(Task.task_type == task_type)
            if priority is not None:
                query = query.where(Task.priority == priority)
            if flow_id is not None:
                query = query.where(Task.flow_id == flow_id)
            if search:
                query = query.where(Task.name.ilike(f"%{search}%"))

            count_query = select(func.count()).select_from(query.subquery())
            count_result = await session.exec(count_query)
            task_total = count_result.one()

            query = query.order_by(col(Task.created_at).desc())
            query = query.offset((page - 1) * page_size).limit(page_size)
            result = await session.exec(query)
            tasks = list(result.all())
            items.extend(TaskRead.model_validate(t) for t in tasks)
        else:
            task_total = 0

        # ---- Workflow executions (surfaced as virtual task rows) ----
        wf_query = select(WorkflowExecution).where(
            WorkflowExecution.user_id == user_id,
        )
        if status is not None:
            wf_status_str = status.value
            wf_query = wf_query.where(WorkflowExecution.status == wf_status_str)
        if flow_id is not None:
            wf_query = wf_query.where(WorkflowExecution.flow_id == flow_id)

        # Resolve flow names for search / display
        flow_name_cache: dict[UUID, str] = {}

        async def _flow_name(fid: UUID | None) -> str:
            if fid is None:
                return "Workflow"
            if fid in flow_name_cache:
                return flow_name_cache[fid]
            from leagent.services.database.models import Flow

            flow = await session.get(Flow, fid)
            name = flow.name if flow else "Workflow"
            flow_name_cache[fid] = name
            return name

        wf_count_query = select(func.count()).select_from(wf_query.subquery())
        wf_count_result = await session.exec(wf_count_query)
        wf_total = wf_count_result.one()

        remaining = page_size - len(items)
        if remaining > 0:
            # Calculate the correct offset for workflow executions
            wf_offset = max(0, (page - 1) * page_size - task_total)
            wf_query = wf_query.order_by(col(WorkflowExecution.created_at).desc())
            wf_query = wf_query.offset(wf_offset).limit(remaining)
            wf_result = await session.exec(wf_query)
            wf_rows = list(wf_result.all())

            for wf in wf_rows:
                mapped_status = _WF_STATUS_MAP.get(wf.status, TaskStatus.PENDING)
                flow_name = await _flow_name(wf.flow_id)

                if search and search.lower() not in flow_name.lower():
                    continue

                progress = 100 if wf.status == "completed" else (
                    50 if wf.status == "running" else 0
                )
                items.append(
                    TaskRead(
                        id=wf.id,
                        name=flow_name,
                        task_type=TaskType.WORKFLOW,
                        status=mapped_status,
                        priority=TaskPriority.NORMAL,
                        description=wf.error if wf.error else None,
                        user_id=wf.user_id,
                        flow_id=wf.flow_id,
                        session_id=None,
                        progress=progress,
                        progress_message=wf.current_node,
                        started_at=wf.started_at,
                        completed_at=wf.completed_at,
                        duration_ms=wf.duration_ms if wf.duration_ms > 0 else None,
                        error=wf.error,
                        output_file=None,
                        notified=False,
                        parent_id=None,
                        created_at=wf.created_at,
                        updated_at=wf.updated_at,
                    )
                )

        total = task_total + wf_total

        return PaginatedResponse[TaskRead](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
            has_prev=page > 1,
        )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> TaskRead:
    """Get task details by ID."""
    async with db.session() as session:
        task = await load_entity_by_id(session, Task, task_id, parent_table="tasks")

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task",
            )

        return TaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_task(
    task_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> None:
    """Cancel a task. Only non-terminal tasks can be cancelled."""
    from leagent.services.task_manager import get_task_manager

    async with db.session() as session:
        task = await load_entity_by_id(session, Task, task_id, parent_table="tasks")

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task",
            )

        if is_terminal_task_status(task.status):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot cancel task in terminal state: '{task.status.value}'",
            )

        mgr = get_task_manager()
        await mgr.cancel_task(session, str(task_id))


class TaskKillResponse(BaseModel):
    """Response for kill endpoint."""

    task_id: str
    killed: bool
    previous_status: str
    message: str


@router.post("/{task_id}/kill", response_model=TaskKillResponse)
async def kill_task(
    task_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> TaskKillResponse:
    """Kill a running task via its abort controller.

    Unlike cancel (which is a soft status change), kill sends an abort signal
    to the running handler and forcefully terminates the background coroutine.
    """
    from leagent.services.task_manager import get_task_manager

    async with db.session() as session:
        task = await load_entity_by_id(session, Task, task_id, parent_table="tasks")

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task",
            )

        previous_status = task.status.value

        if is_terminal_task_status(task.status):
            return TaskKillResponse(
                task_id=str(task_id),
                killed=False,
                previous_status=previous_status,
                message=f"Task already in terminal state: {previous_status}",
            )

        mgr = get_task_manager()
        killed = await mgr.kill_task(session, str(task_id))

        return TaskKillResponse(
            task_id=str(task_id),
            killed=killed,
            previous_status=previous_status,
            message="Task killed successfully" if killed else "Kill signal sent",
        )


class TaskOutputResponse(BaseModel):
    """Response for output streaming endpoint."""

    task_id: str
    output: str
    bytes_read: int
    next_offset: int
    status: str
    is_done: bool


@router.get("/{task_id}/output", response_model=TaskOutputResponse)
async def get_task_output(
    task_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    offset: int = Query(default=0, ge=0, description="Byte offset to read from"),
) -> TaskOutputResponse:
    """Stream task output from its log file.

    Clients poll this endpoint with increasing offsets to tail the live output.
    When ``is_done`` is true the task has reached a terminal state.
    """
    from leagent.services.task_manager import get_task_manager

    async with db.session() as session:
        task = await load_entity_by_id(session, Task, task_id, parent_table="tasks")

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task",
            )

        mgr = get_task_manager()
        output = mgr.read_output(str(task_id), offset=offset, output_file=task.output_file)
        bytes_read = len(output.encode("utf-8"))

        return TaskOutputResponse(
            task_id=str(task_id),
            output=output,
            bytes_read=bytes_read,
            next_offset=offset + bytes_read,
            status=task.status.value,
            is_done=is_terminal_task_status(task.status),
        )


@router.get("/{task_id}/files", response_model=list[FileRead])
async def get_task_files(
    task_id: UUID,
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> list[FileRead]:
    """Get output files for a task."""
    async with db.session() as session:
        task = await load_entity_by_id(session, Task, task_id, parent_table="tasks")

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Task not found",
            )

        if task.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this task",
            )

        if not task.output_data:
            return []

        try:
            output = json.loads(task.output_data)
            file_ids = output.get("files", [])
        except json.JSONDecodeError:
            return []

        if not file_ids:
            return []

        query = select(File).where(File.id.in_(file_ids))
        result = await session.exec(query)
        files = list(result.all())

        return [FileRead.model_validate(f) for f in files]
