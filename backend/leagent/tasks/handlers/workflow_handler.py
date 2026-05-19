"""``TaskHandler`` that runs a workflow via :class:`WorkflowService`."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.services.database.models.task import TaskContext, TaskType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from leagent.services.service_manager import ServiceManager

logger = logging.getLogger(__name__)


class WorkflowTaskHandler:
    """Execute a registered workflow and capture its result."""

    name = "workflow_task_handler"
    task_type: TaskType = TaskType.WORKFLOW

    def __init__(self, *, service_manager: "ServiceManager") -> None:
        self._sm = service_manager

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: "AsyncSession",
    ) -> dict[str, Any]:
        wf_service = getattr(self._sm, "workflow_service", None)
        if wf_service is None:
            raise RuntimeError("WorkflowService unavailable")

        flow_id_raw = (
            params.get("flow_id")
            or params.get("workflow_id")
            or params.get("target_id")
        )
        if not flow_id_raw:
            raise ValueError(
                "Workflow task requires 'flow_id' (or 'workflow_id') in input_data"
            )
        flow_id = UUID(str(flow_id_raw))

        user_id_raw = params.get("user_id")
        user_id = UUID(str(user_id_raw)) if user_id_raw else UUID(int=0)
        inputs = params.get("inputs") or params.get("payload") or {}

        task_ctx.append_output(
            json.dumps(
                {
                    "event": "workflow_run_start",
                    "flow_id": str(flow_id),
                    "inputs_keys": list(inputs.keys()) if isinstance(inputs, dict) else None,
                }
            )
            + "\n"
        )

        result = await wf_service.run(
            flow_id=flow_id,
            user_id=user_id,
            inputs=inputs if isinstance(inputs, dict) else {},
            trigger_type=params.get("trigger_type", "task"),
        )

        # ``WorkflowResult`` is either dataclass-like or plain dict; stringify
        # as JSON for log output and return a structured summary.
        summary = _summarise_result(result)
        task_ctx.append_output(json.dumps({"event": "workflow_run_done", **summary}, default=str) + "\n")
        return summary

    async def kill(self, task_id: str, session: "AsyncSession") -> None:
        return None


def _summarise_result(result: Any) -> dict[str, Any]:
    if result is None:
        return {"status": "completed"}
    if hasattr(result, "to_dict"):
        try:
            return dict(result.to_dict())
        except Exception:
            pass
    if isinstance(result, dict):
        return result
    return {"result": str(result)}
