"""Tests for multi-file HTML canvas merge + publish wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from leagent.services.canvas.html_bundle import merge_html_files_to_document
from leagent.services.canvas.service import sanitize_html


def test_merge_html_files_inlines_css_and_js() -> None:
    files = {
        "index.html": (
            "<!DOCTYPE html><html><head>"
            '<link rel="stylesheet" href="style.css"/>'
            '</head><body><script src="app.js"></script></body></html>'
        ),
        "style.css": "body { color: red; }",
        "app.js": "console.log(1);",
    }
    merged = merge_html_files_to_document(
        entry="index.html",
        files=files,
        max_output_bytes=256 * 1024,
    )
    assert "body { color: red; }" in merged
    assert "console.log(1);" in merged
    assert '<link rel="stylesheet"' not in merged
    out = sanitize_html(merged, max_bytes=256 * 1024)
    assert "color: red" in out


def test_merge_html_files_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="Unsafe"):
        merge_html_files_to_document(
            entry="../x.html",
            files={"../x.html": "a"},
            max_output_bytes=1024,
        )


@pytest.mark.asyncio
async def test_publish_revision_accepts_html_files(monkeypatch: pytest.MonkeyPatch) -> None:
    from uuid import uuid4

    from leagent.services.canvas.service import CanvasService

    session_id = uuid4()
    user_id = uuid4()

    async def _assert_ok(*_a: object, **_k: object) -> MagicMock:
        m = MagicMock()
        m.workspace_id = None
        return m

    db = MagicMock()
    db.session = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(), __aexit__=AsyncMock()))
    inner = AsyncMock()
    inner.execute = AsyncMock(
        return_value=MagicMock(scalar_one=MagicMock(return_value=None)),
    )
    inner.get = AsyncMock(return_value=None)
    inner.add = MagicMock()
    inner.flush = AsyncMock()
    inner.refresh = AsyncMock()
    db.session.return_value.__aenter__.return_value = inner

    settings = MagicMock()
    settings.canvas.max_html_bytes = 512 * 1024
    settings.canvas.embed_allow_loopback = True
    settings.canvas.max_tree_depth = 8
    settings.canvas.max_nodes_per_tree = 100
    settings.canvas.max_ui_snapshot_bytes = 1024

    chat = MagicMock()
    chat.get_session = AsyncMock(side_effect=_assert_ok)

    svc = CanvasService(settings, db, chat=chat)
    monkeypatch.setattr(
        "leagent.services.canvas.service.mint_preview_token",
        lambda *_a, **_k: "tok",
    )
    monkeypatch.setattr(
        "leagent.services.canvas.service.preview_query_path",
        lambda _t: "/api/v1/canvas/preview?token=t",
    )

    out = await svc.publish_revision(
        user_id=user_id,
        session_id=session_id,
        title="t",
        mode="html",
        html=None,
        html_files={
            "index.html": "<!DOCTYPE html><html><body>ok</body></html>",
        },
        html_bundle_entry="index.html",
    )
    assert out["canvas_id"]
    inner.add.assert_called_once()


@pytest.mark.asyncio
async def test_tool_argument_blob_persist_disk_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.util import tool_argument_blob as m
    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobStore, ToolArgumentBlobTool

    sid = "sess-persist-test"

    monkeypatch.setattr(m, "_persist_enabled", lambda: True)
    monkeypatch.setattr(
        m,
        "_blob_disk_path",
        lambda session_id, blob_id: (tmp_path / "tblobs" / session_id / f"{blob_id}.bin").resolve(),
    )

    ctx = ToolContext(user_id="u1", session_id=sid, extra={})
    tool = ToolArgumentBlobTool()
    created = await tool.run({"action": "create"}, ctx)
    assert created.success
    bid = str(created.data["blob_id"])
    app = await tool.run({"action": "append", "blob_id": bid, "chunk": "disk-roundtrip"}, ctx)
    assert app.success and app.data.get("ok") is True
    fin = await tool.run({"action": "finalize", "blob_id": bid}, ctx)
    assert fin.success and fin.data.get("persisted") is True

    text = await ToolArgumentBlobStore.take_utf8_text(sid, bid)
    assert text == "disk-roundtrip"
    p = (tmp_path / "tblobs" / sid / f"{bid}.bin").resolve()
    assert not p.is_file()
    assert await ToolArgumentBlobStore.take_utf8_text(sid, bid) is None
