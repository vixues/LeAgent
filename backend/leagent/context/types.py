"""Core types for the context management system.

All dataclasses, enums, and type aliases used across the context package
live here to avoid circular imports.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping
from uuid import UUID


class ContextScope(str, Enum):
    """Lifetime of a cached source resolution."""

    PROCESS = "process"
    SESSION = "session"
    TURN = "turn"


class RenderTarget(str, Enum):
    """Where a resolved block should be placed."""

    SYSTEM = "system"
    ATTACHMENT_USER = "attachment_user"


class AttachmentKind(str, Enum):
    RECALL = "recall"
    WORKING_SET = "working_set"
    TOOL_HISTORY = "tool_history"
    RECENT_READS = "recent_reads"


class ProjectMemoryOrigin(str, Enum):
    GLOBAL = "global"
    PROJECT = "project"
    LOCAL = "local"


# ---------------------------------------------------------------------------
# ContextBlock — the unit every source emits after resolve()
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ContextBlock:
    """One resolved chunk of context ready for budgeting and rendering."""

    source_id: str
    kind: Literal["identity", "state"]
    render_target: RenderTarget
    body: str
    tokens: int
    cost: int
    signature: str
    priority: int
    weight: float
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @staticmethod
    def approx_tokens(text: str) -> int:
        return max(1, len(text) // 3)

    @staticmethod
    def content_signature(source_id: str, body: str) -> str:
        digest = hashlib.sha256(f"{source_id}:{body}".encode()).hexdigest()[:16]
        return f"{source_id}:{digest}"


# ---------------------------------------------------------------------------
# ProjectMemorySource — discovery audit record
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ProjectMemorySource:
    path: str
    origin: ProjectMemoryOrigin
    content: str
    size: int
    injected: bool = True
    skip_reason: str = ""


# ---------------------------------------------------------------------------
# EnvironmentSnapshot
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class EnvironmentSnapshot:
    date: str
    cwd: str
    env: str
    os_name: str = ""
    shell: str = ""
    is_git_repo: bool = False
    git_branch: str = ""
    git_dirty: bool = False
    git_modified_count: int = 0
    git_ahead: int = 0
    git_behind: int = 0
    sandbox_mode: str = ""
    approval_policy: str = ""


# ---------------------------------------------------------------------------
# FileReadRecord
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FileReadRecord:
    path: str
    mtime_ns: int
    size: int
    tokens: int = 0
    pinned: bool = False


# ---------------------------------------------------------------------------
# WorkingSetEntry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class WorkingSetEntry:
    path: str
    excerpt_head: str = ""
    excerpt_tail: str = ""
    total_lines: int = 0
    tokens: int = 0


# ---------------------------------------------------------------------------
# TurnContext — returned by ContextManager.prepare_turn
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TurnContext:
    """Result of :meth:`ContextManager.prepare_turn`."""

    built_prompt: Any  # BuiltPrompt from leagent.prompts.types
    attachment_messages: list[dict[str, Any]]
    ledger: Any  # ContextLedger
    environment: EnvironmentSnapshot | None
    recall_handle: Any | None  # RecallHandle
    task_id: UUID
    project_memory_sources: list[ProjectMemorySource] = field(default_factory=list)
