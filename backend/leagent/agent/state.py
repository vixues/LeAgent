"""Mutable cross-iteration state for ``query_loop``.

Mirrors the ``State`` type in the reference ``query.ts``: every time the
loop iterates (normal turn, recovery retry, compaction retry), a new
``QueryState`` is rebuilt from the previous one. The dataclass captures
only data that legitimately changes between iterations; session-scoped
state (conversation history, file cache, usage totals) stays on
:class:`leagent.agent.query_engine.QueryEngine`.

This explicit, immutable-at-a-glance shape is what makes the
"continue" pattern in :func:`leagent.agent.query._query_loop` safe
to reason about — the current iteration can only observe values that
were deliberately carried forward, instead of mutating shared locals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from leagent.agent.transitions import Continue

if TYPE_CHECKING:
    from leagent.agent.tool_use_context import ToolUseContext


@dataclass
class AutoCompactTrackingState:
    """Minimal autocompact bookkeeping.

    Extended by ``memory.compact`` when it needs to track retry policy.
    Defaults keep the loop runnable even without compaction configured.
    """

    consecutive_failures: int = 0
    last_compact_tokens_saved: int = 0


@dataclass
class QueryState:
    """Per-loop state mirrored from TypeScript ``query.ts`` ``State``.

    Attributes:
        messages: Running conversation history (list of OpenAI-format
            message dicts). Replaced, not mutated, on every iteration.
        tool_use_context: Shared :class:`ToolUseContext` threaded into
            every tool call and the model stream.
        auto_compact_tracking: Diagnostic counters used by autocompact
            to decide when to give up.
        max_output_tokens_recovery_count: Number of times we've bumped
            ``max_output_tokens`` due to a ``finish_reason=="length"``
            truncation. Bounded to avoid infinite retry.
        has_attempted_reactive_compact: True once we've tried to
            compact in response to a prompt-too-long error this turn.
        max_output_tokens_override: If set, the next model call uses
            this value instead of ``QueryParams.max_output_tokens``.
        pending_tool_use_summary: Placeholder for TS parity; unused in
            the current Python loop but kept so downstream hooks can
            attach structured tool summaries without schema churn.
        turn_count: 1-indexed turn counter; incremented on
            ``NEXT_TURN`` transitions only.
        transition: The :class:`Continue` record that caused this
            iteration (``None`` on first entry).
    """

    messages: list[dict[str, Any]]
    tool_use_context: "ToolUseContext"
    auto_compact_tracking: AutoCompactTrackingState | None = None
    max_output_tokens_recovery_count: int = 0
    has_attempted_reactive_compact: bool = False
    max_output_tokens_override: int | None = None
    pending_tool_use_summary: Any = None  # unused stub (TS parity)
    turn_count: int = 1
    transition: Continue | None = None
