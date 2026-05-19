"""Tests for the multi-signal memory formation policy.

Covers:
- Trigger detection from user text (remember, preference, correction)
- Formation scoring across trigger combinations
- Threshold gating for episodic / procedural / semantic targets
- Feedback scoring (like / dislike)
- Retention scoring for maintenance
- observe_turn integration with fake stores
- observe_feedback integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

from leagent.memory.formation import (
    EPISODIC_THRESHOLD,
    FormationDecision,
    FormationPolicy,
    FormationTarget,
    PROCEDURAL_THRESHOLD,
    SEMANTIC_THRESHOLD,
    TriggerKind,
    TurnObservation,
    build_episode_summary,
    build_procedure_signature,
    detect_triggers,
    retention_score,
)

# ---------------------------------------------------------------------------
# Trigger detection
# ---------------------------------------------------------------------------


class TestDetectTriggers:
    def test_plain_turn_complete(self) -> None:
        obs = TurnObservation(session_id=uuid4(), user_text="hello")
        triggers = detect_triggers(obs)
        assert TriggerKind.TURN_COMPLETE in triggers
        assert TriggerKind.EXPLICIT_REMEMBER not in triggers

    def test_remember_english(self) -> None:
        obs = TurnObservation(session_id=uuid4(), user_text="Please remember my timezone is UTC+8")
        triggers = detect_triggers(obs)
        assert TriggerKind.EXPLICIT_REMEMBER in triggers

    def test_remember_chinese(self) -> None:
        obs = TurnObservation(session_id=uuid4(), user_text="请记住我的时区是UTC+8")
        triggers = detect_triggers(obs)
        assert TriggerKind.EXPLICIT_REMEMBER in triggers

    def test_preference_detected(self) -> None:
        obs = TurnObservation(session_id=uuid4(), user_text="I prefer dark mode")
        triggers = detect_triggers(obs)
        assert TriggerKind.PREFERENCE_DETECTED in triggers

    def test_correction_detected(self) -> None:
        obs = TurnObservation(session_id=uuid4(), user_text="No, that's wrong, the file is at /tmp")
        triggers = detect_triggers(obs)
        assert TriggerKind.CORRECTION in triggers

    def test_tool_success(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            tool_names=["read_file"],
            tool_success_count=1,
            tool_failure_count=0,
        )
        triggers = detect_triggers(obs)
        assert TriggerKind.TOOL_SUCCESS in triggers

    def test_multi_step_success(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            tool_names=["read_file", "summarize", "write_file"],
            tool_success_count=3,
            tool_failure_count=0,
        )
        triggers = detect_triggers(obs)
        assert TriggerKind.MULTI_STEP_SUCCESS in triggers

    def test_tool_failure(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            tool_names=["read_file"],
            tool_success_count=0,
            tool_failure_count=1,
        )
        triggers = detect_triggers(obs)
        assert TriggerKind.TOOL_FAILURE in triggers
        assert TriggerKind.TOOL_SUCCESS not in triggers

    def test_deduplicates_triggers(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            trigger=TriggerKind.TURN_COMPLETE,
            user_text="remember this",
        )
        triggers = detect_triggers(obs)
        assert len(triggers) == len(set(triggers))


# ---------------------------------------------------------------------------
# Formation policy scoring
# ---------------------------------------------------------------------------


class TestFormationPolicy:
    def setup_method(self) -> None:
        self.policy = FormationPolicy()

    def test_simple_turn_produces_episodic(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            user_text="Hello",
            assistant_text="Hi there!",
        )
        decision = self.policy.evaluate(obs)
        assert FormationTarget.EPISODIC in decision.targets
        assert decision.importance >= EPISODIC_THRESHOLD

    def test_simple_turn_does_not_produce_procedural(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            user_text="Hello",
            assistant_text="Hi there!",
        )
        decision = self.policy.evaluate(obs)
        assert FormationTarget.PROCEDURAL not in decision.targets

    def test_multi_tool_success_produces_procedural(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            user_text="Summarize the document",
            assistant_text="Done.",
            tool_names=["read_file", "summarize", "write_file"],
            tool_success_count=3,
            tool_failure_count=0,
            total_steps=6,
        )
        decision = self.policy.evaluate(obs)
        assert FormationTarget.PROCEDURAL in decision.targets
        assert FormationTarget.EPISODIC in decision.targets

    def test_remember_intent_produces_semantic(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            user_id=uuid4(),
            user_text="Please remember my timezone is UTC+8",
            assistant_text="Got it!",
        )
        decision = self.policy.evaluate(obs)
        assert FormationTarget.SEMANTIC in decision.targets

    def test_preference_produces_semantic(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            user_id=uuid4(),
            user_text="I prefer dark mode for all code editors",
            assistant_text="Noted.",
        )
        decision = self.policy.evaluate(obs)
        assert FormationTarget.SEMANTIC in decision.targets

    def test_tool_failure_does_not_produce_procedural(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            user_text="read the file",
            assistant_text="error",
            tool_names=["read_file"],
            tool_success_count=0,
            tool_failure_count=1,
        )
        decision = self.policy.evaluate(obs)
        assert FormationTarget.PROCEDURAL not in decision.targets

    def test_dislike_suppresses_when_score_nonpositive(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            trigger=TriggerKind.USER_DISLIKE,
            user_text="",
            assistant_text="",
        )
        decision = self.policy.evaluate(obs)
        assert decision.suppress is True or decision.importance <= 0.0

    def test_custom_thresholds(self) -> None:
        policy = FormationPolicy(
            episodic_threshold=0.99,
            procedural_threshold=0.99,
            semantic_threshold=0.99,
        )
        obs = TurnObservation(
            session_id=uuid4(),
            user_text="just a hello",
            assistant_text="hi",
        )
        decision = policy.evaluate(obs)
        assert decision.targets == []


# ---------------------------------------------------------------------------
# Feedback scoring
# ---------------------------------------------------------------------------


class TestFeedbackScoring:
    def setup_method(self) -> None:
        self.policy = FormationPolicy()

    def test_like_with_tools_produces_procedural(self) -> None:
        decision = self.policy.score_feedback(
            is_like=True,
            has_tools=True,
            tool_count=3,
        )
        assert FormationTarget.PROCEDURAL in decision.targets
        assert FormationTarget.EPISODIC in decision.targets
        assert decision.importance > 0.5

    def test_like_without_tools_no_procedural(self) -> None:
        decision = self.policy.score_feedback(
            is_like=True,
            has_tools=False,
        )
        assert FormationTarget.PROCEDURAL not in decision.targets
        assert FormationTarget.EPISODIC in decision.targets

    def test_dislike_produces_episodic_only(self) -> None:
        decision = self.policy.score_feedback(
            is_like=False,
            has_tools=True,
            tool_count=2,
        )
        assert FormationTarget.PROCEDURAL not in decision.targets
        assert FormationTarget.EPISODIC in decision.targets


# ---------------------------------------------------------------------------
# Retention scoring
# ---------------------------------------------------------------------------


class TestRetentionScore:
    def test_high_importance_high_recalls_recent(self) -> None:
        score = retention_score(
            importance=0.9,
            recall_count=10,
            age_days=1.0,
        )
        assert score > 0.5

    def test_low_importance_old_no_recalls(self) -> None:
        score = retention_score(
            importance=0.01,
            recall_count=0,
            age_days=365.0,
        )
        assert score < 0.15

    def test_success_rate_boosts_score(self) -> None:
        base = retention_score(
            importance=0.5, recall_count=3, age_days=30.0
        )
        with_success = retention_score(
            importance=0.5, recall_count=3, age_days=30.0, success_rate=1.0
        )
        assert with_success >= base

    def test_bounded_0_to_1(self) -> None:
        score = retention_score(importance=1.0, recall_count=100, age_days=0.0)
        assert 0.0 <= score <= 1.0
        score2 = retention_score(importance=0.0, recall_count=0, age_days=9999.0)
        assert 0.0 <= score2 <= 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_build_episode_summary(self) -> None:
        obs = TurnObservation(
            session_id=uuid4(),
            user_text="What is 2+2?",
            assistant_text="4",
            tool_names=["calculator"],
        )
        summary = build_episode_summary(obs)
        assert "Q:" in summary
        assert "A:" in summary
        assert "calculator" in summary

    def test_build_procedure_signature_deterministic(self) -> None:
        obs1 = TurnObservation(
            session_id=uuid4(),
            user_text="read the file",
            tool_names=["read_file", "summarize"],
        )
        obs2 = TurnObservation(
            session_id=uuid4(),
            user_text="read the file",
            tool_names=["summarize", "read_file"],
        )
        assert build_procedure_signature(obs1) == build_procedure_signature(obs2)

    def test_build_procedure_signature_differs_for_different_intent(self) -> None:
        obs1 = TurnObservation(
            session_id=uuid4(),
            user_text="read the file",
            tool_names=["read_file"],
        )
        obs2 = TurnObservation(
            session_id=uuid4(),
            user_text="delete the file",
            tool_names=["read_file"],
        )
        assert build_procedure_signature(obs1) != build_procedure_signature(obs2)


# ---------------------------------------------------------------------------
# observe_turn integration (using fakes from test_agent_memory.py pattern)
# ---------------------------------------------------------------------------

from leagent.memory.agent_memory import AgentMemory
from leagent.memory.types import Episode, Fact, Procedure, RecallBundle, RecallEntry
from leagent.memory.vector import VectorWriteResult


@dataclass
class _FakeEpisodic:
    episodes: list[Episode] = field(default_factory=list)

    async def record(self, episode: Episode) -> Episode:
        self.episodes.append(episode)
        return episode

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:
        return []

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:
        return []

    async def note_recall(self, source_id: UUID) -> None:
        pass


@dataclass
class _FakeSemantic:
    facts: list[Fact] = field(default_factory=list)

    async def upsert(self, fact: Fact) -> Fact:
        self.facts.append(fact)
        return fact

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:
        return []

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:
        return []


@dataclass
class _FakeProcedural:
    procedures: list[tuple[Procedure, dict[str, Any]]] = field(default_factory=list)
    last_vector_write: VectorWriteResult | None = None

    async def record(
        self, procedure: Procedure, *, outcome: str, success: bool,
        error: str | None = None, duration_ms: int | None = None,
    ) -> Procedure:
        self.procedures.append((procedure, {"outcome": outcome, "success": success}))
        self.last_vector_write = VectorWriteResult(written=False, degraded=True, error="test")
        return procedure

    async def semantic_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:
        return []

    async def lexical_search(self, *a: Any, **kw: Any) -> list[RecallEntry]:
        return []


@dataclass
class _FakeEmbeddings:
    async def embed_one(self, text: str) -> list[float]:
        return [0.0] * 8

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def _make_memory() -> tuple[AgentMemory, _FakeEpisodic, _FakeSemantic, _FakeProcedural]:
    ep = _FakeEpisodic()
    sm = _FakeSemantic()
    pr = _FakeProcedural()
    mem = AgentMemory(
        episodic=ep,  # type: ignore[arg-type]
        semantic=sm,  # type: ignore[arg-type]
        procedural=pr,  # type: ignore[arg-type]
        embeddings=_FakeEmbeddings(),  # type: ignore[arg-type]
    )
    return mem, ep, sm, pr


@pytest.mark.asyncio
class TestObserveTurn:
    async def test_simple_turn_writes_episodic(self) -> None:
        mem, ep, sm, pr = _make_memory()
        obs = TurnObservation(
            session_id=uuid4(),
            user_text="What is Python?",
            assistant_text="A programming language.",
        )
        decision = await mem.observe_turn(obs)
        assert FormationTarget.EPISODIC in decision.targets
        assert len(ep.episodes) == 1
        assert "Python" in ep.episodes[0].summary

    async def test_multi_tool_writes_procedural(self) -> None:
        mem, ep, sm, pr = _make_memory()
        obs = TurnObservation(
            session_id=uuid4(),
            user_text="Summarize the doc",
            assistant_text="Done.",
            tool_names=["read_file", "summarize", "write_file"],
            tool_success_count=3,
            tool_failure_count=0,
            total_steps=6,
        )
        decision = await mem.observe_turn(obs)
        assert FormationTarget.PROCEDURAL in decision.targets
        assert len(pr.procedures) == 1

    async def test_remember_intent_writes_semantic(self) -> None:
        mem, ep, sm, pr = _make_memory()
        uid = uuid4()
        obs = TurnObservation(
            session_id=uuid4(),
            user_id=uid,
            user_text="Please remember that I prefer tabs over spaces",
            assistant_text="Got it!",
        )
        decision = await mem.observe_turn(obs)
        assert FormationTarget.SEMANTIC in decision.targets
        assert len(sm.facts) == 1
        assert "tabs" in sm.facts[0].value.lower()

    async def test_observe_turn_never_raises(self) -> None:
        """Even with a broken policy, observe_turn must not crash."""
        class _BrokenPolicy:
            def evaluate(self, obs: Any) -> Any:
                raise RuntimeError("boom")
            def score_feedback(self, **kw: Any) -> Any:
                raise RuntimeError("boom")

        mem, *_ = _make_memory()
        mem._formation = _BrokenPolicy()  # type: ignore[assignment]
        obs = TurnObservation(session_id=uuid4(), user_text="hello")
        decision = await mem.observe_turn(obs)
        assert decision.suppress is True

    async def test_suppressed_turn_writes_nothing(self) -> None:
        mem, ep, sm, pr = _make_memory()
        obs = TurnObservation(
            session_id=uuid4(),
            trigger=TriggerKind.USER_DISLIKE,
            user_text="",
            assistant_text="",
        )
        decision = await mem.observe_turn(obs)
        assert len(ep.episodes) == 0
        assert len(pr.procedures) == 0


@pytest.mark.asyncio
class TestObserveFeedback:
    async def test_like_feedback_returns_procedural_target(self) -> None:
        mem, *_ = _make_memory()
        decision = await mem.observe_feedback(
            is_like=True,
            has_tools=True,
            tool_count=3,
        )
        assert FormationTarget.PROCEDURAL in decision.targets

    async def test_dislike_feedback_no_procedural(self) -> None:
        mem, *_ = _make_memory()
        decision = await mem.observe_feedback(
            is_like=False,
            has_tools=True,
            tool_count=2,
        )
        assert FormationTarget.PROCEDURAL not in decision.targets

    async def test_observe_feedback_never_raises(self) -> None:
        class _BrokenPolicy:
            def evaluate(self, obs: Any) -> Any:
                raise RuntimeError("boom")
            def score_feedback(self, **kw: Any) -> Any:
                raise RuntimeError("boom")

        mem, *_ = _make_memory()
        mem._formation = _BrokenPolicy()  # type: ignore[assignment]
        decision = await mem.observe_feedback(is_like=True, has_tools=False)
        assert decision.suppress is True
