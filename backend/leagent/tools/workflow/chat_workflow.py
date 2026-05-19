"""ChatWorkflowEmitTool — emit a validated chat workflow card."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.chat_workflow.schema import (
    ValidationError,
    chat_workflow_digest,
    parse_chat_workflow_spec,
)
from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ValidationResult
from leagent.tools.registry import get_registry

logger = structlog.get_logger(__name__)


class ChatWorkflowEmitTool(BaseTool):
    """Validate and attach a structured multi-step workflow to the chat turn."""

    name = "chat_workflow_emit"
    description = (
        "Publish a structured workflow card in the chat. Use when the user asks for a "
        "repeatable plan with executable steps. Each step must call a read-only tool "
        "(e.g. date_calculator, json_parser) with JSON arguments; use placeholders "
        "${session_id}, ${user_id}, ${user_input} in string values where needed. "
        "Pass: version (1), title, optional summary, steps[{id, label, optional hint, "
        "action: {kind: 'tool', tool_id, arguments}}]."
    )
    category = ToolCategory.WORKFLOW
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["emit_chat_workflow", "workflow_card"]
    search_hint = "workflow plan steps card playbook checklist execute buttons"
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        t = (params or {}).get("title")
        return f"Publishing workflow: {t}" if isinstance(t, str) else "Publishing workflow"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "version": {"type": "integer", "enum": [1], "default": 1},
                "title": {"type": "string", "description": "Short workflow title"},
                "summary": {"type": "string", "description": "Optional longer summary"},
                "steps": {
                    "type": "array",
                    "description": "Ordered executable steps",
                    "items": {"type": "object"},
                    "minItems": 1,
                },
            },
            "required": ["title", "steps"],
        }

    async def validate_input(self, params: dict[str, Any], context: ToolContext) -> ValidationResult:
        registry = get_registry()
        raw = {
            "version": int(params.get("version", 1)),
            "title": params.get("title", ""),
            "summary": params.get("summary"),
            "steps": params.get("steps") or [],
        }
        try:
            spec = parse_chat_workflow_spec(raw, registry=registry)
        except ValidationError as e:
            return ValidationResult(valid=False, message=str(e))
        context.extra["_chat_workflow_emit_spec"] = spec.model_dump(mode="json")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        dumped = context.extra.get("_chat_workflow_emit_spec")
        registry = get_registry()
        if isinstance(dumped, dict):
            spec = parse_chat_workflow_spec(dumped, registry=registry)
        else:
            raw = {
                "version": int(params.get("version", 1)),
                "title": params.get("title", ""),
                "summary": params.get("summary"),
                "steps": params.get("steps") or [],
            }
            spec = parse_chat_workflow_spec(raw, registry=registry)
        digest = chat_workflow_digest(spec)
        return {
            "success": True,
            "workflow": spec.model_dump(mode="json"),
            "digest": digest,
        }
