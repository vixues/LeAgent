"""Emit a chat message workflow card backed by the same JSON shape as Flow.data."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.chat_workflow.workflow_embed import (
    WorkflowEmbedValidationError,
    validate_workflow_embed,
)
from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ValidationResult
from leagent.workflow.nodes import get_registry

logger = structlog.get_logger(__name__)


class ChatWorkflowEmbedEmitTool(BaseTool):
    """Publish a DAG workflow in chat using Flow-compatible ``flow_data`` JSON."""

    name = "chat_workflow_embed_emit"
    description = (
        "Publish a workflow graph in the chat using the SAME JSON shape as the Flow "
        "editor / Flow.data: top-level keys like nodes (array or dict), edges, optional "
        "ui, control/start/end, id, name. The graph is validated by the workflow engine "
        "(no separate chat-only schema). Use for multi-step DAGs with ToolCallNode, "
        "StartNode, EndNode, etc. Pass: title (short), optional summary, flow_data (object)."
    )
    category = ToolCategory.WORKFLOW
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["emit_chat_workflow_embed", "workflow_embed_card"]
    search_hint = "workflow graph nodes edges flow embed comfy dag"
    interrupt_behavior = "cancel"
    max_result_size_chars = 500_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        t = (params or {}).get("title")
        return f"Publishing embedded workflow: {t}" if isinstance(t, str) else "Publishing embedded workflow"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Card title shown above the graph"},
                "summary": {"type": "string", "description": "Optional longer summary"},
                "flow_data": {
                    "type": "object",
                    "description": "Same structure as Flow.data (nodes, edges, optional ui, …)",
                },
                "flow_id": {
                    "type": "string",
                    "description": "Optional UUID of a saved Flow row for deep-linking",
                },
            },
            "required": ["title", "flow_data"],
        }

    async def validate_input(self, params: dict[str, Any], context: ToolContext) -> ValidationResult:
        raw_fd = params.get("flow_data")
        if not isinstance(raw_fd, dict):
            return ValidationResult(valid=False, message="flow_data must be an object")
        try:
            doc, digest = validate_workflow_embed(raw_fd, node_registry=get_registry())
        except WorkflowEmbedValidationError as e:
            return ValidationResult(valid=False, message=str(e))
        context.extra["_workflow_embed_doc"] = doc
        context.extra["_workflow_embed_digest"] = digest
        context.extra["_workflow_embed_raw"] = raw_fd
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        digest = context.extra.get("_workflow_embed_digest")
        raw_fd = context.extra.get("_workflow_embed_raw")
        if not isinstance(digest, str) or not isinstance(raw_fd, dict):
            raw_fd = params.get("flow_data")
            if not isinstance(raw_fd, dict):
                return {"success": False, "error": "flow_data missing"}
            _doc, digest = validate_workflow_embed(raw_fd, node_registry=get_registry())
        title = params.get("title", "")
        summary = params.get("summary")
        flow_id = params.get("flow_id")
        return {
            "success": True,
            "digest": digest,
            "flow_data": raw_fd,
            "title": title if isinstance(title, str) else "",
            "summary": summary if isinstance(summary, str) else None,
            "flow_id": flow_id if isinstance(flow_id, str) else None,
        }
