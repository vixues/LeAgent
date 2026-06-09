"""``project_tree`` — compact, depth-limited directory tree.

The first thing the coding agent should do on an unfamiliar project is
get a feel for the shape — top-level directories, the files at each
level, where the source vs. tests vs. config live. ``project_tree``
renders that view in a compact ASCII form, gitignore-aware and capped
at a configurable depth so it doesn't drown the LLM context with
generated artefacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.project.fs import (
    IgnoreMatcher,
    select_project_root,
)

logger = structlog.get_logger(__name__)


class ProjectTreeTool(BaseTool):
    """Render a depth-limited tree of the project directory."""

    name = "project_tree"
    description = (
        "Render a compact ASCII directory tree of the active project, "
        "respecting .gitignore and skipping common caches. Use as the "
        "first call on a new project to understand its layout. The "
        "output is text rather than JSON because the visual structure "
        "is the value."
    )
    category = ToolCategory.CODE
    aliases = ["tree", "code_tree"]
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000
    timeout_sec = 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Subdirectory to render. Defaults to the project root."
                    ),
                },
                "max_depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 3,
                },
                "max_entries_per_dir": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 500,
                    "default": 80,
                },
                "show_files": {
                    "type": "boolean",
                    "default": True,
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
        return "Rendering project tree"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        root = select_project_root(
            context, explicit=params.get("project_path"),
        )
        rel = (params.get("path") or "").strip()
        target = root if not rel else (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return {"error": f"`path` {rel!r} escapes project root."}

        max_depth = int(params.get("max_depth") or 3)
        max_per_dir = int(params.get("max_entries_per_dir") or 80)
        show_files = bool(params.get("show_files", True))
        matcher = IgnoreMatcher(root)

        lines: list[str] = []
        truncated = False

        def _walk(node: Path, depth: int, prefix: str) -> None:
            nonlocal truncated
            if depth > max_depth:
                return
            try:
                entries = list(node.iterdir())
            except (OSError, PermissionError):
                lines.append(f"{prefix}└─ <permission denied>")
                return

            kept = []
            for e in entries:
                if matcher.is_ignored(e):
                    continue
                if not show_files and e.is_file():
                    continue
                kept.append(e)
            kept.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

            visible = kept[:max_per_dir]
            if len(kept) > max_per_dir:
                truncated = True

            for idx, child in enumerate(visible):
                last = idx == len(visible) - 1
                connector = "└─ " if last else "├─ "
                if child.is_dir():
                    lines.append(f"{prefix}{connector}{child.name}/")
                    if depth < max_depth:
                        new_prefix = prefix + ("   " if last else "│  ")
                        _walk(child, depth + 1, new_prefix)
                else:
                    try:
                        size = child.stat().st_size
                    except OSError:
                        size = 0
                    lines.append(
                        f"{prefix}{connector}{child.name} ({_human_size(size)})"
                    )
            if len(kept) > max_per_dir:
                lines.append(
                    f"{prefix}   … and {len(kept) - max_per_dir} more entries"
                )

        rel_label = target.relative_to(root).as_posix() or "."
        lines.append(f"{rel_label}/")
        _walk(target, 1, "")

        return {
            "root": rel_label,
            "max_depth": max_depth,
            "tree": "\n".join(lines),
            "truncated": truncated,
        }


def _human_size(n: int) -> str:
    """Render byte counts as compact human strings (``2.4KB``, ``1.1MB``)."""
    units = ("B", "KB", "MB", "GB")
    val = float(n)
    for unit in units:
        if val < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(val)}B"
            return f"{val:.1f}{unit}"
        val /= 1024
    return f"{int(val)}{units[-1]}"
