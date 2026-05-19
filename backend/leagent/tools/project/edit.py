"""``project_edit`` — surgical string replacement.

This is the workhorse the agent reaches for to make any non-trivial
change to an existing file. The contract intentionally mirrors the
Cursor ``StrReplace`` tool because it is the simplest contract that
gives the LLM a way to express "change exactly this string" without
inventing a brittle line-based protocol:

* ``old_string`` must occur **exactly once** in the file (so the agent
  has to add context if there's any ambiguity), unless
* ``replace_all=True`` is passed, in which case every occurrence is
  rewritten.

The tool returns a unified diff and a replacement count so the parent
agent can decide whether the change matches its intent. Edits that
would produce identical content (``old == new``) are rejected up front
to avoid no-op churn.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.project._fs import (
    apply_str_replace,
    resolve_in_project,
    select_project_root,
)

logger = structlog.get_logger(__name__)


class ProjectEditTool(BaseTool):
    """Replace a substring inside a project file (uniqueness-checked)."""

    name = "project_edit"
    description = (
        "Replace `old_string` with `new_string` in a project file. "
        "Fails unless `old_string` occurs exactly once unless "
        "`replace_all=true` is set, so the LLM is forced to add context "
        "for ambiguous matches. Returns a unified diff of the change. "
        "For large hunks, stage with `tool_argument_blob` then pass "
        "`old_string_blob_id` / `new_string_blob_id` instead of inlining "
        "long strings in JSON."
    )
    category = ToolCategory.CODE
    aliases = ["str_replace", "code_edit"]
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "block"
    max_result_size_chars = 64_000
    timeout_sec = 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Project-relative path to edit.",
                },
                "old_string": {
                    "type": "string",
                    "description": (
                        "Exact substring to replace. Omit when using "
                        "`old_string_blob_id`. Whitespace and indentation "
                        "are significant; include enough surrounding context "
                        "to make the match unique."
                    ),
                },
                "old_string_blob_id": {
                    "type": "string",
                    "description": (
                        "Finalized blob from `tool_argument_blob` with the "
                        "`old_string` text. Consumed on success."
                    ),
                },
                "new_string": {
                    "type": "string",
                    "description": (
                        "Replacement substring. May be empty. Omit when using "
                        "`new_string_blob_id`."
                    ),
                },
                "new_string_blob_id": {
                    "type": "string",
                    "description": (
                        "Finalized blob from `tool_argument_blob` with the "
                        "`new_string` text (may be empty). Consumed on success."
                    ),
                },
                "replace_all": {
                    "type": "boolean",
                    "description": (
                        "When true, replace every occurrence. Defaults "
                        "to false so accidental multi-matches are caught."
                    ),
                    "default": False,
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Optional override of the active project root."
                    ),
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        path = (params or {}).get("path")
        return f"Editing {path}" if path else "Editing project file"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        from leagent.tools.util.tool_argument_blob import resolve_blob_text

        root = select_project_root(
            context, explicit=params.get("project_path"),
        )
        resolved = resolve_in_project(root, params["path"], must_exist=True)

        old_blob = params.get("old_string_blob_id")
        if isinstance(old_blob, str) and old_blob.strip():
            try:
                old_string = await resolve_blob_text(context, old_blob)
            except ValueError as exc:
                return {"error": str(exc), "path": resolved.rel_path}
        else:
            raw_old = params.get("old_string")
            old_string = raw_old if isinstance(raw_old, str) else ""

        new_blob = params.get("new_string_blob_id")
        if isinstance(new_blob, str) and new_blob.strip():
            try:
                new_string = await resolve_blob_text(
                    context, new_blob, allow_empty=True,
                )
            except ValueError as exc:
                return {"error": str(exc), "path": resolved.rel_path}
        else:
            raw_new = params.get("new_string")
            new_string = raw_new if isinstance(raw_new, str) else ""

        if not old_string:
            return {
                "error": (
                    "Provide non-empty `old_string` or a finalized "
                    "`old_string_blob_id` (from `tool_argument_blob`)."
                ),
                "path": resolved.rel_path,
            }
        # new_string may be intentionally empty (delete matched region).

        await self._track_artifact(
            new_string, resolved.rel_path, old_string,
            bool(params.get("replace_all") or False), context,
        )

        try:
            result = apply_str_replace(
                resolved.abs_path,
                resolved.rel_path,
                old_string=old_string,
                new_string=new_string,
                replace_all=bool(params.get("replace_all") or False),
            )
        except ValueError as exc:
            return {"error": str(exc), "path": resolved.rel_path}

        logger.info(
            "project_edit",
            path=resolved.rel_path,
            replacements=result.replacements,
        )
        return {
            "path": resolved.rel_path,
            "replacements": result.replacements,
            "new_size": result.new_size,
            "diff": result.diff,
        }

    @staticmethod
    async def _track_artifact(
        new_string: str,
        rel_path: str,
        old_string: str,
        replace_all: bool,
        context: ToolContext,
    ) -> None:
        try:
            from leagent.tools.code.pipeline import get_pipeline
            from leagent.tools.code.artifact import ArtifactKind

            pipeline = get_pipeline(context)
            if pipeline is None:
                return
            await pipeline.prepare(
                kind=ArtifactKind.FILE_EDIT,
                source=new_string,
                language="auto",
                origin_tool="project_edit",
                context=context,
                target_path=rel_path,
                metadata={
                    "old_string_len": len(old_string),
                    "replace_all": replace_all,
                },
            )
        except Exception:  # noqa: BLE001
            logger.debug("project_edit_artifact_tracking_error", exc_info=True)
