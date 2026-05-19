from __future__ import annotations

from leagent.context.cache import SourceCache
from leagent.context.types import ContextBlock, ContextScope, RenderTarget


def _block(sid="test"):
    return ContextBlock(
        source_id=sid,
        kind="identity",
        render_target=RenderTarget.SYSTEM,
        body="hello",
        tokens=2,
        cost=5,
        signature="sig",
        priority=500,
        weight=1.0,
    )


def test_put_get_session():
    cache = SourceCache()
    cache.put("k1", _block())
    assert cache.get("k1", ContextScope.SESSION) is not None
    assert cache.stats["hits"] == 1


def test_turn_scope_never_cached():
    cache = SourceCache()
    cache.put("k1", _block())
    assert cache.get("k1", ContextScope.TURN) is None
    assert cache.stats["misses"] == 1


def test_invalidate():
    cache = SourceCache()
    cache.put("k1", _block())
    cache.invalidate("k1")
    assert cache.get("k1", ContextScope.SESSION) is None
