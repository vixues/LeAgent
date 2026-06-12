"""Planning mode tools for the agent.

Implements the reference pattern:
- EnterPlanModeTool  -- switches agent to read-only planning mode
- ExitPlanModeTool   -- exits planning, optionally switches to auto-execute
- TodoWriteTool      -- creates/updates structured task lists within a session
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class EnterPlanModeTool(BaseTool):
    """Switch the agent to planning (read-only) mode.

    In plan mode the agent only creates plans and does not execute tools
    that have side effects.
    """

    name = "enter_plan_mode"
    description = (
        "Enter planning mode. In this mode you will create a step-by-step plan "
        "without immediately executing any actions. Use this for complex tasks "
        "that require upfront analysis."
    )
    category = ToolCategory.UTIL
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["plan", "start_plan"]
    search_hint = "plan mode enter planning analysis"
    interrupt_behavior = "cancel"
    max_result_size_chars = 10_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Entering plan mode"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why planning mode is being entered",
                }
            },
            "required": [],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        reason = params.get("reason", "Complex task requires upfront planning")
        context.extra["plan_mode"] = True
        logger.info("plan_mode_entered", session=context.session_id, reason=reason)
        return {
            "status": "plan_mode_active",
            "message": (
                "Planning mode activated. Create your plan using todo_write, "
                "then call exit_plan_mode to begin execution."
            ),
            "reason": reason,
        }


class ExitPlanModeTool(BaseTool):
    """Exit planning mode and optionally start executing the plan."""

    name = "exit_plan_mode"
    description = (
        "Exit planning mode and return to normal execution. "
        "Optionally start executing the created plan immediately."
    )
    category = ToolCategory.UTIL
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["end_plan", "finish_plan"]
    search_hint = "plan mode exit finish execute"
    interrupt_behavior = "cancel"
    max_result_size_chars = 10_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Exiting plan mode"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "execute_plan": {
                    "type": "boolean",
                    "description": "Whether to start executing the plan immediately",
                    "default": True,
                }
            },
            "required": [],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        execute = params.get("execute_plan", True)
        context.extra.pop("plan_mode", None)
        logger.info("plan_mode_exited", session=context.session_id, execute=execute)
        return {
            "status": "plan_mode_inactive",
            "execute_plan": execute,
            "message": "Planning mode deactivated. Proceeding to execute." if execute
                       else "Planning mode deactivated.",
        }


class TodoWriteTool(BaseTool):
    """Create or update a structured task list in the current session.

    The task list is persisted in the session's context variables and can
    be retrieved via the todo_read tool.
    """

    name = "todo_write"
    description = (
        "Create or update a structured task list. Use this to track multi-step "
        "work. Each todo has an id, content, and status "
        "(pending/in_progress/completed/cancelled)."
    )
    category = ToolCategory.UTIL
    is_read_only = False
    is_concurrency_safe = False
    aliases = ["todo", "create_todo", "todo_create", "update_todo"]
    search_hint = "todo task list create update status track progress"
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Updating task list"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "Array of todo items to create or update",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                            },
                        },
                        "required": ["id", "content", "status"],
                    },
                },
                "merge": {
                    "type": "boolean",
                    "description": "If true, merge with existing todos; otherwise replace",
                    "default": False,
                },
            },
            "required": ["todos"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        incoming = params["todos"]
        merge = params.get("merge", False)

        existing: list[dict[str, Any]] = context.extra.get("todos", [])

        if merge and existing:
            existing_map = {t["id"]: t for t in existing}
            for item in incoming:
                existing_map[item["id"]] = item
            updated = list(existing_map.values())
        else:
            updated = list(incoming)

        context.extra["todos"] = updated

        logger.info(
            "todos_updated",
            session=context.session_id,
            count=len(updated),
            merge=merge,
        )

        return {
            "todos": updated,
            "count": len(updated),
            "pending": sum(1 for t in updated if t["status"] == "pending"),
            "in_progress": sum(1 for t in updated if t["status"] == "in_progress"),
            "completed": sum(1 for t in updated if t["status"] == "completed"),
        }


class TodoReadTool(BaseTool):
    """Read the current task list from the session."""

    name = "todo_read"
    description = "Read the current task list for this session."
    category = ToolCategory.UTIL
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["read_todos", "list_todos"]
    search_hint = "todo task list read view progress"
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Reading task list"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "pending", "in_progress", "completed", "cancelled"],
                    "default": "all",
                }
            },
            "required": [],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        todos: list[dict[str, Any]] = context.extra.get("todos", [])
        status_filter = params.get("status_filter", "all")

        if status_filter != "all":
            todos = [t for t in todos if t["status"] == status_filter]

        return {
            "todos": todos,
            "count": len(todos),
        }
