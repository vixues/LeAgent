from __future__ import annotations

import pytest

from leagent.context.budget import minimise, PINNED_THRESHOLD
from leagent.context.types import ContextBlock, RenderTarget


def _block(sid, size, priority=500, weight=1.0):
    body = "x" * size
    return ContextBlock(
        source_id=sid,
        kind="identity",
        render_target=RenderTarget.SYSTEM,
        body=body,
        tokens=size // 3,
        cost=size,
        signature=f"{sid}:sig",
        priority=priority,
        weight=weight,
    )


def test_pinned_blocks_survive():
    blocks = [_block("id", 100, 2000), _block("low", 900, 200)]
    r = minimise(blocks, max_chars=110)
    assert any(b.source_id == "id" for b in r.kept)
    assert "low" in r.dropped or "low" in r.truncated


def test_deterministic_tiebreak():
    blocks = [_block("b_src", 50, 500), _block("a_src", 50, 500)]
    r1 = minimise(blocks, max_chars=60)
    r2 = minimise(list(reversed(blocks)), max_chars=60)
    kept1 = [b.source_id for b in r1.kept]
    kept2 = [b.source_id for b in r2.kept]
    assert kept1 == kept2


def test_empty_input():
    r = minimise([], max_chars=100)
    assert r.kept == []


def test_source_hard_budget_truncates_oversized_fragment():
    from leagent.context.budget import (
        DEFAULT_SOURCE_HARD_CAP_CHARS,
        enforce_source_hard_budgets,
    )

    huge = _block("tool_history", DEFAULT_SOURCE_HARD_CAP_CHARS + 5_000)
    out, truncated = enforce_source_hard_budgets([huge])
    assert truncated == ["tool_history"]
    assert out[0].cost <= 12_000  # SOURCE_HARD_CAPS["tool_history"]
    assert "truncated by context budget" in out[0].body


def test_source_hard_budget_respects_default_cap():
    from leagent.context.budget import (
        DEFAULT_SOURCE_HARD_CAP_CHARS,
        enforce_source_hard_budgets,
    )

    # Unknown source uses the default ~10K-token ceiling.
    huge = _block("identity", DEFAULT_SOURCE_HARD_CAP_CHARS + 1000, priority=2000)
    out, truncated = enforce_source_hard_budgets([huge])
    assert truncated == ["identity"]
    assert out[0].cost <= DEFAULT_SOURCE_HARD_CAP_CHARS


def test_source_hard_budget_leaves_small_blocks():
    from leagent.context.budget import enforce_source_hard_budgets

    small = _block("policies", 100)
    out, truncated = enforce_source_hard_budgets([small])
    assert truncated == []
    assert out[0].body == small.body


def test_fragment_under_10k_tokens_after_hard_budget():
    """Lint: after hard-budget enforcement every fragment is ≤ ~10K tokens."""
    from leagent.context.budget import (
        DEFAULT_SOURCE_HARD_CAP_CHARS,
        enforce_source_hard_budgets,
    )

    blocks = [
        _block("tool_history", 80_000),
        _block("identity", 50_000, priority=2000),
        _block("recent_reads", 40_000),
    ]
    out, _ = enforce_source_hard_budgets(blocks)
    for b in out:
        assert b.tokens <= (DEFAULT_SOURCE_HARD_CAP_CHARS // 3) + 50
        assert b.cost <= DEFAULT_SOURCE_HARD_CAP_CHARS

