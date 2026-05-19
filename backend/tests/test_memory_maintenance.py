"""Tests for the updated maintenance module (consolidation, decay, retention).

Covers:
- consolidate_notable_episodes with dedup_existing
- retention_score consistency
- RecallSource context-budget caps (type-capped formatting)
- Recall pipeline semantic-over-episodic collapse
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from leagent.memory.formation import retention_score
from leagent.memory.recall import RetrievalPipeline, RecallOptions
from leagent.memory.types import (
    Episode,
    Fact,
    MemoryKind,
    RecallBundle,
    RecallEntry,
)

# ---------------------------------------------------------------------------
# Retention score edge cases
# ---------------------------------------------------------------------------


class TestRetentionScoreEdgeCases:
    def test_zero_age_high_importance(self) -> None:
        score = retention_score(importance=1.0, recall_count=5, age_days=0.0)
        assert score > 0.6

    def test_max_decay(self) -> None:
        score = retention_score(importance=0.0, recall_count=0, age_days=10000.0)
        assert score < 0.15

    def test_confidence_matters(self) -> None:
        low = retention_score(
            importance=0.5, recall_count=1, age_days=10.0, confidence=0.1
        )
        high = retention_score(
            importance=0.5, recall_count=1, age_days=10.0, confidence=0.95
        )
        assert high > low

    def test_success_rate_matters(self) -> None:
        low = retention_score(
            importance=0.5, recall_count=1, age_days=10.0, success_rate=0.1
        )
        high = retention_score(
            importance=0.5, recall_count=1, age_days=10.0, success_rate=1.0
        )
        assert high > low


# ---------------------------------------------------------------------------
# Recall pipeline: semantic-over-episodic collapse
# ---------------------------------------------------------------------------


class TestSemanticOverEpisodicCollapse:
    def test_identical_text_prefers_semantic(self) -> None:
        entries = [
            RecallEntry(
                kind=MemoryKind.EPISODIC,
                text="User prefers dark mode",
                score=0.8,
                source_id=uuid4(),
            ),
            RecallEntry(
                kind=MemoryKind.SEMANTIC,
                text="User prefers dark mode",
                score=0.7,
                source_id=uuid4(),
            ),
        ]
        collapsed = RetrievalPipeline._collapse_semantic_over_episodic(entries)
        assert len(collapsed) == 1
        assert collapsed[0].kind is MemoryKind.SEMANTIC

    def test_different_text_keeps_both(self) -> None:
        entries = [
            RecallEntry(
                kind=MemoryKind.EPISODIC,
                text="User asked about Python",
                score=0.8,
                source_id=uuid4(),
            ),
            RecallEntry(
                kind=MemoryKind.SEMANTIC,
                text="User prefers dark mode",
                score=0.7,
                source_id=uuid4(),
            ),
        ]
        collapsed = RetrievalPipeline._collapse_semantic_over_episodic(entries)
        assert len(collapsed) == 2

    def test_no_semantic_entries_returns_all(self) -> None:
        entries = [
            RecallEntry(
                kind=MemoryKind.EPISODIC,
                text="turn summary",
                score=0.8,
                source_id=uuid4(),
            ),
            RecallEntry(
                kind=MemoryKind.PROCEDURAL,
                text="tool chain",
                score=0.6,
                source_id=uuid4(),
            ),
        ]
        collapsed = RetrievalPipeline._collapse_semantic_over_episodic(entries)
        assert len(collapsed) == 2


# ---------------------------------------------------------------------------
# RecallBundle formatting caps
# ---------------------------------------------------------------------------


class TestRecallBundleFormatting:
    def test_to_prompt_block_caps_lines(self) -> None:
        bundle = RecallBundle(query="test")
        for i in range(20):
            bundle.extend([
                RecallEntry(
                    kind=MemoryKind.EPISODIC,
                    text=f"entry {i}",
                    score=0.5,
                    source_id=uuid4(),
                ),
            ])
        block = bundle.to_prompt_block(max_lines=5)
        lines = [l for l in block.split("\n") if l.startswith("- (")]
        assert len(lines) == 5

    def test_empty_bundle_returns_empty_string(self) -> None:
        bundle = RecallBundle(query="test")
        assert bundle.to_prompt_block() == ""


# ---------------------------------------------------------------------------
# Recall pipeline dedup: text-based near-duplicate collapse
# ---------------------------------------------------------------------------


class TestRecallDedup:
    def test_near_duplicate_text_collapsed(self) -> None:
        @dataclass
        class _FakeStore:
            async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:
                return []
            async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:
                return []
            async def note_recall(self, *a: Any) -> None:
                pass

        @dataclass
        class _FakeEmbeddings:
            async def embed_one(self, text: str) -> list[float]:
                return [0.0] * 8

        pipeline = RetrievalPipeline(
            episodic=_FakeStore(),  # type: ignore[arg-type]
            semantic=_FakeStore(),  # type: ignore[arg-type]
            procedural=_FakeStore(),  # type: ignore[arg-type]
            embeddings=_FakeEmbeddings(),  # type: ignore[arg-type]
        )

        ranked = [
            RecallEntry(kind=MemoryKind.EPISODIC, text="same text here", score=0.9, source_id=uuid4()),
            RecallEntry(kind=MemoryKind.EPISODIC, text="same text here", score=0.8, source_id=uuid4()),
            RecallEntry(kind=MemoryKind.SEMANTIC, text="different fact", score=0.7, source_id=uuid4()),
        ]
        deduped = pipeline._deduplicate(ranked, file_state=None)
        assert len(deduped) == 2
        texts = {e.text for e in deduped}
        assert "same text here" in texts
        assert "different fact" in texts
