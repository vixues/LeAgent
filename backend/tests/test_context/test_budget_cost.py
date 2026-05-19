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
