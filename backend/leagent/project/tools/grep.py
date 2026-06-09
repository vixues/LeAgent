"""``project_grep`` — regex search across the project tree.

The implementation has two backends:

1. **ripgrep** (preferred) — when ``rg`` is on ``PATH`` the tool shells
   out to it. Ripgrep is dramatically faster on large repos, supports
   ``.gitignore`` natively, and gives consistent line/column numbers.
2. **Pure-Python fallback** — when ``rg`` is unavailable the tool walks
   the project with the local :class:`IgnoreMatcher` and runs the
   regex line-by-line. Slower but works on every host.

The output is intentionally compact — a list of
``{path, line, column, text}`` matches plus a ``files_with_matches``
summary — so it slots directly into the LLM's context without
swallowing the turn budget. Callers cap the search via ``max_matches``
and ``max_filesize_bytes`` to keep results tight.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.project.fs import (
    IgnoreMatcher,
    looks_binary,
    select_project_root,
    walk_project,
)

logger = structlog.get_logger(__name__)


class ProjectGrepTool(BaseTool):
    """Regex search across the project (rg-aware)."""

    name = "project_grep"
    description = (
        "Search the project tree for a regex pattern. Uses ripgrep when "
        "available, falling back to a pure-Python walker that respects "
        ".gitignore and skips obvious caches (node_modules, __pycache__, "
        "dist, build, .venv, .git). Returns matches with file/line/column."
    )
    category = ToolCategory.CODE
    aliases = ["grep", "code_grep"]
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    timeout_sec = 60

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern (Python re syntax).",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Subdirectory or file to search relative to the "
                        "project root. Defaults to the entire project."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": (
                        "Optional glob to restrict file names "
                        "(e.g. `*.ts`, `src/**/*.py`)."
                    ),
                },
                "case_insensitive": {
                    "type": "boolean",
                    "default": False,
                },
                "max_matches": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 2000,
                    "default": 200,
                },
                "context_before": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 0,
                },
                "context_after": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 0,
                },
                "files_with_matches_only": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "When true, return just the file list — handy "
                        "for narrowing before a follow-up read."
                    ),
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
        return f"Searching for /{pat}/" if pat else "Searching project"

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        root = select_project_root(
            context, explicit=params.get("project_path"),
        )
        pattern = params["pattern"]
        rel_target = (params.get("path") or "").strip()
        max_matches = int(params.get("max_matches") or 200)
        case_i = bool(params.get("case_insensitive") or False)
        glob = params.get("glob") or None
        before = int(params.get("context_before") or 0)
        after = int(params.get("context_after") or 0)
        files_only = bool(params.get("files_with_matches_only") or False)

        target_dir = root if not rel_target else (root / rel_target).resolve()
        try:
            target_dir.relative_to(root)
        except ValueError:
            return {"error": f"`path` {rel_target!r} escapes project root."}

        rg = shutil.which("rg")
        if rg is not None:
            try:
                return await _run_ripgrep(
                    rg=rg,
                    pattern=pattern,
                    cwd=str(target_dir),
                    project_root=root,
                    case_insensitive=case_i,
                    glob=glob,
                    max_matches=max_matches,
                    before=before,
                    after=after,
                    files_only=files_only,
                )
            except Exception as exc:  # noqa: BLE001 - fallback to Python
                logger.debug("project_grep_rg_failed", error=str(exc))

        try:
            flags = re.IGNORECASE if case_i else 0
            regex = re.compile(pattern, flags)
        except re.error as exc:
            return {"error": f"Invalid regex: {exc}"}

        matches: list[dict[str, Any]] = []
        files: set[str] = set()
        matcher = IgnoreMatcher(root)

        for fpath in walk_project(target_dir, matcher=matcher):
            try:
                rel = fpath.relative_to(root).as_posix()
            except ValueError:
                continue
            if glob and not _glob_match(rel, glob):
                continue
            try:
                size = fpath.stat().st_size
            except OSError:
                continue
            if size > 5 * 1024 * 1024:
                continue
            try:
                with fpath.open("rb") as fh:
                    head = fh.read(8192)
                if looks_binary(head):
                    continue
                with fpath.open("r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()
            except OSError:
                continue

            for i, line in enumerate(lines, start=1):
                m = regex.search(line)
                if not m:
                    continue
                files.add(rel)
                if files_only:
                    break
                ctx_before = [
                    {"line": j, "text": lines[j - 1].rstrip("\n")}
                    for j in range(max(1, i - before), i)
                ] if before else []
                ctx_after = [
                    {"line": j, "text": lines[j - 1].rstrip("\n")}
                    for j in range(i + 1, min(len(lines) + 1, i + 1 + after))
                ] if after else []
                matches.append({
                    "path": rel,
                    "line": i,
                    "column": m.start() + 1,
                    "text": line.rstrip("\n"),
                    "before": ctx_before,
                    "after": ctx_after,
                })
                if len(matches) >= max_matches:
                    break
            if len(matches) >= max_matches:
                break

        if files_only:
            return {
                "files_with_matches": sorted(files),
                "count": len(files),
                "engine": "python",
            }
        return {
            "matches": matches,
            "count": len(matches),
            "files_with_matches": sorted(files),
            "truncated": len(matches) >= max_matches,
            "engine": "python",
        }


async def _run_ripgrep(
    *,
    rg: str,
    pattern: str,
    cwd: str,
    project_root,
    case_insensitive: bool,
    glob: str | None,
    max_matches: int,
    before: int,
    after: int,
    files_only: bool,
) -> dict[str, Any]:
    """Invoke ripgrep with JSON output and normalise the response."""
    args: list[str] = [rg, "--json", "-n", "-H"]
    if case_insensitive:
        args.append("-i")
    if before:
        args.extend(["-B", str(before)])
    if after:
        args.extend(["-A", str(after)])
    if glob:
        args.extend(["-g", glob])
    if files_only:
        args.append("-l")
    args.append("-m")
    args.append(str(max_matches))
    args.append("--")
    args.append(pattern)
    args.append(".")

    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=45.0,
        )
    except asyncio.TimeoutError:
        proc.kill()
        return {"error": "ripgrep timed out", "engine": "ripgrep"}

    if proc.returncode not in (0, 1):
        return {
            "error": stderr.decode("utf-8", errors="replace") or "ripgrep failed",
            "engine": "ripgrep",
        }

    if files_only:
        files = [
            ln.strip() for ln in stdout.decode("utf-8", errors="replace").splitlines()
            if ln.strip()
        ]
        # rg in -l mode outputs paths relative to ``cwd``; rebase under the
        # project root so the agent receives canonical refs.
        try:
            from pathlib import Path

            rebased = []
            for f in files:
                p = (Path(cwd) / f).resolve()
                try:
                    rebased.append(p.relative_to(project_root).as_posix())
                except ValueError:
                    rebased.append(f)
            files = rebased
        except Exception:  # noqa: BLE001
            pass
        return {
            "files_with_matches": sorted(set(files)),
            "count": len(set(files)),
            "engine": "ripgrep",
        }

    import json as _json
    matches: list[dict[str, Any]] = []
    files: set[str] = set()
    pending: dict[str, list[dict[str, Any]]] = {}
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        if not raw_line.strip():
            continue
        try:
            evt = _json.loads(raw_line)
        except _json.JSONDecodeError:
            continue
        if evt.get("type") != "match":
            continue
        data = evt.get("data") or {}
        path_obj = (data.get("path") or {}).get("text", "")
        line_no = data.get("line_number")
        if not path_obj or not isinstance(line_no, int):
            continue
        from pathlib import Path

        try:
            rel = (Path(cwd) / path_obj).resolve().relative_to(project_root).as_posix()
        except (OSError, ValueError):
            rel = path_obj
        files.add(rel)
        text_obj = (data.get("lines") or {}).get("text", "")
        column = 0
        sub = data.get("submatches") or []
        if sub:
            column = sub[0].get("start", 0) + 1
        matches.append({
            "path": rel,
            "line": line_no,
            "column": column,
            "text": text_obj.rstrip("\n"),
        })
        if len(matches) >= max_matches:
            break
    return {
        "matches": matches,
        "count": len(matches),
        "files_with_matches": sorted(files),
        "truncated": len(matches) >= max_matches,
        "engine": "ripgrep",
    }


def _glob_match(rel_path: str, pattern: str) -> bool:
    """Compare a posix relative path to a glob (``*.py``, ``src/**/*.ts``)."""
    from fnmatch import fnmatchcase

    if "**" in pattern:
        regex = (
            re.escape(pattern)
            .replace(r"\*\*/", ".*")
            .replace(r"/\*\*", ".*")
            .replace(r"\*\*", ".*")
            .replace(r"\*", "[^/]*")
            .replace(r"\?", "[^/]")
        )
        return re.fullmatch(regex, rel_path) is not None
    return fnmatchcase(rel_path, pattern) or fnmatchcase(
        os.path.basename(rel_path), pattern
    )
