"""``project_multiedit`` — batch str_replace edits on one project file."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.project.fs import (
    StrReplaceError,
    perform_str_replace,
    resolve_in_project,
    select_project_root,
)

logger = structlog.get_logger(__name__)


class ProjectMultieditTool(BaseTool):
    """Apply several old/new replacements to one project file in one call."""

    name = "project_multiedit"
    description = (
        "Apply multiple `old_string` → `new_string` edits to a single "
        "project file in order. Each edit must match uniquely unless "
        "`replace_all` is set on that edit. Returns per-edit diffs."
    )
    category = ToolCategory.CODE
    aliases = ["multiedit"]
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "block"
    max_result_size_chars = 96_000
    timeout_sec = 60

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Project-relative file path.",
                },
                "edits": {
                    "type": "array",
                    "description": "Ordered list of replacements to apply.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_string": {"type": "string"},
                            "new_string": {"type": "string"},
                            "replace_all": {"type": "boolean", "default": False},
                        },
                        "required": ["old_string", "new_string"],
                    },
                    "minItems": 1,
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional override of the active project root.",
                },
            },
            "required": ["path", "edits"],
            "additionalProperties": False,
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        root = select_project_root(context, explicit=params.get("project_path"))
        resolved = resolve_in_project(root, params["path"], must_exist=True)
        edits = params.get("edits") or []
        if not isinstance(edits, list) or not edits:
            raise ValueError("'edits' must be a non-empty array")

        applied: list[dict[str, Any]] = []
        total_replacements = 0

        for idx, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return {
                    "error": f"Edit at index {idx} must be an object",
                    "path": resolved.rel_path,
                    "applied": applied,
                }
            old_string = edit.get("old_string")
            new_string = edit.get("new_string")
            if not isinstance(old_string, str) or not isinstance(new_string, str):
                return {
                    "error": f"Edit at index {idx} needs old_string and new_string",
                    "path": resolved.rel_path,
                    "applied": applied,
                }
            try:
                result = perform_str_replace(
                    resolved.abs_path,
                    resolved.rel_path,
                    old_string=old_string,
                    new_string=new_string,
                    replace_all=bool(edit.get("replace_all") or False),
                )
            except StrReplaceError as exc:
                payload: dict[str, Any] = {
                    "error": str(exc),
                    "path": resolved.rel_path,
                    "failed_at_index": idx,
                    "applied": applied,
                }
                if exc.patch_hint is not None:
                    payload["patch_hint"] = exc.patch_hint
                return payload

            total_replacements += result.replacements
            applied.append(
                {
                    "index": idx,
                    "replacements": result.replacements,
                    "new_size": result.new_size,
                    "diff": result.diff,
                }
            )

        logger.info(
            "project_multiedit",
            path=resolved.rel_path,
            edits=len(applied),
            replacements=total_replacements,
        )
        from leagent.code.pipeline import record_operation

        record_operation(
            context,
            tool="project_multiedit",
            kind="file_edit",
            path=resolved.rel_path,
            summary=f"{len(applied)} edit(s), {total_replacements} replacement(s)",
        )
        return {
            "path": resolved.rel_path,
            "edits_applied": len(applied),
            "replacements": total_replacements,
            "applied": applied,
        }
