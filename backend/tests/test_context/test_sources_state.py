from __future__ import annotations

import pytest

from leagent.context.sources.base import ResolveContext
from leagent.context.sources.recent_reads import RecentReadsSource
from leagent.context.types import RenderTarget


class _MockFileState:
    def recent_paths(self, *, limit=5):
        return ["/tmp/a.py", "/tmp/b.py"]


@pytest.mark.asyncio
async def test_recent_reads_emits_attachment():
    ctx = ResolveContext(file_state=_MockFileState())
    block = await RecentReadsSource().resolve(ctx)
    assert block is not None
    assert block.render_target == RenderTarget.ATTACHMENT_USER
    assert "recent_reads" in block.body
    assert "/tmp/a.py" in block.body
    assert block.signature


@pytest.mark.asyncio
async def test_recent_reads_returns_none_when_empty():
    class _Empty:
        def recent_paths(self, *, limit=5):
            return []

    ctx = ResolveContext(file_state=_Empty())
    block = await RecentReadsSource().resolve(ctx)
    assert block is None
