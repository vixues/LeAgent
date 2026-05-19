"""Multi-signal memory formation policy.

Replaces the previous "likes-only" gate for procedural memory with a
scoring system that evaluates multiple signals — tool outcomes, user
feedback, task complexity, explicit memory intent, and repetition — to
decide *what* gets written, *where* (episodic / semantic / procedural),
and at *what importance*.

The public entry point is :class:`FormationPolicy`, consumed by
:meth:`AgentMemory.observe_turn` and the feedback endpoint.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trigger taxonomy
# ---------------------------------------------------------------------------


class TriggerKind(str, Enum):
    """Why a memory formation was considered."""

    TURN_COMPLETE = "turn_complete"
    USER_LIKE = "user_like"
    USER_DISLIKE = "user_dislike"
    EXPLICIT_REMEMBER = "explicit_remember"
    TOOL_SUCCESS = "tool_success"
    TOOL_FAILURE = "tool_failure"
    MULTI_STEP_SUCCESS = "multi_step_success"
    CORRECTION = "correction"
    PREFERENCE_DETECTED = "preference_detected"
    FACT_STATED = "fact_stated"


# ---------------------------------------------------------------------------
# Observation — a snapshot of a turn or feedback event
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TurnObservation:
    """Everything the formation policy needs to score a single event."""

    session_id: UUID
    user_id: UUID | None = None
    workspace_id: UUID | None = None

    user_text: str = ""
    assistant_text: str = ""

    tool_names: list[str] = field(default_factory=list)
    tool_success_count: int = 0
    tool_failure_count: int = 0
    total_steps: int = 0

    trigger: TriggerKind = TriggerKind.TURN_COMPLETE
    tags: list[str] = field(default_factory=list)

    duration_ms: int | None = None
    error: str | None = None

    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scored formation decision
# ---------------------------------------------------------------------------


class FormationTarget(str, Enum):
    """Which memory store(s) should receive the write."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


@dataclass(slots=True)
class FormationDecision:
    """Output of the formation policy — what to write and how important it is."""

    targets: list[FormationTarget] = field(default_factory=list)
    importance: float = 0.0
    confidence: float = 0.5
    provenance: str = ""
    suppress: bool = False
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Intent detection helpers
# ---------------------------------------------------------------------------

_REMEMBER_PATTERNS = re.compile(
    r"(?:请?记住|别忘[了记]|以后.*(?:记得|注意)|remember\b|don'?t forget|keep in mind|note that|always\s)",
    re.IGNORECASE,
)

_PREFERENCE_PATTERNS = re.compile(
    r"(?:我(?:喜欢|偏好|习惯|总是)|i (?:prefer|like|always|want you to)|my (?:preference|style|convention))",
    re.IGNORECASE,
)

_CORRECTION_PATTERNS = re.compile(
    r"(?:不[是对]|错了|纠正|actually|no,?\s*(?:it'?s|that'?s)|wrong|incorrect|correction)",
    re.IGNORECASE,
)


def detect_triggers(obs: TurnObservation) -> list[TriggerKind]:
    """Detect additional implicit triggers from user/assistant text."""
    triggers: list[TriggerKind] = [obs.trigger]
    text = obs.user_text or ""

    if _REMEMBER_PATTERNS.search(text):
        triggers.append(TriggerKind.EXPLICIT_REMEMBER)
    if _PREFERENCE_PATTERNS.search(text):
        triggers.append(TriggerKind.PREFERENCE_DETECTED)
    if _CORRECTION_PATTERNS.search(text):
        triggers.append(TriggerKind.CORRECTION)

    if obs.tool_names:
        if obs.tool_success_count > 0 and obs.tool_failure_count == 0:
            triggers.append(TriggerKind.TOOL_SUCCESS)
        elif obs.tool_failure_count > 0:
            triggers.append(TriggerKind.TOOL_FAILURE)
        if len(obs.tool_names) >= 3 and obs.tool_failure_count == 0:
            triggers.append(TriggerKind.MULTI_STEP_SUCCESS)

    return list(dict.fromkeys(triggers))


# ---------------------------------------------------------------------------
# Formation policy — the scoring engine
# ---------------------------------------------------------------------------

EPISODIC_THRESHOLD = 0.10
PROCEDURAL_THRESHOLD = 0.35
SEMANTIC_THRESHOLD = 0.25

TRIGGER_WEIGHTS: dict[TriggerKind, float] = {
    TriggerKind.TURN_COMPLETE: 0.15,
    TriggerKind.USER_LIKE: 0.40,
    TriggerKind.USER_DISLIKE: -0.10,
    TriggerKind.EXPLICIT_REMEMBER: 0.55,
    TriggerKind.TOOL_SUCCESS: 0.20,
    TriggerKind.TOOL_FAILURE: 0.05,
    TriggerKind.MULTI_STEP_SUCCESS: 0.35,
    TriggerKind.CORRECTION: 0.30,
    TriggerKind.PREFERENCE_DETECTED: 0.40,
    TriggerKind.FACT_STATED: 0.35,
}


