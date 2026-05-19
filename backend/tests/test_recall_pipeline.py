"""Tests for :class:`RetrievalPipeline` rerank + dedup behaviour.

The recall pipeline fans out across three stores, merges the results,
boosts them by recency / confidence / success rate, dedupes by
``(kind, source_id)``, and filters out files the current turn already
has open via :class:`FileStateCache`.

All of those pieces are unit-testable without Milvus: we feed the
pipeline hand-crafted :class:`RecallEntry` lists through fake stores
and assert on the final order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import pytest

from leagent.memory.recall import RecallOptions, RetrievalPipeline
from leagent.memory.types import MemoryKind, RecallEntry


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _StaticStore:
    """Returns a fixed list for semantic_search and nothing for lexical_search."""

    entries: list[RecallEntry] = field(default_factory=list)
    kind: MemoryKind = MemoryKind.EPISODIC
    recall_notes: list[UUID] = field(default_factory=list)

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return list(self.entries)

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []

    async def note_recall(self, source_id: UUID) -> None:
        self.recall_notes.append(source_id)


@dataclass
class _EmptyStore:
    """Both semantic and lexical search return an empty list."""

    kind: MemoryKind = MemoryKind.SEMANTIC

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []


@dataclass
class _CountingStore:
    semantic_entries: list[RecallEntry] = field(default_factory=list)
    lexical_entries: list[RecallEntry] = field(default_factory=list)
    kind: MemoryKind = MemoryKind.EPISODIC
    semantic_calls: int = 0
    lexical_calls: int = 0

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        self.semantic_calls += 1
        return list(self.semantic_entries)

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        self.lexical_calls += 1
        return list(self.lexical_entries)

    async def note_recall(self, source_id: UUID) -> None:
        return None


@dataclass
class _StaticEmbeddings:
    async def embed_one(self, text: str) -> list[float]:  # noqa: ARG002
        return [1.0] * 8

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[1.0] * 8 for _ in texts]


# ---------------------------------------------------------------------------
# FileStateCache stub for dedup tests
# ---------------------------------------------------------------------------


@dataclass
class _StaticFileState:
    known_paths: list[str] = field(default_factory=list)

    def paths(self) -> list[str]:
        return list(self.known_paths)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry(
    *,
    kind: MemoryKind,
    text: str,
    score: float,
    metadata: dict[str, Any] | None = None,
    source_id: UUID | None = None,
) -> RecallEntry:
    return RecallEntry(
        kind=kind,
        text=text,
        score=score,
        source_id=source_id or uuid4(),
        metadata=metadata or {},
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRecallPipeline:
    async def test_empty_query_short_circuits(self) -> None:
        pipeline = RetrievalPipeline(
            episodic=_EmptyStore(kind=MemoryKind.EPISODIC),  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_EmptyStore(kind=MemoryKind.PROCEDURAL),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )
        bundle = await pipeline.recall(RecallOptions(query="   "))
        assert bundle.is_empty()

    async def test_recall_anchor_used_when_query_blank(self) -> None:
        user_id = uuid4()
        ep = _StaticStore(
            kind=MemoryKind.EPISODIC,
            entries=[_entry(kind=MemoryKind.EPISODIC, text="anchored", score=0.9)],
        )
        pipeline = RetrievalPipeline(
            episodic=ep,  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_EmptyStore(kind=MemoryKind.PROCEDURAL),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )
        bundle = await pipeline.recall(
            RecallOptions(
                query="   ",
                recall_anchor="last user said this",
                user_id=user_id,
            )
        )
        assert bundle.query == "last user said this"
        assert not bundle.is_empty()
        assert any(e.text == "anchored" for e in bundle.entries)

    async def test_recent_episode_beats_stale_one(self) -> None:
        now = datetime.now(timezone.utc)
        recent = _entry(
            kind=MemoryKind.EPISODIC,
            text="recent turn",
            score=0.5,
            metadata={
                "created_at": _iso(now - timedelta(days=1)),
                "importance": 0.2,
            },
        )
        stale = _entry(
            kind=MemoryKind.EPISODIC,
            text="stale turn",
            score=0.5,
            metadata={
                "created_at": _iso(now - timedelta(days=60)),
                "importance": 0.2,
            },
        )

        pipeline = RetrievalPipeline(
            episodic=_StaticStore(entries=[stale, recent]),  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_EmptyStore(kind=MemoryKind.PROCEDURAL),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )
        bundle = await pipeline.recall(RecallOptions(query="turn"))

        assert [e.text for e in bundle.entries[:2]] == ["recent turn", "stale turn"]

    async def test_low_success_procedure_is_penalised(self) -> None:
        high = _entry(
            kind=MemoryKind.PROCEDURAL,
            text="reliable chain",
            score=0.5,
            metadata={"run_count": 20, "success_rate": 0.95},
        )
        low = _entry(
            kind=MemoryKind.PROCEDURAL,
            text="shaky chain",
            score=0.5,
            metadata={"run_count": 20, "success_rate": 0.05},
        )

        pipeline = RetrievalPipeline(
            episodic=_EmptyStore(kind=MemoryKind.EPISODIC),  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_StaticStore(
                entries=[low, high], kind=MemoryKind.PROCEDURAL
            ),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )
        bundle = await pipeline.recall(RecallOptions(query="chain"))

        assert bundle.entries[0].text == "reliable chain"
        assert bundle.entries[1].text == "shaky chain"

    async def test_file_state_dedup_drops_entries_mentioning_known_paths(
        self,
    ) -> None:
        open_path = "/tmp/leagent/session-abc/report.pdf"
        mentions = _entry(
            kind=MemoryKind.EPISODIC,
            text=f"summarised {open_path} previously",
            score=1.0,
        )
        unrelated = _entry(
            kind=MemoryKind.EPISODIC,
            text="asked about fiscal policy",
            score=0.8,
        )

        pipeline = RetrievalPipeline(
            episodic=_StaticStore(entries=[mentions, unrelated]),  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_EmptyStore(kind=MemoryKind.PROCEDURAL),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )
        bundle = await pipeline.recall(
            RecallOptions(
                query="recent topics",
                file_state=_StaticFileState(known_paths=[open_path]),  # type: ignore[arg-type]
            )
        )
        assert [e.text for e in bundle.entries] == ["asked about fiscal policy"]

    async def test_duplicate_source_ids_are_collapsed(self) -> None:
        dup_id = uuid4()
        first = _entry(
            kind=MemoryKind.EPISODIC,
            text="first",
            score=0.9,
            source_id=dup_id,
        )
        copy = _entry(
            kind=MemoryKind.EPISODIC,
            text="duplicate",
            score=0.9,
            source_id=dup_id,
        )
        distinct = _entry(
            kind=MemoryKind.EPISODIC,
            text="distinct",
            score=0.1,
        )

        pipeline = RetrievalPipeline(
            episodic=_StaticStore(entries=[first, copy, distinct]),  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_EmptyStore(kind=MemoryKind.PROCEDURAL),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )
        bundle = await pipeline.recall(RecallOptions(query="recall"))
        ids = [e.source_id for e in bundle.entries]
        assert ids.count(dup_id) == 1
        assert len(bundle.entries) == 2

    async def test_note_recall_called_once_per_episode(self) -> None:
        ep_id = uuid4()
        ep_store = _StaticStore(
            entries=[
                _entry(
                    kind=MemoryKind.EPISODIC,
                    text="remember this",
                    score=1.0,
                    source_id=ep_id,
                )
            ]
        )
        pipeline = RetrievalPipeline(
            episodic=ep_store,  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_EmptyStore(kind=MemoryKind.PROCEDURAL),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )
        await pipeline.recall(RecallOptions(query="remember"))
        assert ep_store.recall_notes == [ep_id]

    async def test_vector_search_precedes_lexical_fallback(self) -> None:
        semantic_hit = _entry(
            kind=MemoryKind.EPISODIC,
            text="semantic memory",
            score=0.9,
        )
        lexical_hit = _entry(
            kind=MemoryKind.EPISODIC,
            text="lexical memory",
            score=0.5,
        )
        ep_store = _CountingStore(
            semantic_entries=[semantic_hit],
            lexical_entries=[lexical_hit],
        )
        pipeline = RetrievalPipeline(
            episodic=ep_store,  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_EmptyStore(kind=MemoryKind.PROCEDURAL),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )

        bundle = await pipeline.recall(RecallOptions(query="memory"))

        assert [entry.text for entry in bundle.entries] == ["semantic memory"]
        assert ep_store.semantic_calls == 1
        assert ep_store.lexical_calls == 0

    async def test_lexical_search_fills_empty_vector_results(self) -> None:
        lexical_hit = _entry(
            kind=MemoryKind.EPISODIC,
            text="lexical fallback",
            score=0.5,
        )
        ep_store = _CountingStore(lexical_entries=[lexical_hit])
        pipeline = RetrievalPipeline(
            episodic=ep_store,  # type: ignore[arg-type]
            semantic=_EmptyStore(kind=MemoryKind.SEMANTIC),  # type: ignore[arg-type]
            procedural=_EmptyStore(kind=MemoryKind.PROCEDURAL),  # type: ignore[arg-type]
            embeddings=_StaticEmbeddings(),  # type: ignore[arg-type]
        )

        bundle = await pipeline.recall(RecallOptions(query="memory"))

        assert [entry.text for entry in bundle.entries] == ["lexical fallback"]
        assert ep_store.semantic_calls == 1
        assert ep_store.lexical_calls == 1
