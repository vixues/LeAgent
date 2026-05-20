"""Structured code artifact model and session-scoped registry.

Every code-producing tool (``code_execution``, ``project_write``,
``project_edit``, ``project_apply_patch``, ``deepseek_fim``) creates a
:class:`CodeArtifact` via the :class:`CodeGenerationPipeline` before
executing or writing. This gives the system a unified intermediate
representation for validation, auditing, and frontend visibility.

The :class:`CodeArtifactRegistry` is a lightweight in-memory store
keyed by ``artifact_id``, living on :class:`ToolUseContext` so all
tools in a turn can access it. Entries are pruned per-session after
the turn completes. The optional :class:`SessionArtifactStore`
persists artifact **metadata** (not source text) across turns so the
LLM has awareness of previously generated artifacts.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class ArtifactKind(str, Enum):
    """Classification of a code artifact by its downstream consumer."""

    EXECUTE = "execute"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    FILE_PATCH = "file_patch"
    SNIPPET = "snippet"


def _content_hash(source: str) -> str:
    """SHA-256 hex digest of the artifact source text."""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


@dataclass
class CodeArtifact:
    """A single unit of LLM-generated code/text with validation metadata."""

    kind: ArtifactKind
    language: str
    source: str
    origin_tool: str
    session_id: str
    artifact_id: str = field(default_factory=lambda: uuid4().hex)
    target_path: str | None = None
    syntax_valid: bool | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    file_hash: str = field(default="")
    parent_artifact_id: str | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.file_hash and self.source:
            self.file_hash = _content_hash(self.source)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for SSE transport / structured logging."""
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind.value,
            "language": self.language,
            "origin_tool": self.origin_tool,
            "session_id": self.session_id,
            "target_path": self.target_path,
            "syntax_valid": self.syntax_valid,
            "diagnostics": self.diagnostics,
            "source_length": len(self.source),
            "file_hash": self.file_hash,
            "parent_artifact_id": self.parent_artifact_id,
        }

    def summary_line(self) -> str:
        """One-line summary for context injection (no source text)."""
        status = "valid" if self.syntax_valid else ("invalid" if self.syntax_valid is False else "?")
        path = self.target_path or "(inline)"
        return f"- {path} [{self.language}] {self.kind.value} {status} ({len(self.source)} chars)"


_MAX_ARTIFACTS_PER_SESSION = 200


class CodeArtifactRegistry:
    """Session-scoped in-memory registry of code artifacts.

    Thread-safe via a lock since tools may run concurrently across
    sessions (the registry is process-global, keyed by session).

    Automatically links edits to the same ``target_path`` via
    ``parent_artifact_id`` so the LLM can see the edit chain.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: OrderedDict[str, CodeArtifact] = OrderedDict()
        self._by_session: dict[str, list[str]] = {}
        self._latest_by_path: dict[tuple[str, str], str] = {}

    def register(self, artifact: CodeArtifact) -> None:
        with self._lock:
            if artifact.target_path and artifact.parent_artifact_id is None:
                path_key = (artifact.session_id, artifact.target_path)
                prev_id = self._latest_by_path.get(path_key)
                if prev_id and prev_id != artifact.artifact_id:
                    artifact.parent_artifact_id = prev_id
                self._latest_by_path[path_key] = artifact.artifact_id

            self._by_id[artifact.artifact_id] = artifact
            session_list = self._by_session.setdefault(artifact.session_id, [])
            session_list.append(artifact.artifact_id)
            if len(session_list) > _MAX_ARTIFACTS_PER_SESSION:
                evicted = session_list.pop(0)
                self._by_id.pop(evicted, None)

    def get(self, artifact_id: str) -> CodeArtifact | None:
        with self._lock:
            return self._by_id.get(artifact_id)

    def list_for_session(self, session_id: str) -> list[CodeArtifact]:
        with self._lock:
            ids = self._by_session.get(session_id, [])
            return [self._by_id[aid] for aid in ids if aid in self._by_id]

    def recent_for_session(
        self, session_id: str, limit: int = 20,
    ) -> list[CodeArtifact]:
        """Return the most recent *limit* artifacts for a session."""
        with self._lock:
            ids = self._by_session.get(session_id, [])
            tail = ids[-limit:] if len(ids) > limit else ids
            return [self._by_id[aid] for aid in tail if aid in self._by_id]

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            ids = self._by_session.pop(session_id, [])
            for aid in ids:
                self._by_id.pop(aid, None)
            to_remove = [
                k for k in self._latest_by_path if k[0] == session_id
            ]
            for k in to_remove:
                del self._latest_by_path[k]


# ---------------------------------------------------------------------------
# Persistent artifact metadata store
# ---------------------------------------------------------------------------


@dataclass
class ArtifactRecord:
    """Lightweight metadata record for cross-turn persistence.

    Source text is NOT stored here — it lives on disk.
    """

    artifact_id: str
    session_id: str
    kind: str
    language: str
    origin_tool: str
    target_path: str | None
    file_hash: str
    syntax_valid: bool | None
    parent_artifact_id: str | None
    created_at: float
    source_length: int

    @classmethod
    def from_artifact(cls, a: CodeArtifact) -> ArtifactRecord:
        return cls(
            artifact_id=a.artifact_id,
            session_id=a.session_id,
            kind=a.kind.value,
            language=a.language,
            origin_tool=a.origin_tool,
            target_path=a.target_path,
            file_hash=a.file_hash,
            syntax_valid=a.syntax_valid,
            parent_artifact_id=a.parent_artifact_id,
            created_at=a.created_at,
            source_length=len(a.source),
        )


class SessionArtifactStore:
    """In-memory persistent artifact metadata store, keyed by session.

    Lives in the process alongside the volatile ``CodeArtifactRegistry``.
    The registry calls :meth:`persist` on every registration so metadata
    survives across turns even after the registry evicts old artifacts.

    For a production deployment requiring process-restart durability, this
    store can be extended to flush to the database. The current in-memory
    implementation covers the common single-process case.
    """

    _MAX_PER_SESSION = 500

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_session: dict[str, list[ArtifactRecord]] = {}

    def persist(self, artifact: CodeArtifact) -> None:
        record = ArtifactRecord.from_artifact(artifact)
        with self._lock:
            records = self._by_session.setdefault(record.session_id, [])
            records.append(record)
            if len(records) > self._MAX_PER_SESSION:
                self._by_session[record.session_id] = records[-self._MAX_PER_SESSION :]

    def recent(self, session_id: str, limit: int = 20) -> list[ArtifactRecord]:
        with self._lock:
            records = self._by_session.get(session_id, [])
            return list(records[-limit:])

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._by_session.pop(session_id, None)

    def summary_text(self, session_id: str, limit: int = 15) -> str:
        """Build a compact text summary for context injection."""
        records = self.recent(session_id, limit)
        if not records:
            return ""
        lines: list[str] = ["## Recent code artifacts"]
        for r in records:
            status = "valid" if r.syntax_valid else ("invalid" if r.syntax_valid is False else "?")
            path = r.target_path or "(inline)"
            lines.append(
                f"- `{path}` [{r.language}] {r.kind} {status} "
                f"({r.source_length} chars, hash={r.file_hash[:12]}…)"
            )
        return "\n".join(lines)
