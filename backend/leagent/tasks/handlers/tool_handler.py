"""``TaskHandler`` that runs a single tool through :class:`ToolExecutor`."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from leagent.services.database.models.task import TaskContext, TaskType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from leagent.services.service_manager import ServiceManager

logger = logging.getLogger(__name__)


class ToolTaskHandler:
    """Execute a single tool and record its result on the task."""

    name = "tool_task_handler"
    task_type: TaskType = TaskType.TOOL

    def __init__(self, *, service_manager: "ServiceManager | None" = None) -> None:
        self._sm = service_manager

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: "AsyncSession",
    ) -> dict[str, Any]:
        from leagent.tools.executor import ToolExecutor
        from leagent.tools.registry import get_registry

        tool_name = params.get("tool_name") or params.get("name")
        if not tool_name:
            raise ValueError("Tool task requires 'tool_name' in input_data")

        tool_params = params.get("parameters") or params.get("params") or {}
        registry = get_registry()
        executor = ToolExecutor(registry=registry, service_manager=self._sm)

        task_ctx.append_output(
            json.dumps({"event": "tool_call", "tool": tool_name, "params": tool_params}, default=str)
            + "\n"
        )

        result = await executor.execute(
            tool_name=tool_name,
            parameters=tool_params,
            context=None,
        )
        summary = {
            "tool_name": tool_name,
            "success": result.result.success,
            "duration_ms": result.duration_ms,
            "output": result.result.to_dict(),
        }
        task_ctx.append_output(json.dumps({"event": "tool_result", **summary}, default=str) + "\n")

        if not result.result.success:
            raise RuntimeError(
                result.result.to_dict().get("error") or f"Tool {tool_name} failed"
            )
        return summary

    async def kill(self, task_id: str, session: "AsyncSession") -> None:
        return None
