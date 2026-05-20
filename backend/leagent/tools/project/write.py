"""``project_write`` — full-file writes inside the active project root.

The coding agent should reach for ``project_edit`` or
``project_apply_patch`` first; ``project_write`` is for the cases where
those don't apply: brand-new files (scaffolding a module), or
intentional whole-file rewrites where a surgical patch would be larger
than the rewrite itself. To stop the LLM from accidentally clobbering
files it never read, the tool refuses to overwrite an existing file
unless ``overwrite=True`` is passed in the same call.

The tool supports ``validate_only=True`` for dry-run syntax checking
without writing to disk. When used, the pipeline still creates a
:class:`~leagent.tools.code.artifact.CodeArtifact`, validates syntax,
and returns diagnostics — but the file is not modified.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.project._fs import (
    resolve_content,
    resolve_in_project,
    select_project_root,
)

logger = structlog.get_logger(__name__)


class ProjectWriteTool(BaseTool):
    """Write a full file inside the project root (creates parents)."""

    name = "project_write"
    description = (
        "Write or overwrite a text file inside the active project root. "
        "Prefer `project_edit` / `project_apply_patch` for changes to "
        "existing files; use this for brand-new files or intentional "
        "whole-file rewrites. Pass `overwrite=true` to replace an "
        "existing file. Pass `validate_only=true` to syntax-check "
        "without writing. For large bodies, use `tool_argument_blob` "
        "then `content_blob_id` instead of inlining `content` in JSON."
    )
    category = ToolCategory.CODE
    aliases = ["write_file", "code_write"]
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "block"
    max_result_size_chars = 128_000
    timeout_sec = 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Project-relative path of the file to write."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Full file contents as UTF-8 without a BOM. Omit when "
                        "using `content_blob_id`."
                    ),
                },
                "content_blob_id": {
                    "type": "string",
                    "description": (
                        "Staged blob from `tool_argument_blob` (create → append → "
                        "finalize). Consumed on success; use instead of huge "
                        "`content` in tool-call JSON."
                    ),
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Optional override of the active project root."
                    ),
                },
                "overwrite": {
                    "type": "boolean",
                    "description": (
                        "When true, replace an existing file. Defaults "
                        "to false to protect against blind overwrites."
                    ),
                    "default": False,
                },
                "create_parents": {
                    "type": "boolean",
                    "description": (
                        "Create missing parent directories. Defaults to "
                        "true so scaffolding works without an extra "
                        "`project_shell mkdir` call."
                    ),
                    "default": True,
                },
                "validate_only": {
                    "type": "boolean",
                    "description": (
                        "When true, run syntax validation on the content "
                        "without writing to disk. Returns diagnostics so "
                        "the LLM can fix issues before committing."
                    ),
                    "default": False,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        path = (params or {}).get("path")
        if (params or {}).get("validate_only"):
            return f"Validating {path}" if path else "Validating project file"
        return f"Writing {path}" if path else "Writing project file"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        root = select_project_root(
            context, explicit=params.get("project_path"),
        )
        resolved = resolve_in_project(root, params["path"], must_exist=False)

        overwrite = bool(params.get("overwrite") or False)
        create_parents = bool(params.get("create_parents", True))
        validate_only = bool(params.get("validate_only") or False)

        try:
            content = await resolve_content(
                params, context,
                inline_key="content", blob_key="content_blob_id",
            )
        except ValueError as exc:
            return {"error": str(exc)}

        artifact = await self._track_artifact(
            content, resolved.rel_path, context,
        )

        if validate_only:
            result: dict[str, Any] = {
                "path": resolved.rel_path,
                "validate_only": True,
                "source_length": len(content),
            }
            if artifact is not None:
                result["artifact_id"] = artifact.artifact_id
                result["syntax_valid"] = artifact.syntax_valid
                result["language"] = artifact.language
                if artifact.diagnostics:
                    result["syntax_diagnostics"] = artifact.diagnostics
            return result

        existed = resolved.abs_path.exists()
        if existed and not overwrite:
            return {
                "error": (
                    f"{resolved.rel_path} already exists. Pass "
                    "`overwrite=true` to replace it, or use `project_edit` "
                    "to make a surgical change."
                ),
                "path": resolved.rel_path,
                "existed": True,
            }

        if create_parents:
            resolved.abs_path.parent.mkdir(parents=True, exist_ok=True)
        elif not resolved.abs_path.parent.exists():
            return {
                "error": (
                    f"Parent directory {resolved.abs_path.parent} does "
                    "not exist. Pass `create_parents=true` or create it "
                    "first."
                ),
                "path": resolved.rel_path,
            }

        encoded = content.encode("utf-8")
        resolved.abs_path.write_bytes(encoded)
        logger.info(
            "project_write",
            path=resolved.rel_path,
            bytes=len(encoded),
            overwrote=existed,
        )
        result = {
            "path": resolved.rel_path,
            "bytes_written": len(encoded),
            "lines": content.count("\n") + (0 if content.endswith("\n") else 1),
            "created": not existed,
        }
        if artifact is not None:
            result["artifact_id"] = artifact.artifact_id
            result["syntax_valid"] = artifact.syntax_valid
            result["language"] = artifact.language
            result["kind"] = artifact.kind.value
            result["source_length"] = len(artifact.source)
            result["target_path"] = artifact.target_path
            if artifact.diagnostics:
                result["syntax_diagnostics"] = artifact.diagnostics

        from leagent.tools.code.pipeline import record_operation

        record_operation(
            context,
            tool="project_write",
            kind="file_write",
            path=resolved.rel_path,
            summary=f"{'created' if not existed else 'overwrote'} ({len(encoded)} bytes)",
            artifact_id=artifact.artifact_id if artifact else None,
        )
        return result

    @staticmethod
    async def _track_artifact(
        content: str, rel_path: str, context: ToolContext,
    ) -> Any:
        """Create a CodeArtifact via the pipeline; returns the artifact or None."""
        try:
            from leagent.tools.code.pipeline import get_pipeline
            from leagent.tools.code.artifact import ArtifactKind

            pipeline = get_pipeline(context)
            if pipeline is None:
                return None
            return await pipeline.prepare(
                kind=ArtifactKind.FILE_WRITE,
                source=content,
                language="auto",
                origin_tool="project_write",
                context=context,
                target_path=rel_path,
            )
        except Exception:  # noqa: BLE001
            logger.debug("project_write_artifact_tracking_error", exc_info=True)
            return None
