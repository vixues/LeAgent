"""``project_read`` — line-numbered read for files inside the project root.

Why a dedicated tool when ``text_processor`` already exists? Because
the coding agent needs three things ``text_processor`` does not give
it for free:

1. **Project-rooted paths.** The agent thinks in terms of relative
   paths like ``src/auth/login.ts``; this tool resolves them against
   ``context.extra['project_roots']`` rather than the upload sandbox.
2. **Line numbers in the output.** Editing tools (``project_edit``,
   ``project_apply_patch``) want exact line references; rendering
   ``LINE_NUM|content`` makes the agent's references unambiguous.
3. **Offset/limit pagination.** Large source files (>2k lines) need
   range reads so the agent doesn't blow its context window.

A single ``project_read`` call returns up to ~2000 lines starting at
``offset``. The result is text rather than JSON because the file's
contents are usually the headline; structured metadata stays compact.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.project.fs import (
    MAX_TEXT_FILE_BYTES,
    format_lines_with_numbers,
    read_text_with_detection,
    resolve_in_project,
    select_project_root,
)

logger = structlog.get_logger(__name__)


class ProjectReadTool(BaseTool):
    """Read a file inside the active project root with line numbers."""

    name = "project_read"
    description = (
        "Read a text file inside the active project root and return its "
        "contents with `LINE_NUMBER|content` rows. Use this whenever you "
        "need to inspect source before editing — line numbers are required "
        "for `project_edit` / `project_apply_patch`. Supports offset+limit "
        "pagination for large files."
    )
    category = ToolCategory.CODE
    aliases = ["read_file", "code_read"]
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    timeout_sec = 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Path to read. Either relative to the project "
                        "root (e.g. `src/auth/login.ts`) or an absolute "
                        "path that already lives inside the root."
                    ),
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Optional override of the active project root. "
                        "Normally inherited from the calling agent."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "description": "1-indexed first line to render.",
                    "minimum": 1,
                    "default": 1,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to render.",
                    "minimum": 1,
                    "maximum": 4000,
                    "default": 2000,
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        path = (params or {}).get("path")
        return f"Reading {path}" if path else "Reading project file"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        root = select_project_root(
            context, explicit=params.get("project_path"),
        )
        resolved = resolve_in_project(
            root, params["path"], must_exist=True,
        )

        size = resolved.abs_path.stat().st_size
        if size > MAX_TEXT_FILE_BYTES:
            return {
                "error": (
                    f"File is too large to read in one shot ({size} bytes; "
                    f"limit {MAX_TEXT_FILE_BYTES}). Use project_grep for "
                    "targeted lookups or read smaller ranges with offset/limit."
                ),
                "path": resolved.rel_path,
                "size": size,
            }

        try:
            text, encoding = read_text_with_detection(resolved.abs_path)
        except UnicodeDecodeError as exc:
            return {
                "error": f"File is not text or has unknown encoding: {exc}",
                "path": resolved.rel_path,
                "size": size,
            }

        offset = int(params.get("offset") or 1)
        limit = int(params.get("limit") or 2000)
        rendered, start, end = format_lines_with_numbers(
            text, offset=offset, limit=limit,
        )
        total_lines = text.count("\n") + (
            0 if text.endswith("\n") or not text else 1
        )
        return {
            "path": resolved.rel_path,
            "encoding": encoding,
            "size": size,
            "total_lines": total_lines,
            "start_line": start,
            "end_line": end,
            "content": rendered,
            "truncated": end < total_lines,
        }
