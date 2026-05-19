"""Tests for shared session attachment ToolContext.extra construction."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_tool_extra_for_chat_session_includes_normalized_paths(tmp_path: Path) -> None:
    from leagent.tools.session_attachment_context import tool_extra_for_chat_session

    f = tmp_path / "doc.txt"
    f.write_text("hello")
    resolved_path = str(f.resolve())

    att_id = uuid4()

    class _Att:
        id = att_id
        filename = "doc.txt"
        storage_path = resolved_path

    class _SM:
        async def list_attachments(self, _sid):  # noqa: ANN001
            return [_Att]

    extra = await tool_extra_for_chat_session(_SM(), uuid4())
    assert extra["attachments"] == [resolved_path]
    assert "attachment_lookup" in extra
    assert extra["attachment_lookup"]["by_id"][str(att_id)] == resolved_path


@pytest.mark.asyncio
async def test_tool_extra_for_chat_session_merges_extra_paths(tmp_path: Path) -> None:
    from leagent.tools.session_attachment_context import tool_extra_for_chat_session

    a = tmp_path / "a.txt"
    a.write_text("a")
    b = tmp_path / "b.txt"
    b.write_text("b")
    ra, rb = str(a.resolve()), str(b.resolve())

    att = SimpleNamespace(id=uuid4(), filename="a.txt", storage_path=ra)

    class _SM:
        async def list_attachments(self, _sid):  # noqa: ANN001
            return [att]

    extra = await tool_extra_for_chat_session(_SM(), uuid4(), extra_paths=[rb])
    assert set(extra["attachments"]) == {ra, rb}
