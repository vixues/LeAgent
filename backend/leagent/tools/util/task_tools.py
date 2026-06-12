"""Task CRUD tools for the agent.

Provides tools to create, read, update, kill, and list tasks,
mirroring the reference Task.ts / tasks.ts patterns with:
- Prefixed task ID generation
- Terminal-state guards
- Output file streaming
- Kill via TaskManager abort controller
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class TaskCreateTool(BaseTool):
    """Create a new background task via the TaskManager."""

    name = "task_create"
    description = (
        "Create a new background task. The task will be queued and executed "
        "asynchronously. Returns the task ID for later status checks."
    )
    category = ToolCategory.UTIL
    is_read_only = False
    is_concurrency_safe = False
    aliases = ["create_task", "new_task"]
    search_hint = "task create new background async queue"
    interrupt_behavior = "block"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Creating task"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the task",
                },
                "task_type": {
                    "type": "string",
                    "enum": ["agent", "shell", "workflow", "tool", "batch", "dream"],
                    "default": "agent",
                    "description": "Type of task to create",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of what the task should do",
                },
                "input_data": {
                    "type": "object",
                    "description": "Input parameters for the task",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "urgent"],
                    "default": "normal",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "default": 300,
                    "minimum": 1,
                    "maximum": 86400,
                    "description": "Maximum execution time in seconds",
                },
            },
            "required": ["name"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            from leagent.db import get_database_service
            from leagent.db.models import TaskType
            from leagent.services.task_manager import get_task_manager

            task_type_map = {
                "agent": TaskType.AGENT,
                "shell": TaskType.SHELL,
                "workflow": TaskType.WORKFLOW,
                "tool": TaskType.TOOL,
                "batch": TaskType.BATCH,
                "dream": TaskType.DREAM,
            }

            db = get_database_service()
            mgr = get_task_manager()

            async with db.session() as session:
                task = await mgr.create_task(
                    session,
                    name=params["name"],
                    task_type=task_type_map.get(params.get("task_type", "agent"), TaskType.AGENT),
                    description=params.get("description", ""),
                    user_id=UUID(context.user_id) if context.user_id else None,
                    session_id=UUID(context.session_id) if context.session_id else None,
                    input_data=params.get("input_data"),
                    priority=params.get("priority", "normal"),
                    timeout_seconds=params.get("timeout_seconds", 300),
                )

                logger.info("task_created", task_id=str(task.id), name=task.name)
                return {
                    "task_id": str(task.id),
                    "name": task.name,
                    "status": task.status.value,
                    "task_type": task.task_type.value,
                    "output_file": task.output_file,
                }
        except Exception as e:
            logger.error("task_create_failed", error=str(e))
            return {"error": str(e)}


class TaskGetTool(BaseTool):
    """Get the status and details of a task by ID."""

    name = "task_get"
    description = "Get the status and details of a task by its ID."
    category = ToolCategory.UTIL
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["get_task", "task_status"]
    search_hint = "task get status details progress"
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Getting task status"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "UUID of the task to retrieve",
                }
            },
            "required": ["task_id"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            from leagent.db import get_database_service
            from leagent.db.models import Task, is_terminal_task_status
            from leagent.services.task_manager import get_task_manager

            db = get_database_service()
            mgr = get_task_manager()
            task_id = UUID(params["task_id"])

            async with db.session() as session:
                task = await session.get(Task, task_id)
                if not task:
                    return {"error": f"Task {task_id} not found"}

                return {
                    "task_id": str(task.id),
                    "name": task.name,
                    "status": task.status.value,
                    "task_type": task.task_type.value,
                    "description": task.description,
                    "progress": task.progress,
                    "progress_message": task.progress_message,
                    "created_at": str(task.created_at),
                    "started_at": str(task.started_at) if task.started_at else None,
                    "completed_at": str(task.completed_at) if task.completed_at else None,
                    "duration_ms": task.duration_ms,
                    "error": task.error,
                    "output_file": task.output_file,
                    "is_terminal": is_terminal_task_status(task.status),
                    "is_running": mgr.is_running(str(task.id)),
                    "parent_id": str(task.parent_id) if task.parent_id else None,
                }
        except Exception as e:
            return {"error": str(e)}


class TaskListTool(BaseTool):
    """List tasks for the current user/session."""

    name = "task_list"
    description = "List tasks with optional status/type filters."
    category = ToolCategory.UTIL
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["list_tasks", "show_tasks"]
    search_hint = "task list show filter status type"
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Listing tasks"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "queued", "running", "completed", "failed", "cancelled", "killed", "timeout"],
                    "description": "Filter by task status",
                },
                "task_type": {
                    "type": "string",
                    "enum": ["agent", "shell", "workflow", "tool", "cron", "batch"],
                    "description": "Filter by task type",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
                "include_terminal": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include tasks in terminal states (completed/failed/killed)",
                },
            },
            "required": [],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            from sqlmodel import select
            from leagent.db import get_database_service
            from leagent.db.models import Task, TaskStatus, TaskType, is_terminal_task_status
            from leagent.services.task_manager import get_task_manager

            db = get_database_service()
            mgr = get_task_manager()
            limit = params.get("limit", 10)
            status_filter = params.get("status")
            type_filter = params.get("task_type")
            include_terminal = params.get("include_terminal", True)

            async with db.session() as session:
                query = select(Task)
                if context.user_id:
                    query = query.where(Task.user_id == UUID(context.user_id))
                if status_filter:
                    query = query.where(Task.status == TaskStatus(status_filter))
                if type_filter:
                    query = query.where(Task.task_type == TaskType(type_filter))
                query = query.limit(limit)

                result = await session.exec(query)
                tasks = result.all()

                if not include_terminal:
                    tasks = [t for t in tasks if not is_terminal_task_status(t.status)]

                return {
                    "tasks": [
                        {
                            "task_id": str(t.id),
                            "name": t.name,
                            "status": t.status.value,
                            "task_type": t.task_type.value,
                            "progress": t.progress,
                            "is_terminal": is_terminal_task_status(t.status),
                            "is_running": mgr.is_running(str(t.id)),
                            "created_at": str(t.created_at),
                        }
                        for t in tasks
                    ],
                    "count": len(tasks),
                    "active_count": mgr.active_task_count,
                }
        except Exception as e:
            return {"error": str(e)}


class TaskUpdateTool(BaseTool):
    """Update a task's status or metadata."""

    name = "task_update"
    description = "Update a task's status, progress, or output."
    category = ToolCategory.UTIL
    is_read_only = False
    is_concurrency_safe = False
    aliases = ["update_task"]
    search_hint = "task update status progress output"
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Updating task"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "queued", "running", "completed", "failed", "cancelled", "killed", "timeout"],
                },
                "progress": {"type": "number", "minimum": 0, "maximum": 100},
                "progress_message": {"type": "string"},
                "output_data": {"type": "object"},
                "error_message": {"type": "string"},
            },
            "required": ["task_id"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            from leagent.db import get_database_service
            from leagent.db.models import Task, TaskStatus, is_terminal_task_status

            db = get_database_service()
            task_id = UUID(params["task_id"])

            async with db.session() as session:
                task = await session.get(Task, task_id)
                if not task:
                    return {"error": f"Task {task_id} not found"}

                if is_terminal_task_status(task.status):
                    return {
                        "error": f"Cannot update task in terminal state: {task.status.value}",
                        "task_id": str(task.id),
                        "status": task.status.value,
                    }

                if "status" in params:
                    task.status = TaskStatus(params["status"])
                if "progress" in params:
                    task.progress = int(params["progress"])
                if "progress_message" in params:
                    task.progress_message = params["progress_message"]
                if "output_data" in params:
                    task.output_data = json.dumps(params["output_data"])
                if "error_message" in params:
                    task.error = params["error_message"]

                session.add(task)
                await session.flush()

                return {
                    "task_id": str(task.id),
                    "status": task.status.value,
                    "progress": task.progress,
                    "updated": True,
                }
        except Exception as e:
            return {"error": str(e)}


class TaskKillTool(BaseTool):
    """Kill a running task (mirrors reference Task.kill)."""

    name = "task_kill"
    description = (
        "Kill a running task by its ID. Sends abort signal and transitions "
        "the task to 'killed' status. Only works on non-terminal tasks."
    )
    category = ToolCategory.UTIL
    is_read_only = False
    is_concurrency_safe = False
    is_destructive = True
    aliases = ["kill_task", "stop_task", "abort_task"]
    search_hint = "task kill stop abort cancel terminate running"
    interrupt_behavior = "block"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Killing task"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "UUID of the task to kill",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            from leagent.db import get_database_service
            from leagent.services.task_manager import get_task_manager

            db = get_database_service()
            mgr = get_task_manager()

            async with db.session() as session:
                killed = await mgr.kill_task(session, params["task_id"])

                return {
                    "task_id": params["task_id"],
                    "killed": killed,
                    "message": "Task killed successfully" if killed else "Task was not running or already terminal",
                }
        except Exception as e:
            logger.error("task_kill_failed", task_id=params.get("task_id"), error=str(e))
            return {"error": str(e)}


class TaskOutputTool(BaseTool):
    """Read streaming output from a task's log file."""

    name = "task_output"
    description = (
        "Read the output/log of a task starting from a byte offset. "
        "Useful for streaming live task output."
    )
    category = ToolCategory.UTIL
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["read_task_output", "task_log", "task_stream"]
    search_hint = "task output log stream read live"
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Reading task output"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "UUID of the task",
                },
                "offset": {
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Byte offset to start reading from",
                },
            },
            "required": ["task_id"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            from leagent.db import get_database_service
            from leagent.db.models import Task, is_terminal_task_status
            from leagent.services.task_manager import get_task_manager

            db = get_database_service()
            mgr = get_task_manager()
            offset = params.get("offset", 0)

            output = mgr.read_output(params["task_id"], offset=offset)

            async with db.session() as session:
                task = await session.get(Task, UUID(params["task_id"]))
                status = task.status.value if task else "unknown"
                is_done = is_terminal_task_status(task.status) if task else True

            return {
                "task_id": params["task_id"],
                "output": output,
                "bytes_read": len(output.encode("utf-8")),
                "next_offset": offset + len(output.encode("utf-8")),
                "status": status,
                "is_done": is_done,
            }
        except Exception as e:
            return {"error": str(e)}
