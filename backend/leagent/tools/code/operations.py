"""Typed operation envelopes and session-scoped operation journal.

Every code-producing tool (``project_write``, ``project_edit``,
``project_apply_patch``, ``code_execution``) returns a typed
operation model via ``.model_dump()``.  The wire format is identical
to the previous ad-hoc dicts so downstream consumers (``query.py``
serialiser, SSE, frontend) do not break — but construction is now
validated at the Pydantic boundary.

The :class:`OperationJournal` keeps an ordered log of
:class:`JournalEntry` items on ``ToolUseContext.extra`` so the LLM
can consult "what I've done so far" through the
:class:`~leagent.context.sources.session_artifacts.SessionArtifactsSource`
without re-reading every file.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Operation envelopes — one per tool family
# ---------------------------------------------------------------------------


class FileWriteOp(BaseModel):
    """Returned by ``project_write``."""

    path: str
    bytes_written: int = 0
    lines: int = 0
    created: bool = False
    overwrite: bool = False
    validate_only: bool = False
    source_length: int = 0
    artifact_id: str | None = None
    syntax_valid: bool | None = None
    language: str | None = None
    kind: str | None = None
    target_path: str | None = None
    syntax_diagnostics: list[dict[str, Any]] | None = None


class FileEditOp(BaseModel):
    """Returned by ``project_edit``."""

    path: str
    replacements: int = 0
    new_size: int = 0
    diff: str = ""
    artifact_id: str | None = None


class PatchedFile(BaseModel):
    """One file touched by a unified diff."""

    path: str
    is_new: bool = False
    is_deleted: bool = False


class FilePatchOp(BaseModel):
    """Returned by ``project_apply_patch``."""

    files: list[PatchedFile] = Field(default_factory=list)
    count: int = 0


class CodeExecOp(BaseModel):
    """Returned by ``code_execution``.

    Mirrors :class:`~leagent.tools.code.execution.CodeExecutionEnvelope`
    but with Pydantic validation.
    """

    status: str = "ok"
    error: str | None = None
    error_type: str | None = None
    stdout: str = ""
    stderr: str = ""
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    result: Any = None
    produced_files: list[dict[str, Any]] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    files: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0
    workspace: str = ""
    returncode: int = 0
    source_echo: str = ""
    source_length: int = 0
    artifact_id: str | None = None
    syntax_diagnostics: list[dict[str, Any]] | None = None
    suggested_fix_region: dict[str, Any] | None = None
    workspace_file: str | None = None
    repair_workflow: str | None = None


# ---------------------------------------------------------------------------
# Operation journal
# ---------------------------------------------------------------------------


class JournalEntry(BaseModel):
    """One operation recorded in the journal."""

    seq: int = 0
    timestamp: float = Field(default_factory=time.time)
    tool: str = ""
    path: str | None = None
    kind: str = ""
    summary: str = ""
    success: bool = True
    artifact_id: str | None = None
    verification: str | None = None


_MAX_JOURNAL_ENTRIES = 60


class OperationJournal:
    """Ordered, thread-safe log of operations within a session.

    Lives on ``ToolUseContext.extra["_operation_journal"]`` and is
    consumed by :class:`SessionArtifactsSource` for prompt injection.
    """

    def __init__(self, max_entries: int = _MAX_JOURNAL_ENTRIES) -> None:
        self._lock = threading.Lock()
        self._entries: list[JournalEntry] = []
        self._seq = 0
        self._max = max_entries

    def append(self, entry: JournalEntry) -> JournalEntry:
        with self._lock:
            self._seq += 1
            entry.seq = self._seq
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max:]
        return entry

    def recent(self, limit: int = 20) -> list[JournalEntry]:
        with self._lock:
            return list(self._entries[-limit:])

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def summary_text(self, limit: int = 15) -> str:
        """Compact text for context injection."""
        entries = self.recent(limit)
        if not entries:
            return ""
        lines: list[str] = ["## Recent operations"]
        for e in entries:
            status = "ok" if e.success else "FAIL"
            path = e.path or "(session)"
            verify = f" [{e.verification}]" if e.verification else ""
            lines.append(
                f"- #{e.seq} `{e.tool}` {e.kind} `{path}` {status}{verify}"
            )
        return "\n".join(lines)


JOURNAL_CONTEXT_KEY = "_operation_journal"
"""Key used in ``ToolUseContext.extra`` to store the journal."""
