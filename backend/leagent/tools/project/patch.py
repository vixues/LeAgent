"""``project_apply_patch`` — apply a unified diff across one or more files.

For multi-hunk or multi-file edits it is more compact (and far less
error-prone) to send a single unified diff than to issue a sequence of
``project_edit`` calls. This tool consumes the same ``diff -u`` /
``git diff`` format the agent already knows from training data, so the
LLM can author patches naturally.

Limitations (kept deliberate to avoid silent miscompiles):

* No fuzzy / context-tolerant matching. Every ``-`` and context line
  must match the file on disk exactly. When mismatches occur the tool
  refuses the patch instead of pretending it succeeded.
* No rename detection. To move a file, emit a delete + create pair.
* Hunk header line counts are tolerated when wrong, but the body must
  still describe a self-consistent edit.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.project._fs import (
    apply_unified_diff,
    resolve_content,
    select_project_root,
)

logger = structlog.get_logger(__name__)


class ProjectApplyPatchTool(BaseTool):
    """Apply a unified diff to the project files."""

    name = "project_apply_patch"
    description = (
        "Apply a unified diff (the format produced by `git diff` or "
        "`diff -u`) across one or more files in the active project "
        "root. Use for multi-hunk or multi-file edits where issuing "
        "individual `project_edit` calls would be unwieldy. New files "
        "use the `--- /dev/null` convention; deleted files use "
        "`+++ /dev/null`. Context lines must match the file on disk "
        "exactly — re-read the file with `project_read` if a hunk "
        "rejects. Large diffs: stage with `tool_argument_blob` then "
        "`diff_blob_id`."
    )
    category = ToolCategory.CODE
    aliases = ["apply_patch", "code_patch"]
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "block"
    max_result_size_chars = 64_000
    timeout_sec = 60

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": (
                        "Unified diff to apply. Omit when using `diff_blob_id`."
                    ),
                },
                "diff_blob_id": {
                    "type": "string",
                    "description": (
                        "Finalized blob from `tool_argument_blob` containing the "
                        "unified diff text. Consumed on success."
                    ),
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Optional override of the active project root."
                    ),
                },
            },
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Applying patch"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        root = select_project_root(
            context, explicit=params.get("project_path"),
        )
        try:
            diff_text = await resolve_content(
                params, context,
                inline_key="diff", blob_key="diff_blob_id",
            )
        except ValueError as exc:
            return {"error": str(exc)}

        await self._track_artifact(diff_text, context)

        try:
            applied = apply_unified_diff(root, diff_text)
        except (ValueError, FileNotFoundError, PermissionError) as exc:
            return {"error": str(exc)}

        files = [
            {
                "path": pf.rel_path,
                "is_new": pf.is_new,
                "is_deleted": pf.is_deleted,
            }
            for pf in applied
        ]
        logger.info("project_apply_patch", files=len(files))

        from leagent.tools.code.pipeline import record_operation

        paths = [pf.rel_path for pf in applied]
        record_operation(
            context,
            tool="project_apply_patch",
            kind="file_patch",
            path=paths[0] if len(paths) == 1 else None,
            summary=f"{len(files)} file(s) patched",
        )
        return {
            "files": files,
            "count": len(files),
        }

    @staticmethod
    async def _track_artifact(diff_text: str, context: ToolContext) -> None:
        try:
            from leagent.tools.code.pipeline import get_pipeline
            from leagent.tools.code.artifact import ArtifactKind

            pipeline = get_pipeline(context)
            if pipeline is None:
                return
            await pipeline.prepare(
                kind=ArtifactKind.FILE_PATCH,
                source=diff_text,
                language="diff",
                origin_tool="project_apply_patch",
                context=context,
                skip_validation=True,
            )
        except Exception:  # noqa: BLE001
            logger.debug("project_apply_patch_artifact_tracking_error", exc_info=True)
