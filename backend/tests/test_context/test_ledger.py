from __future__ import annotations

from leagent.context.ledger import ContextLedger, LedgerRow


def test_to_structlog_dict():
    row = LedgerRow(
        source_id="identity",
        bytes=100,
        tokens=33,
        cache_hit=True,
        skip_reason="",
        truncated=False,
        dropped=False,
        render_target="system",
        priority=2000,
    )
    ledger = ContextLedger(
        rows=[row],
        stable_hash="abc",
        full_hash="def",
        duration_ms=42,
    )
    d = ledger.to_structlog_dict()
    assert d["stable_hash"] == "abc"
    assert len(d["sources"]) == 1
    assert d["sources"][0]["id"] == "identity"
    assert d["prepare_duration_ms"] == 42
