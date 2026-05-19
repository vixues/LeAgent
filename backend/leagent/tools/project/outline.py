"""``project_outline`` — lightweight Python symbol and import index.

Parses each ``*.py`` file with :mod:`ast` (no tree-sitter) and returns
top-level functions, async functions, classes, and import statements so
the coding agent can navigate without reading entire modules.
"""

from __future__ import annotations

import ast
import re
from typing import TYPE_CHECKING, Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.project._fs import (
    IgnoreMatcher,
    read_text_with_detection,
    resolve_in_project,
    select_project_root,
    walk_project,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern)
    translated = (
        escaped.replace(r"\*\*/", "(?:.*/)?")
        .replace(r"/\*\*", "(?:/.*)?")
        .replace(r"\*\*", ".*")
        .replace(r"\*", "[^/]*")
        .replace(r"\?", "[^/]")
    )
    return re.compile(translated)


def _outline_python_source(rel_path: str, source: str) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source, filename=rel_path)
    except SyntaxError as exc:
        return {
            "path": rel_path,
            "language": "python",
            "parse_error": str(exc),
            "lineno": getattr(exc, "lineno", None),
            "offset": getattr(exc, "offset", None),
            "symbols": [],
            "imports": [],
        }

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    {
                        "kind": "import",
                        "module": None,
                        "names": [alias.name],
                        "line": int(node.lineno),
                    }
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module
            names = [a.name for a in node.names]
            imports.append(
                {
                    "kind": "from",
                    "module": mod,
                    "names": names,
                    "line": int(node.lineno),
                }
            )
        elif isinstance(node, ast.FunctionDef):
            end = getattr(node, "end_lineno", None)
            symbols.append(
                {
                    "kind": "function",
                    "name": node.name,
                    "line": int(node.lineno),
                    "end_line": int(end) if isinstance(end, int) else None,
                }
            )
        elif isinstance(node, ast.AsyncFunctionDef):
            end = getattr(node, "end_lineno", None)
            symbols.append(
                {
                    "kind": "async_function",
                    "name": node.name,
                    "line": int(node.lineno),
                    "end_line": int(end) if isinstance(end, int) else None,
                }
            )
        elif isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", None)
            symbols.append(
                {
                    "kind": "class",
                    "name": node.name,
                    "line": int(node.lineno),
                    "end_line": int(end) if isinstance(end, int) else None,
                }
            )

    return {
        "path": rel_path,
        "language": "python",
        "symbols": symbols,
        "imports": imports,
    }


class ProjectOutlineTool(BaseTool):
    """Return top-level Python symbols and imports for files in the project."""

    name = "project_outline"
    description = (
        "List top-level functions, async functions, classes, and import "
        "statements for Python files under the active project root. "
        "Use before `project_read` to locate symbols. Pass `path` as a "
        "single `.py` file or a subdirectory; combine with `glob` "
        "(default `**/*.py`) and `max_files` to cap work on large trees."
    )
    category = ToolCategory.CODE
    aliases = ["python_outline", "code_outline"]
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    timeout_sec = 45

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Project-relative file (`.py`) or directory. "
                        "Defaults to the project root."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": (
                        "Glob matched against project-relative paths "
                        "(default `**/*.py`)."
                    ),
                    "default": "**/*.py",
                },
                "max_files": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 40,
                    "description": "Maximum number of Python files to parse.",
                },
                "project_path": {
                    "type": "string",
                    "description": "Optional override of the active project root.",
                },
            },
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        p = (params or {}).get("path")
        return f"Outline {p}" if p else "Outline project (Python)"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        root = select_project_root(
            context, explicit=params.get("project_path"),
        )
        rel = (params.get("path") or "").strip()
        if rel:
            resolved = resolve_in_project(root, rel, must_exist=True)
            target = resolved.abs_path
        else:
            target = root

        glob_pat = str(params.get("glob") or "**/*.py").strip() or "**/*.py"
        max_files = int(params.get("max_files") or 40)
        max_files = max(1, min(500, max_files))
        regex = _glob_to_regex(glob_pat)

        py_files: list[Path] = []
        truncated_walk = False

        if target.is_file():
            if target.suffix != ".py":
                return {
                    "error": "project_outline only supports `.py` files.",
                    "path": rel or ".",
                }
            try:
                target.relative_to(root)
            except ValueError:
                return {"error": "Path escapes project root."}
            py_files = [target]
        else:
            matcher = IgnoreMatcher(root)
            for fpath in walk_project(target, matcher=matcher, max_files=50_000):
                if fpath.suffix != ".py":
                    continue
                try:
                    rel_p = fpath.relative_to(root).as_posix()
                except ValueError:
                    continue
                if not regex.fullmatch(rel_p) and not regex.fullmatch(fpath.name):
                    continue
                py_files.append(fpath)
                if len(py_files) >= max_files:
                    truncated_walk = True
                    break

        py_files.sort(key=lambda p: p.relative_to(root).as_posix())

        outlines: list[dict[str, Any]] = []
        for fpath in py_files:
            rel_p = fpath.relative_to(root).as_posix()
            try:
                text, _enc = read_text_with_detection(fpath)
            except OSError as exc:
                outlines.append(
                    {
                        "path": rel_p,
                        "language": "python",
                        "error": str(exc),
                        "symbols": [],
                        "imports": [],
                    }
                )
                continue
            outlines.append(_outline_python_source(rel_p, text))

        logger.info(
            "project_outline",
            files=len(outlines),
            truncated=truncated_walk,
        )
        return {
            "glob": glob_pat,
            "max_files": max_files,
            "files": outlines,
            "count": len(outlines),
            "truncated": truncated_walk,
        }
