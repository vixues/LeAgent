"""Terminal and continue transitions for the query loop (maps ``query/transitions.ts``).

The inner ``query_loop`` in :mod:`leagent.agent.query` is a state
machine: every iteration either keeps going (with a diagnostic
``Continue`` reason describing *why*) or exits (with a ``Terminal``
reason describing the final state). Callers — notably
:class:`leagent.agent.query_engine.QueryEngine` — inspect the
``Terminal`` to decide how to surface the outcome to the SDK consumer
(normal completion, abort, model error, token-budget exceeded, ...).

Keeping these values as string enums makes them easy to log and
serialise (SDK messages quote the raw string), while the wrapper
dataclasses carry structured metadata (``meta``) alongside the reason
so recovery branches can pass diagnostic details without threading
extra arguments through the loop body.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TerminalReason(str, Enum):
    """Why the outer query loop exited.

    Values mirror the reference TypeScript loop so logs and telemetry
    line up cross-language:

    - ``COMPLETED``: the assistant produced a final answer with no
      outstanding tool calls.
    - ``MAX_TURNS``: we hit ``QueryParams.max_turns`` without converging.
    - ``BLOCKING_LIMIT``: a hook or guard (rate limit, budget) halted
      the loop.
    - ``MODEL_ERROR``: streaming raised or the provider returned an
      unrecoverable error frame.
    - ``ABORTED_STREAMING``: the abort event was set mid-stream.
    - ``PROMPT_TOO_LONG``: compaction could not shrink the prompt
      enough to fit the model context window.
    - ``TOKEN_BUDGET_EXCEEDED``: usage accumulators passed a configured
      ceiling.
    - ``AWAITING_USER_INPUT``: the model called ``ask_user``; the loop
      exits without dispatching tools until the client supplies tool
      results on the next turn.
    """

    COMPLETED = "completed"
    MAX_TURNS = "max_turns"
    BLOCKING_LIMIT = "blocking_limit"
    MODEL_ERROR = "model_error"
    ABORTED_STREAMING = "aborted_streaming"
    PROMPT_TOO_LONG = "prompt_too_long"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    AWAITING_USER_INPUT = "awaiting_user_input"


class ContinueReason(str, Enum):
    """Why an iteration continued.

    These are purely diagnostic — the loop restarts regardless. They
    exist so tests and telemetry can assert which recovery path fired:

    - ``NEXT_TURN``: normal "model requested tools, we ran them, back to
      the top" path.
    - ``COLLAPSE_DRAIN_RETRY``: queued events had to be drained before
      re-issuing the call.
    - ``REACTIVE_COMPACT_RETRY``: we compacted and are retrying.
    - ``MAX_OUTPUT_TOKENS_RECOVERY``: the stream truncated on length;
      we bumped ``max_output_tokens`` and retry.
    - ``TOKEN_BUDGET_CONTINUATION``: resumed after a budget throttle.
    """

    NEXT_TURN = "next_turn"
    COLLAPSE_DRAIN_RETRY = "collapse_drain_retry"
    REACTIVE_COMPACT_RETRY = "reactive_compact_retry"
    MAX_OUTPUT_TOKENS_RECOVERY = "max_output_tokens_recovery"
    TOKEN_BUDGET_CONTINUATION = "token_budget_continuation"


@dataclass(frozen=True)
class Continue:
    """Diagnostic carry-over between query loop iterations.

    Stored on :class:`leagent.agent.state.QueryState.transition` so the
    next iteration can log *why* it was kicked off and, if relevant,
    read out ``meta`` fields set by the previous iteration (e.g. the
    new token budget during a ``MAX_OUTPUT_TOKENS_RECOVERY``).
    """

    reason: ContinueReason
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Terminal:
    """Final outcome of ``query()`` / ``query_loop()``.

    The query loop yields exactly one ``Terminal`` right before it
    returns. ``QueryEngine`` translates it into an SDK ``result`` frame
    and short-circuits any downstream processing.
    """

    reason: TerminalReason
    meta: dict[str, Any] = field(default_factory=dict)
