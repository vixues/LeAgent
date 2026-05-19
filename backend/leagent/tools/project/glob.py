"""``project_glob`` — gitignore-aware glob over the project tree.

Useful for "give me every TypeScript test file" or "where do we keep
GitHub workflow YAMLs". Returns paths sorted by recently modified
mtime first because the most-relevant files in any non-trivial
investigation tend to be the freshest. Skips the same caches as
``project_grep``.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.project._fs import (
    IgnoreMatcher,
    select_project_root,
    walk_project,
)

logger = structlog.get_logger(__name__)


class ProjectGlobTool(BaseTool):
    """List files in the project matching a glob pattern."""

    name = "project_glob"
    description = (
        "Find files matching a glob pattern (e.g. `**/*.ts`, "
        "`src/**/test_*.py`) inside the active project root. Skips "
        "common caches and respects .gitignore. Results are sorted by "
        "modification time (newest first) so the most likely candidates "
        "show up at the top."
    )
    category = ToolCategory.CODE
    aliases = ["glob_files", "code_glob"]
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
                "pattern": {
                    "type": "string",
                    "description": (
                        "Glob pattern. Use `**` for recursive match, "
                        "`*` to match within a path segment."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Subdirectory to search within. Defaults to the "
                        "project root."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5000,
                    "default": 500,
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Optional override of the active project root."
                    ),
                },
            },
            "required": ["pattern"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        pat = (params or {}).get("pattern", "")
        return f"Globbing {pat}" if pat else "Globbing project"

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

        max_results = int(params.get("max_results") or 500)
        pattern = params["pattern"]
        regex = _glob_to_regex(pattern)

        matcher = IgnoreMatcher(root)
        hits: list[tuple[float, str, int]] = []
        for fpath in walk_project(target, matcher=matcher):
            try:
                rel_p = fpath.relative_to(root).as_posix()
            except ValueError:
                continue
            if not regex.fullmatch(rel_p) and not regex.fullmatch(fpath.name):
                continue
            try:
                st = fpath.stat()
            except OSError:
                continue
            hits.append((st.st_mtime, rel_p, st.st_size))

        hits.sort(key=lambda x: (-x[0], x[1]))
        files = [
            {"path": p, "size": size, "mtime": mtime}
            for mtime, p, size in hits[:max_results]
        ]
        return {
            "pattern": pattern,
            "files": files,
            "count": len(files),
            "truncated": len(hits) > len(files),
        }


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob (with ``**``) to a regex matching POSIX paths."""
    escaped = re.escape(pattern)
    translated = (
        escaped
        .replace(r"\*\*/", "(?:.*/)?")
        .replace(r"/\*\*", "(?:/.*)?")
        .replace(r"\*\*", ".*")
        .replace(r"\*", "[^/]*")
        .replace(r"\?", "[^/]")
    )
    return re.compile(translated)
