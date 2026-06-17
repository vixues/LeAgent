"""Workflow CRUD tools — list, run, status, cancel, pause, resume."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from leagent.tools.base import ToolCategory, ToolContext, ToolResult
from leagent.tools.workflow._schema_tool import SchemaWorkflowTool

logger = structlog.get_logger(__name__)


class WorkflowListTool(SchemaWorkflowTool):
    name = "workflow_list"
    description = (
        "List available workflows (flows) in the system. "
        "Returns name, id, status, description and last run time."
    )
    category = ToolCategory.WORKFLOW
    is_concurrency_safe = True
    is_read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "flow_type": {
                "type": "string",
                "enum": ["agent", "workflow", "chat", "tool"],
                "description": "Filter by flow type",
            },
            "status": {
                "type": "string",
                "enum": ["draft", "published", "archived"],
                "description": "Filter by flow status",
            },
            "limit": {"type": "integer", "default": 20},
        },
    }

    async def _execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        from sqlmodel import select

        from leagent.db.models.flow import Flow
        from leagent.tools.workflow import get_workflow_service, workflow_error_result

        try:
            from leagent.services.service_manager import get_service_manager

            sm = get_service_manager()
            if sm.db is None:
                return ToolResult(success=False, error="Database not available")

            async with sm.db.session() as session:
                q = select(Flow).where(Flow.is_deleted == False)  # noqa: E712
                if kwargs.get("flow_type"):
                    q = q.where(Flow.flow_type == kwargs["flow_type"])
                if kwargs.get("status"):
                    q = q.where(Flow.status == kwargs["status"])
                q = q.limit(kwargs.get("limit", 20))
                result = await session.exec(q)
                flows = result.all()

            return ToolResult(
                success=True,
                data=[
                    {
                        "id": str(f.id),
                        "name": f.name,
                        "description": f.description,
                        "flow_type": f.flow_type.value,
                        "status": f.status.value,
                        "run_count": f.run_count,
                        "last_run_at": f.last_run_at.isoformat() if f.last_run_at else None,
                    }
                    for f in flows
                ],
            )
        except Exception as exc:
            return workflow_error_result("list", exc)


class WorkflowRunTool(SchemaWorkflowTool):
    name = "workflow_run"
    description = (
        "Trigger a workflow execution by flow ID or name. "
        "Returns an execution ID that can be used to track progress."
    )
    is_concurrency_safe = False
    category = ToolCategory.WORKFLOW
    parameters_schema = {
        "type": "object",
        "properties": {
            "flow_id": {"type": "string", "description": "UUID of the flow to run"},
            "inputs": {
                "type": "object",
                "description": "Input parameters for the workflow",
                "default": {},
            },
        },
        "required": ["flow_id"],
    }

    async def _execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        from leagent.tools.workflow import get_workflow_service, workflow_error_result

        try:
            svc = get_workflow_service()
            flow_id = UUID(kwargs["flow_id"])

            from leagent.services.auth.service import LOCAL_USER_ID

            user_id = None
            if context and hasattr(context, "user_id") and context.user_id:
                user_id = UUID(str(context.user_id))
            else:
                user_id = LOCAL_USER_ID

            result = await svc.start(
                flow_id=flow_id,
                user_id=user_id,
                inputs=kwargs.get("inputs", {}),
                trigger_type="agent",
            )

            return ToolResult(
                success=result.status.value in ("completed",),
                data={
                    "execution_id": str(result.state_id),
                    "status": result.status.value,
                    "outputs": result.outputs,
                    "errors": result.errors,
                    "duration_ms": result.duration_ms,
                },
            )
        except Exception as exc:
            return workflow_error_result("run", exc)


class WorkflowStatusTool(SchemaWorkflowTool):
    name = "workflow_status"
    description = "Get the current status and details of a workflow execution by execution ID."
    category = ToolCategory.WORKFLOW
    is_concurrency_safe = True
    is_read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "execution_id": {
                "type": "string",
                "description": "Execution ID returned by workflow_run",
            }
        },
        "required": ["execution_id"],
    }

    async def _execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        from leagent.tools.workflow import get_workflow_service, workflow_error_result

        try:
            svc = get_workflow_service()
            record = await svc.get_execution(UUID(kwargs["execution_id"]))
            if not record:
                return ToolResult(success=False, error="Execution not found")
            return ToolResult(success=True, data=record)
        except Exception as exc:
            return workflow_error_result("status", exc)


class WorkflowCancelTool(SchemaWorkflowTool):
    name = "workflow_cancel"
    description = "Cancel a running or paused workflow execution."
    category = ToolCategory.WORKFLOW
    is_concurrency_safe = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "execution_id": {"type": "string", "description": "Execution ID to cancel"}
        },
        "required": ["execution_id"],
    }

    async def _execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        from leagent.tools.workflow import get_workflow_service, workflow_error_result

        try:
            svc = get_workflow_service()
            ok = await svc.cancel_execution(UUID(kwargs["execution_id"]))
            if not ok:
                return ToolResult(success=False, error="Execution not found or not cancellable")
            return ToolResult(success=True, data={"execution_id": kwargs["execution_id"], "status": "cancelled"})
        except Exception as exc:
            return workflow_error_result("cancel", exc)


class WorkflowPauseTool(SchemaWorkflowTool):
    name = "workflow_pause"
    description = "Pause a currently running workflow execution."
    category = ToolCategory.WORKFLOW
    is_concurrency_safe = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "execution_id": {"type": "string", "description": "Execution ID to pause"}
        },
        "required": ["execution_id"],
    }

    async def _execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        from leagent.tools.workflow import get_workflow_service, workflow_error_result

        try:
            svc = get_workflow_service()
            ok = await svc.pause_execution(UUID(kwargs["execution_id"]))
            if not ok:
                return ToolResult(success=False, error="Execution not found or not pausable")
            return ToolResult(success=True, data={"execution_id": kwargs["execution_id"], "status": "paused"})
        except Exception as exc:
            return workflow_error_result("pause", exc)


class WorkflowResumeTool(SchemaWorkflowTool):
    name = "workflow_resume"
    description = "Resume a paused workflow execution."
    category = ToolCategory.WORKFLOW
    is_concurrency_safe = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "execution_id": {"type": "string", "description": "Execution ID to resume"},
            "flow_id": {"type": "string", "description": "Flow ID associated with the execution"},
            "resume_data": {
                "type": "object",
                "description": "Optional data to inject on resume (e.g. human review response)",
                "default": {},
            },
        },
        "required": ["execution_id", "flow_id"],
    }

    async def _execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        from leagent.tools.workflow import get_workflow_service, workflow_error_result

        try:
            svc = get_workflow_service()
            result = await svc.resume_execution(
                UUID(kwargs["execution_id"]),
                UUID(kwargs["flow_id"]),
                kwargs.get("resume_data"),
            )
            if not result:
                return ToolResult(success=False, error="Execution not found or not resumable")
            return ToolResult(
                success=True,
                data={"execution_id": kwargs["execution_id"], "status": result.status.value},
            )
        except Exception as exc:
            return workflow_error_result("resume", exc)
