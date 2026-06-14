"""``TaskHandler`` that runs a workflow via :class:`WorkflowService`."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.db.models.task import TaskContext, TaskType
from leagent.runtime.execution_factory import begin_execution, end_execution
from leagent.runtime.execution_run import ExecutionScope
from leagent.services.event.manager import EventType

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

        exec_run = begin_execution(
            scope=ExecutionScope.WORKFLOW,
            user_id=str(user_id),
            task_id=str(task_ctx.task_id) if task_ctx.task_id else None,
        )
        event_mgr = getattr(self._sm, "event", None)
        if event_mgr is not None:
            try:
                await event_mgr.emit_task_event(
                    EventType.TASK_STARTED,
                    task_id=str(task_ctx.task_id),
                    data={"run_id": exec_run.run_id, "flow_id": str(flow_id)},
                )
            except Exception:
                pass

        task_ctx.append_output(
            json.dumps(
                {
                    "event": "workflow_run_start",
                    "flow_id": str(flow_id),
                    "run_id": exec_run.run_id,
                    "inputs_keys": list(inputs.keys()) if isinstance(inputs, dict) else None,
                }
            )
            + "\n"
        )

        try:
            result = await wf_service.start(
                flow_id=flow_id,
                user_id=user_id,
                inputs=inputs if isinstance(inputs, dict) else {},
                trigger_type=params.get("trigger_type", "task"),
                extra_data={"parent_run_id": exec_run.run_id, "task_run_id": exec_run.run_id},
            )
            summary = _summarise_result(result)
            summary["run_id"] = exec_run.run_id
            task_ctx.append_output(
                json.dumps({"event": "workflow_run_done", **summary}, default=str) + "\n"
            )
            if event_mgr is not None:
                try:
                    await event_mgr.emit_task_event(
                        EventType.TASK_COMPLETED,
                        task_id=str(task_ctx.task_id),
                        data={"run_id": exec_run.run_id, **summary},
                    )
                except Exception:
                    pass
            return summary
        finally:
            end_execution(exec_run.run_id)

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
