"""Block webpage HTML emission from ``code_execution``.

Hosted pages belong on ``canvas_publish`` / blob / ``project_write``. This
module is the single policy string + detection used by
:class:`~leagent.code.execution.CodeExecutionTool`.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

_WEBPAGE_SUFFIXES = frozenset({".html", ".htm"})

_SOURCE_HTML_WRITE = re.compile(
    r"""(?ix)
    (?:
        open\s*\(\s*(?:f)?['\"][^'\"]+\.html?['\"]\s*,\s*(?:f)?['\"][wa][^'\"]*['\"]
      | Path\s*\(\s*(?:f)?['\"][^'\"]+\.html?['\"]\s*\)\s*\.\s*
            write(?:_text|_bytes)?\s*\(
    )
    """
)

WEBPAGE_NEXT_STEP = (
    "Publish webpages with `canvas_publish(mode=html)`: "
    "compact → inline `html`; no Active Project → `tool_argument_blob` then "
    "`html_blob_id` / `html_files_blob_id`; Active Project → `project_write` "
    "then `html_paths`. Use `code_execution` for data/stats only."
)

WEBPAGE_BLOCK_ERROR = (
    "code_execution cannot write webpage .html/.htm files; "
    "use canvas_publish / blob / project_write (see next_step)."
)


def source_writes_webpage(source: str) -> bool:
    """True when source clearly opens an HTML file for write."""
    return bool(_SOURCE_HTML_WRITE.search(source or ""))


def webpage_paths_in_produced(
    produced_files: list[dict[str, Any]] | None,
) -> list[str]:
    """Return unique `.html`/`.htm` paths from sandbox produced_files."""
    out: list[str] = []
    seen: set[str] = set()
    for entry in produced_files or []:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("file_path") or entry.get("path") or entry.get("filename") or ""
        path = str(raw).strip()
        if not path:
            continue
        suffix = PurePosixPath(path.replace("\\", "/").split("/")[-1]).suffix.lower()
        if suffix not in _WEBPAGE_SUFFIXES or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def attach_webpage_block(
    envelope: dict[str, Any],
    *,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """Mark a code_execution envelope as a webpage-write policy failure."""
    envelope["status"] = "error"
    envelope["error"] = WEBPAGE_BLOCK_ERROR
    envelope["error_type"] = "validation"
    envelope["next_step"] = WEBPAGE_NEXT_STEP
    envelope["repair_workflow"] = WEBPAGE_NEXT_STEP
    if paths:
        envelope["blocked_webpage_files"] = list(paths)
    return envelope
