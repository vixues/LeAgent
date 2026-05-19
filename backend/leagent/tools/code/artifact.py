"""Structured code artifact model and session-scoped registry.

Every code-producing tool (``code_execution``, ``project_write``,
``project_edit``, ``project_apply_patch``, ``deepseek_fim``) creates a
:class:`CodeArtifact` via the :class:`CodeGenerationPipeline` before
executing or writing. This gives the system a unified intermediate
representation for validation, auditing, and frontend visibility.

The :class:`CodeArtifactRegistry` is a lightweight in-memory store
keyed by ``artifact_id``, living on :class:`ToolUseContext` so all
tools in a turn can access it. Entries are pruned per-session after
the turn completes.
"""

from __future__ import annotations

import threading
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
        }


_MAX_ARTIFACTS_PER_SESSION = 200


class CodeArtifactRegistry:
    """Session-scoped in-memory registry of code artifacts.

    Thread-safe via a lock since tools may run concurrently across
    sessions (the registry is process-global, keyed by session).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_id: OrderedDict[str, CodeArtifact] = OrderedDict()
        self._by_session: dict[str, list[str]] = {}

    def register(self, artifact: CodeArtifact) -> None:
        with self._lock:
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

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            ids = self._by_session.pop(session_id, [])
            for aid in ids:
                self._by_id.pop(aid, None)
