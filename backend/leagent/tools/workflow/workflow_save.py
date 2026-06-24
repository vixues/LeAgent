"""``workflow_save`` — persist an agent-authored workflow graph as a Flow row.

Closes the agent production loop: the agent designs a DAG (the same
``flow_data`` JSON shape used by ``chat_workflow_embed_emit`` and the Flow
editor), saves it here to obtain a durable ``flow_id``, then drives it with
``workflow_run`` / ``workflow_status``. The graph is validated against the
canonical workflow document (engine schema) before it is stored — invalid
graphs never reach the database.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from leagent.chat_workflow.workflow_embed import (
    WorkflowEmbedValidationError,
    validate_workflow_embed,
)
from leagent.tools.base import ToolCategory, ToolContext, ToolResult
from leagent.tools.workflow._schema_tool import SchemaWorkflowTool
from leagent.workflow.nodes import get_registry

logger = structlog.get_logger(__name__)


class WorkflowSaveTool(SchemaWorkflowTool):
    name = "workflow_save"
    description = (
        "Persist a workflow graph as a reusable Flow and return its flow_id. flow_data "
        "uses the SAME JSON shape as chat_workflow_embed_emit / the Flow editor (nodes "
        "dict, control.start/end, optional ui) and is validated by the engine before "
        "saving. Drive it with workflow_run, then workflow_status — the "
        "design -> run -> evaluate loop. Save only when a graph should be kept/reused; "
        "for one-off runs prefer chat_workflow_embed_emit."
    )
    category = ToolCategory.WORKFLOW
    is_concurrency_safe = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Human-readable workflow name"},
            "flow_data": {
                "type": "object",
                "description": "Canonical workflow document (nodes, control, optional ui).",
            },
            "description": {"type": "string", "description": "Optional description"},
            "flow_id": {
                "type": "string",
                "description": "Optional UUID of an existing Flow to update in place.",
            },
            "publish": {
                "type": "boolean",
                "description": "Save as published (runnable) rather than draft. Default true.",
                "default": True,
            },
        },
        "required": ["name", "flow_data"],
    }

    async def _execute(self, context: ToolContext, **kwargs: Any) -> ToolResult:
        from uuid import UUID

        from leagent.tools.workflow import workflow_error_result

        raw_fd = kwargs.get("flow_data")
        if not isinstance(raw_fd, dict):
            return ToolResult(success=False, error="flow_data must be an object")

        try:
            doc, digest = validate_workflow_embed(raw_fd, node_registry=get_registry())
        except WorkflowEmbedValidationError as exc:
            return ToolResult(success=False, error=f"Invalid workflow graph: {exc}")

        canonical = doc.to_dict()
        ui = raw_fd.get("ui")
        if isinstance(ui, dict):
            canonical["ui"] = ui

        try:
            from leagent.db.models.flow import Flow, FlowStatus, FlowType
            from leagent.services.auth.service import LOCAL_USER_ID
            from leagent.services.service_manager import get_service_manager

            sm = get_service_manager()
            if sm.db is None:
                return ToolResult(success=False, error="Database not available")

            user_id = LOCAL_USER_ID
            if context and getattr(context, "user_id", None):
                user_id = UUID(str(context.user_id))

            name = str(kwargs.get("name") or doc.name or "Untitled Workflow")
            description = str(kwargs.get("description") or doc.description or "")
            status = (
                FlowStatus.PUBLISHED if kwargs.get("publish", True) else FlowStatus.DRAFT
            )
            data_json = json.dumps(canonical)

            existing_id = kwargs.get("flow_id")
            async with sm.db.session() as session:
                flow: Flow | None = None
                if existing_id:
                    flow = await session.get(Flow, UUID(str(existing_id)))
                if flow is not None:
                    flow.name = name
                    flow.description = description
                    flow.status = status
                    flow.data = data_json
                    session.add(flow)
                else:
                    flow = Flow(
                        name=name,
                        description=description,
                        status=status,
                        flow_type=FlowType.WORKFLOW,
                        data=data_json,
                        user_id=user_id,
                    )
                    session.add(flow)
                await session.flush()
                await session.refresh(flow)
                flow_id = str(flow.id)
                node_count = len(canonical.get("nodes", {}) or {})

            logger.info(
                "workflow_saved", flow_id=flow_id, node_count=node_count, digest=digest,
            )
            return ToolResult(
                success=True,
                data={
                    "flow_id": flow_id,
                    "name": name,
                    "digest": digest,
                    "node_count": node_count,
                    "status": status.value,
                },
            )
        except Exception as exc:  # noqa: BLE001
            return workflow_error_result("save", exc)
