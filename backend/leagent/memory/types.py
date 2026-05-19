"""Typed shapes exchanged between the agent runtime and :mod:`memory`.

These dataclasses are the language the :class:`AgentMemory` facade speaks.
They intentionally do not expose ORM models to callers — the agent never
sees raw SQLModel instances, only these flat dicts.

Three cognitive memory kinds:

* :class:`Episode` — summaries of past conversation turns.
* :class:`Fact` — stable user / workspace facts.
* :class:`Procedure` — outcomes of tool chains.

And one retrieval shape:

* :class:`RecallEntry` / :class:`RecallBundle` — the result of
  :meth:`AgentMemory.recall`, carrying ranked items alongside their
  provenance so the controller can render them into the system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable
from uuid import UUID, uuid4


class MemoryKind(str, Enum):
    """Which cognitive store an item came from."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Episode:
    """One past-turn summary the agent may recall."""

    session_id: UUID
    summary: str
    transcript: str | None = None
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    flow_id: UUID | None = None
    tags: list[str] = field(default_factory=list)
    importance: float = 0.0
    token_count: int | None = None
    recall_count: int = 0
    last_recalled_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class Fact:
    """A stable user/workspace-level fact or preference."""

    user_id: UUID
    key: str
    value: str
    workspace_id: UUID | None = None
    confidence: float = 0.8
    source: str | None = None
    created_at: datetime = field(default_factory=_utc_now)
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class Procedure:
    """A canonical tool-chain outcome the agent can pattern-match against."""

    name: str
    signature: str
    description: str
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    run_count: int = 0
    success_count: int = 0
    last_outcome: str | None = None
    last_error: str | None = None
    last_duration_ms: int | None = None
    last_run_at: datetime | None = None
    created_at: datetime = field(default_factory=_utc_now)
    id: UUID = field(default_factory=uuid4)
    # Back-compat: older code paths passed task_type=; it is not used by stores.
    task_type: str | None = field(default=None, repr=False)

    @property
    def success_rate(self) -> float:
        if self.run_count <= 0:
            return 0.0
        return max(0.0, min(1.0, self.success_count / self.run_count))


@dataclass(slots=True)
class RecallEntry:
    """One item returned by :meth:`AgentMemory.recall`."""

    kind: MemoryKind
    text: str
    score: float
    source_id: UUID
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt_line(self) -> str:
        """Render the entry as a single prompt-ready bullet."""
        prefix = {
            MemoryKind.EPISODIC: "past",
            MemoryKind.SEMANTIC: "fact",
            MemoryKind.PROCEDURAL: "procedure",
        }.get(self.kind, "memory")
        return f"- ({prefix}) {self.text.strip()}"


@dataclass(slots=True)
class RecallBundle:
    """Grouped recall output — keeps provenance legible for the controller."""

    query: str
    entries: list[RecallEntry] = field(default_factory=list)
    episodes: list[RecallEntry] = field(default_factory=list)
    facts: list[RecallEntry] = field(default_factory=list)
    procedures: list[RecallEntry] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.entries

    def extend(self, items: Iterable[RecallEntry]) -> None:
        for item in items:
            self.entries.append(item)
            if item.kind is MemoryKind.EPISODIC:
                self.episodes.append(item)
            elif item.kind is MemoryKind.SEMANTIC:
                self.facts.append(item)
            elif item.kind is MemoryKind.PROCEDURAL:
                self.procedures.append(item)

    def to_prompt_block(self, *, max_lines: int = 16) -> str:
        """Render the bundle as a compact system-prompt block.

        Returns an empty string when the bundle is empty so callers can just
        concatenate the output unconditionally.
        """
        if not self.entries:
            return ""
        limit = min(max_lines, len(self.entries))
        lines = [entry.to_prompt_line() for entry in self.entries[:limit]]
        return (
            "<agent_memory>\n"
            + "\n".join(lines)
            + "\n</agent_memory>"
        )


__all__ = [
    "Episode",
    "Fact",
    "MemoryKind",
    "Procedure",
    "RecallBundle",
    "RecallEntry",
]
