"""In-memory fake backends for the memory store protocols.

These are test doubles that satisfy the same interface as the real
:class:`EpisodicStore`, :class:`SemanticStore`, and
:class:`ProceduralStore` without any database or Milvus dependency.
Use them in unit tests via:

    from leagent.memory.fake import FakeAgentMemory
    memory = FakeAgentMemory()
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from leagent.memory.embeddings import NullEmbeddingProvider
from leagent.memory.formation import FormationPolicy
from leagent.memory.types import (
    Episode,
    Fact,
    MemoryKind,
    Procedure,
    RecallBundle,
    RecallEntry,
)


class FakeEpisodicStore:
    """In-memory episodic store for tests."""

    def __init__(self) -> None:
        self._rows: dict[UUID, Episode] = {}

    async def record(self, episode: Episode) -> Episode:
        if episode.id is None:
            episode.id = uuid.uuid4()
        self._rows[episode.id] = episode
        return episode

    async def delete(self, episode_id: UUID) -> None:
        self._rows.pop(episode_id, None)

    async def list_recent(
        self,
        *,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        limit: int = 20,
    ) -> list[Episode]:
        results = list(self._rows.values())
        if user_id:
            results = [e for e in results if e.user_id == user_id]
        if session_id:
            results = [e for e in results if e.session_id == session_id]
        return results[:limit]

    async def lexical_search(
        self, query: str, *, user_id: UUID | None = None,
        session_id: UUID | None = None, limit: int = 5,
    ) -> list[RecallEntry]:
        results = []
        for ep in self._rows.values():
            if query.lower() in (ep.summary or "").lower():
                results.append(RecallEntry(
                    kind=MemoryKind.EPISODIC,
                    text=ep.summary or "",
                    score=0.5,
                    source_id=ep.id or uuid.uuid4(),
                ))
        return results[:limit]

    async def semantic_search(
        self, vector: list[float], *, user_id: UUID | None = None,
        session_id: UUID | None = None, limit: int = 5,
    ) -> list[RecallEntry]:
        return []

    async def note_recall(self, episode_id: UUID, *, at: datetime | None = None) -> None:
        pass


class FakeSemanticStore:
    """In-memory semantic (fact) store for tests."""

    def __init__(self) -> None:
        self._rows: dict[UUID, Fact] = {}

    async def upsert(self, fact: Fact) -> Fact:
        if fact.id is None:
            fact.id = uuid.uuid4()
        self._rows[fact.id] = fact
        return fact

    async def delete(self, fact_id: UUID) -> None:
        self._rows.pop(fact_id, None)

    async def get_by_key(
        self, *, user_id: UUID, key: str, workspace_id: UUID | None = None,
    ) -> Fact | None:
        for f in self._rows.values():
            if f.user_id == user_id and f.key == key:
                return f
        return None

    async def list_for_user(
        self, user_id: UUID, *, workspace_id: UUID | None = None, limit: int = 100,
    ) -> list[Fact]:
        results = [f for f in self._rows.values() if f.user_id == user_id]
        return results[:limit]

    async def lexical_search(
        self, query: str, *, user_id: UUID | None = None,
        workspace_id: UUID | None = None, limit: int = 5,
    ) -> list[RecallEntry]:
        results = []
        for f in self._rows.values():
            if query.lower() in (f.value or "").lower():
                results.append(RecallEntry(
                    kind=MemoryKind.SEMANTIC,
                    text=f.value or "",
                    score=0.5,
                    source_id=f.id or uuid.uuid4(),
                ))
        return results[:limit]

    async def semantic_search(
        self, vector: list[float], *, user_id: UUID | None = None,
        workspace_id: UUID | None = None, limit: int = 5,
    ) -> list[RecallEntry]:
        return []


class FakeProceduralStore:
    """In-memory procedural store for tests."""

    def __init__(self) -> None:
        self._rows: dict[UUID, Procedure] = {}

    async def record(
        self, procedure: Procedure, *, outcome: str, success: bool,
        error: str | None = None, duration_ms: int | None = None,
    ) -> Procedure:
        if procedure.id is None:
            procedure.id = uuid.uuid4()
        procedure.run_count = (procedure.run_count or 0) + 1
        if success:
            procedure.success_count = (procedure.success_count or 0) + 1
        self._rows[procedure.id] = procedure
        return procedure

    async def delete(self, procedure_id: UUID) -> None:
        self._rows.pop(procedure_id, None)

    async def get_by_signature(
        self, signature: str, *, user_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> Procedure | None:
        for p in self._rows.values():
            if p.signature == signature:
                return p
        return None

    async def list_recent_for_user(
        self, *, user_id: UUID, limit: int = 20,
    ) -> list[Procedure]:
        results = [p for p in self._rows.values() if p.user_id == user_id]
        return results[:limit]

    async def lexical_search(
        self, query: str, *, user_id: UUID | None = None,
        workspace_id: UUID | None = None, limit: int = 5,
    ) -> list[RecallEntry]:
        return []

    async def semantic_search(
        self, vector: list[float], *, user_id: UUID | None = None,
        workspace_id: UUID | None = None, limit: int = 5,
    ) -> list[RecallEntry]:
        return []


def FakeAgentMemory() -> Any:
    """Build an :class:`AgentMemory` backed by in-memory fakes.

    Returns a real ``AgentMemory`` instance so the full formation and
    recall pipelines are exercised, just without persistence.
    """
    from leagent.memory.agent_memory import AgentMemory

    return AgentMemory(
        episodic=FakeEpisodicStore(),  # type: ignore[arg-type]
        semantic=FakeSemanticStore(),  # type: ignore[arg-type]
        procedural=FakeProceduralStore(),  # type: ignore[arg-type]
        embeddings=NullEmbeddingProvider(),
        formation_policy=FormationPolicy(),
    )


__all__ = [
    "FakeAgentMemory",
    "FakeEpisodicStore",
    "FakeProceduralStore",
    "FakeSemanticStore",
]
