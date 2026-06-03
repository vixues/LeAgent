"""``code_workspace_edit`` — surgical edits inside the session code workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.services.code_execution import WorkspaceManager
from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ToolResult
from leagent.tools.code.execution import (
    CodeExecutionConfig,
    CodeExecutionTool,
    build_default_code_execution_config,
)
from leagent.tools.project._fs import (
    StrReplaceError,
    perform_str_replace,
    resolve_content,
    str_replace_result_dict,
)

logger = structlog.get_logger(__name__)


class CodeWorkspaceEditTool(BaseTool):
    """Replace a substring in a file under the session code-execution workspace."""

    name = "code_workspace_edit"
    description = (
        "Replace `old_string` with `new_string` in a file inside the session "
        "code-execution workspace (same directory as `code_execution`). "
        "Use after a failed run to patch `__last_source__.py` or other "
        "workspace files, then re-run with `code_execution(workspace_file=...)`."
    )
    category = ToolCategory.CODE
    aliases = ["workspace_edit", "sandbox_edit"]
    search_hint = "code workspace sandbox edit str replace patch script fix"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "block"
    max_result_size_chars = 64_000
    timeout_sec = 30

    def __init__(self, *, config: CodeExecutionConfig | None = None) -> None:
        self._config = config if config is not None else build_default_code_execution_config()
        self._workspaces = WorkspaceManager(
            self._config.workspace_root,
            max_workspace_bytes=self._config.max_workspace_bytes,
        )

    def _get_workspace(self, context: ToolContext) -> Any:
        metadata = {
            "user_id": context.user_id or "",
            "session_id": context.session_id or "",
            "task_id": context.task_id or "",
        }
        return self._workspaces.get(
            user_id=context.user_id,
            session_id=context.session_id,
            metadata=metadata,
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Relative path inside the session workspace. "
                        f"Defaults to `{CodeExecutionTool._LAST_SOURCE_NAME}` "
                        "after a failed `code_execution`."
                    ),
                    "default": CodeExecutionTool._LAST_SOURCE_NAME,
                },
                "old_string": {
                    "type": "string",
                    "description": "Exact substring to replace.",
                },
                "old_string_blob_id": {
                    "type": "string",
                    "description": "Blob id for `old_string` from `tool_argument_blob`.",
                },
                "new_string": {
                    "type": "string",
                    "description": "Replacement text (may be empty).",
                },
                "new_string_blob_id": {
                    "type": "string",
                    "description": "Blob id for `new_string` from `tool_argument_blob`.",
                },
                "replace_all": {
                    "type": "boolean",
                    "default": False,
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        path = (params or {}).get("path") or CodeExecutionTool._LAST_SOURCE_NAME
        return f"Editing workspace file {path}"

    def coerce_tool_result(self, raw: Any, *, duration_ms: int, attempt: int) -> ToolResult:
        if isinstance(raw, dict) and raw.get("error"):
            return ToolResult.fail(
                str(raw["error"]),
                duration_ms=duration_ms,
                data=raw,
                attempts=attempt,
            )
        return ToolResult.ok(raw, duration_ms=duration_ms, attempts=attempt)

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        rel_path = str(params.get("path") or CodeExecutionTool._LAST_SOURCE_NAME).strip()
        if not rel_path:
            raise ValueError("'path' must be a non-empty relative path")

        root = self._get_workspace(context).path.resolve()
        target = (root / rel_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"path {rel_path!r} escapes the workspace") from exc
        if not target.is_file():
            raise ValueError(
                f"workspace file {rel_path!r} does not exist. Run `code_execution` "
                "first (failed runs persist `__last_source__.py`)."
            )

        try:
            old_string = await resolve_content(
                params,
                context,
                inline_key="old_string",
                blob_key="old_string_blob_id",
            )
        except ValueError:
            return {
                "error": (
                    "Provide non-empty `old_string` or `old_string_blob_id`."
                ),
                "path": rel_path,
            }

        try:
            new_string = await resolve_content(
                params,
                context,
                inline_key="new_string",
                blob_key="new_string_blob_id",
                allow_empty=True,
            )
        except ValueError as exc:
            return {"error": str(exc), "path": rel_path}

        try:
            result = perform_str_replace(
                target,
                rel_path,
                old_string=old_string,
                new_string=new_string,
                replace_all=bool(params.get("replace_all") or False),
            )
        except StrReplaceError as exc:
            payload: dict[str, Any] = {"error": str(exc), "path": rel_path}
            if exc.patch_hint is not None:
                payload["patch_hint"] = exc.patch_hint
            return payload

        logger.info(
            "code_workspace_edit",
            path=rel_path,
            replacements=result.replacements,
        )
        from leagent.tools.code.pipeline import record_operation

        record_operation(
            context,
            tool="code_workspace_edit",
            kind="workspace_edit",
            path=rel_path,
            summary=f"{result.replacements} replacement(s)",
        )
        out = str_replace_result_dict(result)
        out["workspace"] = str(root)
        return out
