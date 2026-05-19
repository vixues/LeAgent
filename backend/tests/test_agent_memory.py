"""Unit tests for :class:`AgentMemory` + :class:`RecallHandle`.

These tests use hand-rolled fakes for the episodic / semantic / procedural
stores. The real stores talk to Postgres + Milvus; we rely on the
existing integration suite to keep those honest. What we pin down here
is:

1. The façade dispatches writes to the right store and tolerates store
   failures without bubbling them up (memory must never crash the
   request).
2. :class:`RecallHandle` runs :meth:`AgentMemory.recall` exactly once
   even when :meth:`consume` is awaited repeatedly, caches the result,
   and returns an empty :class:`RecallBundle` on failure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from leagent.memory.agent_memory import AgentMemory, RecallHandle
from leagent.memory.recall import RecallOptions, RetrievalPipeline
from leagent.memory.types import (
    Episode,
    Fact,
    MemoryKind,
    Procedure,
    RecallBundle,
    RecallEntry,
)
from leagent.memory.vector import VectorWriteResult


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class _FakeEpisodic:
    episodes: list[Episode] = field(default_factory=list)
    raise_on_record: bool = False
    recall_notes: list[UUID] = field(default_factory=list)

    async def record(self, episode: Episode) -> Episode:
        if self.raise_on_record:
            raise RuntimeError("episodic down")
        self.episodes.append(episode)
        return episode

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []

    async def note_recall(self, source_id: UUID) -> None:
        self.recall_notes.append(source_id)


@dataclass
class _FakeSemantic:
    facts: list[Fact] = field(default_factory=list)
    raise_on_upsert: bool = False

    async def upsert(self, fact: Fact) -> Fact:
        if self.raise_on_upsert:
            raise RuntimeError("semantic down")
        self.facts.append(fact)
        return fact

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []


@dataclass
class _FakeProcedural:
    procedures: list[tuple[Procedure, dict[str, Any]]] = field(default_factory=list)
    raise_on_record: bool = False
    last_vector_write: VectorWriteResult | None = None

    async def record(
        self,
        procedure: Procedure,
        *,
        outcome: str,
        success: bool,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> Procedure:
        if self.raise_on_record:
            raise RuntimeError("procedural down")
        self.procedures.append(
            (
                procedure,
                {
                    "outcome": outcome,
                    "success": success,
                    "error": error,
                    "duration_ms": duration_ms,
                },
            )
        )
        self.last_vector_write = VectorWriteResult(written=False, degraded=True, error="milvus unavailable")
        return procedure

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
        return []


@dataclass
class _FakeEmbeddings:
    calls: int = 0

    async def embed_one(self, text: str) -> list[float]:  # noqa: ARG002
        self.calls += 1
        return [0.0] * 8

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def _make_memory(
    *,
    episodic: _FakeEpisodic | None = None,
    semantic: _FakeSemantic | None = None,
    procedural: _FakeProcedural | None = None,
) -> tuple[AgentMemory, _FakeEpisodic, _FakeSemantic, _FakeProcedural]:
    ep = episodic or _FakeEpisodic()
    sm = semantic or _FakeSemantic()
    pr = procedural or _FakeProcedural()
    mem = AgentMemory(
        episodic=ep,  # type: ignore[arg-type]
        semantic=sm,  # type: ignore[arg-type]
        procedural=pr,  # type: ignore[arg-type]
        embeddings=_FakeEmbeddings(),  # type: ignore[arg-type]
    )
    return mem, ep, sm, pr


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgentMemoryWrites:
    async def test_record_episode_delegates_to_episodic_store(self) -> None:
        mem, ep, _, _ = _make_memory()
        episode = Episode(session_id=uuid4(), summary="turn summary")
        out = await mem.record_episode(episode)
        assert out is episode
        assert ep.episodes == [episode]

    async def test_record_episode_swallows_store_errors(self) -> None:
        mem, _, _, _ = _make_memory(episodic=_FakeEpisodic(raise_on_record=True))
        episode = Episode(session_id=uuid4(), summary="boom")
        # Must not raise — memory must never crash the request pipeline.
        out = await mem.record_episode(episode)
        assert out is episode

    async def test_upsert_fact_delegates_to_semantic(self) -> None:
        mem, _, sm, _ = _make_memory()
        fact = Fact(user_id=uuid4(), key="tz", value="Asia/Shanghai")
        out = await mem.upsert_fact(fact)
        assert out is fact
        assert sm.facts == [fact]

    async def test_record_procedure_passes_outcome(self) -> None:
        mem, _, _, pr = _make_memory()
        proc = Procedure(
            name="excel_summary",
            signature="excel_reader+table_to_markdown",
            description="Summarise an uploaded spreadsheet.",
        )
        await mem.record_procedure(
            proc,
            outcome="ok",
            success=True,
            duration_ms=1234,
        )
        assert len(pr.procedures) == 1
        recorded, meta = pr.procedures[0]
        assert recorded is proc
        assert meta == {
            "outcome": "ok",
            "success": True,
            "error": None,
            "duration_ms": 1234,
        }
        status = mem.procedure_write_status()
        assert status["pg_written"] is True
        assert status["vector_written"] is False
        assert status["vector_degraded"] is True

    async def test_record_procedure_status_reports_store_failure(self) -> None:
        mem, _, _, _ = _make_memory(procedural=_FakeProcedural(raise_on_record=True))
        proc = Procedure(
            name="broken",
            signature="broken",
            description="broken procedure",
        )
        out = await mem.record_procedure(proc, outcome="failed", success=False)
        assert out is proc
        status = mem.procedure_write_status()
        assert status["pg_written"] is False
        assert status["vector_written"] is False
        assert status["degraded"] is True


# ---------------------------------------------------------------------------
# Reads — empty bundle fast path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAgentMemoryRecall:
    async def test_empty_query_returns_empty_bundle(self) -> None:
        mem, _, _, _ = _make_memory()
        bundle = await mem.recall("   ")
        assert isinstance(bundle, RecallBundle)
        assert bundle.is_empty()

    async def test_recall_never_raises(self) -> None:
        class _BrokenEmbeddings:
            async def embed_one(self, text: str) -> list[float]:  # noqa: ARG002
                raise RuntimeError("embedding down")

            async def embed_many(self, texts: list[str]) -> list[list[float]]:  # noqa: ARG002
                raise RuntimeError("embedding down")

        mem = AgentMemory(
            episodic=_FakeEpisodic(),  # type: ignore[arg-type]
            semantic=_FakeSemantic(),  # type: ignore[arg-type]
            procedural=_FakeProcedural(),  # type: ignore[arg-type]
            embeddings=_BrokenEmbeddings(),  # type: ignore[arg-type]
        )
        bundle = await mem.recall("anything", user_id=uuid4())
        assert bundle.is_empty()

    async def test_recall_skips_embedding_when_vectors_are_off(self) -> None:
        user_id = uuid4()
        entry = RecallEntry(
            kind=MemoryKind.SEMANTIC,
            text="Remembered preference",
            score=0.5,
            source_id=uuid4(),
        )

        class _OffCollection:
            can_search = False

        class _LexicalStore:
            collection = _OffCollection()

            async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
                raise AssertionError("semantic search should be skipped")

            async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:  # noqa: ARG002
                return [entry]

            async def note_recall(self, source_id: UUID) -> None:  # noqa: ARG002
                return None

        embeddings = _FakeEmbeddings()
        pipeline = RetrievalPipeline(
            episodic=_LexicalStore(),  # type: ignore[arg-type]
            semantic=_LexicalStore(),  # type: ignore[arg-type]
            procedural=_LexicalStore(),  # type: ignore[arg-type]
            embeddings=embeddings,  # type: ignore[arg-type]
        )

        bundle = await pipeline.recall(RecallOptions(query="preference", user_id=user_id))

        assert embeddings.calls == 0
        assert bundle.entries
        assert bundle.entries[0].text == "Remembered preference"


# ---------------------------------------------------------------------------
# RecallHandle
# ---------------------------------------------------------------------------


class _StubMemory:
    """AgentMemory stand-in that counts recall invocations."""

    def __init__(self, result: RecallBundle | Exception) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    async def recall(self, query: str, **kwargs: Any) -> RecallBundle:
        self.calls.append({"query": query, **kwargs})
        if isinstance(self._result, Exception):
            raise self._result
        # Tiny sleep so start() + consume() can exercise the async path.
        await asyncio.sleep(0)
        return self._result


@pytest.mark.asyncio
class TestRecallHandle:
    async def test_consume_caches_result(self) -> None:
        bundle = RecallBundle(query="q")
        bundle.extend(
            [
                RecallEntry(
                    kind=MemoryKind.EPISODIC,
                    text="e1",
                    score=1.0,
                    source_id=uuid4(),
                )
            ]
        )
        mem = _StubMemory(result=bundle)
        handle = RecallHandle(mem)  # type: ignore[arg-type]
        handle.start("q", user_id=uuid4())

        first = await handle.consume()
        second = await handle.consume()
        assert first is second is bundle
        # start() is idempotent per handle.
        handle.start("again")
        assert len(mem.calls) == 1

    async def test_consume_with_failure_returns_empty_bundle(self) -> None:
        mem = _StubMemory(result=RuntimeError("boom"))
        handle = RecallHandle(mem)  # type: ignore[arg-type]
        handle.start("q")
        bundle = await handle.consume()
        assert bundle.is_empty()

    async def test_consume_without_start_returns_empty(self) -> None:
        mem = _StubMemory(result=RecallBundle(query="q"))
        handle = RecallHandle(mem)  # type: ignore[arg-type]
        bundle = await handle.consume()
        assert bundle.is_empty()
        assert mem.calls == []


# ---------------------------------------------------------------------------
# Procedure model
# ---------------------------------------------------------------------------


def test_procedure_accepts_legacy_task_type_keyword() -> None:
    proc = Procedure(
        name="run",
        signature="abc",
        description="d",
        task_type="general",
    )
    assert proc.task_type == "general"
