"""ask_user: LLM-initiated clarification (schema + fallback execute)."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext, ToolResult

logger = structlog.get_logger(__name__)


class AskUserTool(SyncTool):
    """Present structured questions to the user via the chat UI.

    The query loop intercepts this tool and does not call ``execute`` in
    normal chat flows. If execution is reached (e.g. tests), return a
    clear noop envelope.
    """

    name = "ask_user"
    description = (
        "Ask the user one or more questions with optional fixed choices. "
        "Use this when requirements are ambiguous or you need a decision before continuing. "
        "Call this tool alone in the turn — do not combine with other tools. "
        "Each question needs a stable string id and a prompt; optional choices, "
        "allow_custom (free-text in addition to choices), multi_select, and UI hints: "
        "ui_variant (questionnaire|permission), permission_kind (file_access|tool_run|"
        "mode_change|generic), detail (short subtitle), primary_choice / secondary_choice "
        "(override Allow/Deny labels for permission UI)."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 5
    is_concurrency_safe = False
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Stable id for this question (e.g. q1, stack_choice).",
                            },
                            "prompt": {
                                "type": "string",
                                "description": "Question text shown to the user.",
                            },
                            "choices": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional fixed answers; user picks one or more.",
                            },
                            "allow_custom": {
                                "type": "boolean",
                                "description": "If true, user may type an answer in addition to choices.",
                            },
                            "multi_select": {
                                "type": "boolean",
                                "description": "If true and choices are set, user may select multiple.",
                            },
                            "ui_variant": {
                                "type": "string",
                                "enum": ["questionnaire", "permission"],
                                "description": (
                                    "permission: composer strip with Allow/Deny; "
                                    "questionnaire: full chip UI (default)."
                                ),
                            },
                            "permission_kind": {
                                "type": "string",
                                "enum": ["file_access", "tool_run", "mode_change", "generic"],
                                "description": "Icon/category when ui_variant is permission.",
                            },
                            "detail": {
                                "type": "string",
                                "description": "Subtitle (path, tool name, mode name) for permission UI.",
                            },
                            "primary_choice": {
                                "type": "string",
                                "description": "Override label for the primary (allow) action.",
                            },
                            "secondary_choice": {
                                "type": "string",
                                "description": "Override label for the secondary (deny) action.",
                            },
                        },
                        "required": ["id", "prompt"],
                    },
                    "description": "Questions to show in the chat composer area.",
                },
            },
            "required": ["questions"],
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> Any:
        logger.info("ask_user_execute_fallback", session_id=str(context.session_id))
        return ToolResult.ok(
            {"handled_by": "runtime", "note": "ask_user is normally resolved by the chat UI."},
        )