class FormationPolicy:
    """Stateless scorer that turns observations into write decisions.

    The policy is deliberately simple and deterministic — no LLM calls.
    The weights can be tuned via subclassing or env-driven config later.
    """

    def __init__(
        self,
        *,
        episodic_threshold: float = EPISODIC_THRESHOLD,
        procedural_threshold: float = PROCEDURAL_THRESHOLD,
        semantic_threshold: float = SEMANTIC_THRESHOLD,
        trigger_weights: dict[TriggerKind, float] | None = None,
    ) -> None:
        self.episodic_threshold = episodic_threshold
        self.procedural_threshold = procedural_threshold
        self.semantic_threshold = semantic_threshold
        self._weights = trigger_weights or dict(TRIGGER_WEIGHTS)

    def evaluate(self, obs: TurnObservation) -> FormationDecision:
        """Score an observation and decide which stores to write to."""
        triggers = detect_triggers(obs)
        raw_score = sum(self._weights.get(t, 0.0) for t in triggers)
        importance = max(0.0, min(1.0, raw_score))

        tool_count = len(obs.tool_names)
        if tool_count >= 2:
            importance = min(1.0, importance + 0.05 * min(tool_count, 6))
        if obs.total_steps >= 4:
            importance = min(1.0, importance + 0.05)

        targets: list[FormationTarget] = []
        reasoning_parts: list[str] = []

        if importance >= self.episodic_threshold:
            targets.append(FormationTarget.EPISODIC)
            reasoning_parts.append("episodic(score meets threshold)")

        has_tools = bool(obs.tool_names)
        tool_success = obs.tool_success_count > 0 and obs.tool_failure_count == 0
        if has_tools and tool_success and importance >= self.procedural_threshold:
            targets.append(FormationTarget.PROCEDURAL)
            reasoning_parts.append("procedural(tools succeeded + score)")

        explicit_semantic = any(
            t in (TriggerKind.EXPLICIT_REMEMBER, TriggerKind.PREFERENCE_DETECTED,
                  TriggerKind.CORRECTION, TriggerKind.FACT_STATED)
            for t in triggers
        )
        if explicit_semantic and importance >= self.semantic_threshold:
            targets.append(FormationTarget.SEMANTIC)
            reasoning_parts.append("semantic(explicit intent detected)")

        suppress = TriggerKind.USER_DISLIKE in triggers and importance <= 0.0
        confidence = min(1.0, 0.3 + importance * 0.7)
        provenance = ",".join(t.value for t in triggers)

        return FormationDecision(
            targets=targets,
            importance=importance,
            confidence=confidence,
            provenance=provenance,
            suppress=suppress,
            reasoning="; ".join(reasoning_parts) or "below all thresholds",
        )

    def score_feedback(
        self,
        *,
        is_like: bool,
        has_tools: bool,
        tool_count: int = 0,
        existing_importance: float = 0.3,
    ) -> FormationDecision:
        """Fast-path scorer for the feedback endpoint (like/dislike)."""
        trigger = TriggerKind.USER_LIKE if is_like else TriggerKind.USER_DISLIKE
        base = self._weights.get(trigger, 0.0) + existing_importance

        if has_tools:
            base += 0.10
            base += 0.03 * min(tool_count, 6)

        importance = max(0.0, min(1.0, base))
        targets: list[FormationTarget] = []

        if is_like:
            targets.append(FormationTarget.EPISODIC)
            if has_tools and importance >= self.procedural_threshold:
                targets.append(FormationTarget.PROCEDURAL)
        else:
            targets.append(FormationTarget.EPISODIC)

        return FormationDecision(
            targets=targets,
            importance=importance,
            confidence=min(1.0, 0.5 + importance * 0.5),
            provenance=trigger.value,
            suppress=not is_like and importance <= 0.0,
            reasoning="feedback-path like" if is_like else "feedback-path dislike",
        )


# ---------------------------------------------------------------------------
# Retention scoring (for maintenance / decay)
# ---------------------------------------------------------------------------


def retention_score(
    *,
    importance: float,
    recall_count: int,
    age_days: float,
    success_rate: float | None = None,
    confidence: float | None = None,
    half_life_days: float = 60.0,
) -> float:
    """Compute a 0–1 retention score for an existing memory entry.

    Used by maintenance jobs to decide what to keep, consolidate, or prune.
    Higher = more worth retaining.
    """
    import math

    base = max(0.0, min(1.0, importance))
    recall_boost = min(0.3, 0.03 * recall_count)
    recency = math.exp(-age_days / max(1.0, half_life_days))

    score = 0.35 * base + 0.25 * recall_boost + 0.25 * recency
    if confidence is not None:
        score += 0.15 * max(0.0, min(1.0, confidence))
    else:
        score += 0.075
    if success_rate is not None:
        score *= 0.5 + 0.5 * max(0.0, min(1.0, success_rate))
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Helpers used by AgentMemory.observe_turn
# ---------------------------------------------------------------------------


def build_episode_summary(obs: TurnObservation, *, max_len: int = 1200) -> str:
    """Build an episode summary string from an observation."""
    user = (obs.user_text or "").strip()[:400]
    assistant = (obs.assistant_text or "").strip()[:800]
    summary = f"Q: {user}\nA: {assistant}" if user and assistant else user or assistant
    if obs.tool_names:
        show = obs.tool_names[:32]
        tail = "" if len(obs.tool_names) <= 32 else f" (+{len(obs.tool_names) - 32} more)"
        summary += f"\nTools: {', '.join(show)}{tail}"
    return summary[:max_len]


def build_procedure_signature(obs: TurnObservation) -> str:
    """Deterministic digest for a procedure from an observation."""
    intent = (obs.user_text or "").strip().lower()[:200]
    tools = sorted({t.strip() for t in obs.tool_names if t.strip()})
    payload = intent + "\x00" + ",".join(tools)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "FormationDecision",
    "FormationPolicy",
    "FormationTarget",
    "TriggerKind",
    "TurnObservation",
    "build_episode_summary",
    "build_procedure_signature",
    "detect_triggers",
    "retention_score",
]
