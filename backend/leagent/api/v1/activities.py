"""Activity feed API endpoint."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import col, select

from leagent.services.auth import CurrentUserId
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.models import Task, TaskStatus
from leagent.services.database.models.workflow_execution import WorkflowExecution

router = APIRouter()

ActivityType = Literal[
    "task_completed",
    "task_failed",
    "task_started",
    "workflow_paused",
    "warning",
]


class Activity(BaseModel):
    id: str
    type: ActivityType
    title: str
    description: str
    timestamp: str


_STATUS_TO_ACTIVITY: dict[TaskStatus, ActivityType] = {
    TaskStatus.COMPLETED: "task_completed",
    TaskStatus.FAILED: "task_failed",
    TaskStatus.RUNNING: "task_started",
    TaskStatus.CANCELLED: "warning",
    TaskStatus.KILLED: "warning",
    TaskStatus.TIMEOUT: "warning",
}

_WF_STATUS_TO_ACTIVITY: dict[str, ActivityType] = {
    "completed": "task_completed",
    "failed": "task_failed",
    "running": "task_started",
    "paused": "workflow_paused",
    "cancelled": "warning",
}


@router.get("", response_model=list[Activity])
async def get_activities(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    limit: int = Query(default=20, ge=1, le=100),
) -> list[Activity]:
    """Return a feed of recent task and workflow activities for the current user."""
    activities: list[Activity] = []

    async with db.session() as session:
        # Task activities
        task_query = (
            select(Task)
            .where(Task.user_id == user_id)
            .order_by(col(Task.updated_at).desc())
            .limit(limit)
        )
        result = await session.exec(task_query)
        tasks = list(result.all())

        for task in tasks:
            activity_type = _STATUS_TO_ACTIVITY.get(task.status, "warning")

            if task.status == TaskStatus.COMPLETED:
                description = "Task completed successfully"
                if task.duration_ms:
                    ms = task.duration_ms
                    dur = f"{ms}ms" if ms < 1000 else f"{ms / 1000:.1f}s"
                    description = f"Completed in {dur}"
            elif task.status == TaskStatus.FAILED:
                description = task.error or "Task encountered an error"
                if len(description) > 100:
                    description = description[:97] + "..."
            elif task.status == TaskStatus.RUNNING:
                description = f"Progress: {task.progress}%"
            elif task.status in (TaskStatus.CANCELLED, TaskStatus.KILLED):
                description = f"Task was {task.status.value}"
            elif task.status == TaskStatus.TIMEOUT:
                description = "Task exceeded timeout limit"
            else:
                description = f"Status: {task.status.value}"

            timestamp = task.updated_at or task.created_at
            activities.append(
                Activity(
                    id=str(task.id),
                    type=activity_type,
                    title=task.name,
                    description=description,
                    timestamp=timestamp.isoformat() if timestamp else "",
                )
            )

        # Workflow execution activities
        wf_query = (
            select(WorkflowExecution)
            .where(WorkflowExecution.user_id == user_id)
            .order_by(col(WorkflowExecution.updated_at).desc())
            .limit(limit)
        )
        wf_result = await session.exec(wf_query)
        wf_executions = list(wf_result.all())

        for wf in wf_executions:
            activity_type = _WF_STATUS_TO_ACTIVITY.get(wf.status, "warning")

            if wf.status == "completed":
                description = "Workflow completed successfully"
                if wf.duration_ms and wf.duration_ms > 0:
                    ms = wf.duration_ms
                    dur = f"{ms}ms" if ms < 1000 else f"{ms / 1000:.1f}s"
                    description = f"Completed in {dur}"
            elif wf.status == "failed":
                description = wf.error or "Workflow encountered an error"
                if len(description) > 100:
                    description = description[:97] + "..."
            elif wf.status == "running":
                description = f"Running node: {wf.current_node or 'starting'}"
            elif wf.status == "paused":
                description = "Workflow paused"
            elif wf.status == "cancelled":
                description = "Workflow was cancelled"
            else:
                description = f"Status: {wf.status}"

            # Resolve the flow name for a better title
            flow_name = f"Workflow {str(wf.id)[:8]}"
            if wf.flow_id:
                from leagent.services.database.models import Flow

                flow = await session.get(Flow, wf.flow_id)
                if flow:
                    flow_name = flow.name

            timestamp = wf.updated_at or wf.created_at
            activities.append(
                Activity(
                    id=str(wf.id),
                    type=activity_type,
                    title=flow_name,
                    description=description,
                    timestamp=timestamp.isoformat() if timestamp else "",
                )
            )

    # Sort combined activities by timestamp descending and take the limit
    activities.sort(key=lambda a: a.timestamp, reverse=True)
    return activities[:limit]
