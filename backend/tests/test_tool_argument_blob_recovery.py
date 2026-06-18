"""Tests for the Blob System Overhaul: recovery, create_and_finalize, streaming ingest."""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from leagent.tools.base import ToolContext
from leagent.tools.executor import (
    _recover_tool_argument_blob_args,
    _try_parse_raw_tool_args,
    parse_tool_arguments_str,
)
from leagent.agent.deps import _try_blob_streaming_ingest, _try_direct_content_ingest
from leagent.tools.util.tool_argument_blob import (
    ToolArgumentBlobStore,
    ToolArgumentBlobTool,
    resolve_blob_text,
)


def _ctx(session_id: str = "test-session") -> ToolContext:
    return ToolContext(user_id="u1", session_id=session_id)


# ---------------------------------------------------------------------------
# Phase 1: _recover_tool_argument_blob_args
# ---------------------------------------------------------------------------


class TestRecoverToolArgumentBlobArgs:
    def test_recovers_broken_html_chunk(self) -> None:
        raw = (
            '{"action":"append","blob_id":"abc123",'
            '"chunk":"<div class="hero"><h1>Hello</h1></div>"}'
        )
        result = _recover_tool_argument_blob_args(raw)
        assert result is not None
        assert result["action"] == "append"
        assert result["blob_id"] == "abc123"
        assert "chunk" in result
        assert "<div" in result["chunk"]

    def test_preserves_valid_chunk_base64(self) -> None:
        payload = base64.b64encode(b"<h1>Test</h1>").decode()
        raw = json.dumps({
            "action": "append",
            "blob_id": "xyz789",
            "chunk_base64": payload,
        })
        result = _recover_tool_argument_blob_args(raw)
        assert result is not None
        assert result["chunk_base64"] == payload
        assert result["blob_id"] == "xyz789"

    def test_returns_none_for_non_blob_action(self) -> None:
        raw = '{"action":"finalize","blob_id":"abc123"}'
        assert _recover_tool_argument_blob_args(raw) is None

    def test_returns_none_for_unrelated_tool(self) -> None:
        raw = '{"source":"print(1)","timeout_sec":30}'
        assert _recover_tool_argument_blob_args(raw) is None

    def test_recovers_create_and_finalize_action(self) -> None:
        raw = (
            '{"action":"create_and_finalize",'
            '"chunk":"<div style="color:red">x</div>"}'
        )
        result = _recover_tool_argument_blob_args(raw)
        assert result is not None
        assert result["action"] == "create_and_finalize"
        assert "chunk" in result

    def test_empty_chunk_returns_none(self) -> None:
        raw = '{"action":"append","blob_id":"b1","chunk":""}'
        assert _recover_tool_argument_blob_args(raw) is None

    def test_wired_into_try_parse_raw(self) -> None:
        raw = (
            '{"action":"append","blob_id":"abc123",'
            '"chunk":"<div class="test">broken json</div>"}'
        )
        result = parse_tool_arguments_str(raw)
        assert result is not None
        assert result["action"] == "append"
        assert "chunk" in result

    def test_recovers_multiline_jsx_chunk(self) -> None:
        """Malformed multiline JSX — recovery extracts as much as it can."""
        raw = (
            '{"action":"append","blob_id":"m1",'
            '"chunk":"<div className=\\"wrapper\\">\\n  <span>Hello</span>\\n</div>"}'
        )
        result = _recover_tool_argument_blob_args(raw)
        assert result is not None
        decoded = result["chunk"]
        assert "wrapper" in decoded


# ---------------------------------------------------------------------------
# Phase 3: create_and_finalize action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateAndFinalize:
    def setup_method(self, method: Any = None) -> None:
        ToolArgumentBlobStore._blobs.clear()

    async def test_create_and_finalize_with_chunk(self) -> None:
        tool = ToolArgumentBlobTool()
        ctx = _ctx()
        result = await tool.execute(
            {"action": "create_and_finalize", "chunk": "hello world"},
            ctx,
        )
        assert result["ok"] is True
        assert "blob_id" in result
        assert result["total_bytes"] == len(b"hello world")

        text = await ToolArgumentBlobStore.take_utf8_text(
            ctx.session_id, result["blob_id"],
        )
        assert text == "hello world"

    async def test_create_and_finalize_with_chunk_base64(self) -> None:
        tool = ToolArgumentBlobTool()
        ctx = _ctx()
        encoded = base64.b64encode("café résumé".encode("utf-8")).decode("ascii")
        result = await tool.execute(
            {"action": "create_and_finalize", "chunk_base64": encoded},
            ctx,
        )
        assert result["ok"] is True
        blob_id = result["blob_id"]
        text = await ToolArgumentBlobStore.take_utf8_text(ctx.session_id, blob_id)
        assert text == "café résumé"

    async def test_create_and_finalize_missing_chunk_returns_error(self) -> None:
        tool = ToolArgumentBlobTool()
        result = await tool.execute(
            {"action": "create_and_finalize"},
            _ctx(),
        )
        assert result["ok"] is False
        assert "error" in result

    async def test_create_and_finalize_chunk_ingested(self) -> None:
        tool = ToolArgumentBlobTool()
        result = await tool.execute(
            {
                "action": "create_and_finalize",
                "blob_id": "pre-created-id",
                "_chunk_ingested": True,
                "_ingested_bytes": 42,
            },
            _ctx(),
        )
        assert result["ok"] is True
        assert result["total_bytes"] == 42
        assert "streamed directly" in result.get("note", "")


# ---------------------------------------------------------------------------
# Phase 4: _chunk_ingested flag on append
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestChunkIngestedFlag:
    def setup_method(self, method: Any = None) -> None:
        ToolArgumentBlobStore._blobs.clear()

    async def test_append_with_chunk_ingested_skips_append(self) -> None:
        tool = ToolArgumentBlobTool()
        ctx = _ctx()
        blob_id = await ToolArgumentBlobStore.create(ctx.session_id)
        result = await tool.execute(
            {
                "action": "append",
                "blob_id": blob_id,
                "_chunk_ingested": True,
                "_ingested_bytes": 100,
            },
            ctx,
        )
        assert result["ok"] is True
        assert result["total_bytes"] == 100
        assert "streamed directly" in result.get("note", "")


# ---------------------------------------------------------------------------
# Phase 4: streaming ingest via deps.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBlobStreamingIngest:
    def setup_method(self, method: Any = None) -> None:
        ToolArgumentBlobStore._blobs.clear()

    async def test_streaming_ingest_append(self) -> None:
        from leagent.agent.deps import _try_blob_streaming_ingest

        sid = "stream-test-session"
        blob_id = await ToolArgumentBlobStore.create(sid)

        raw = (
            '{"action":"append","blob_id":"' + blob_id + '",'
            '"chunk":"<div class="broken">content</div>"}'
        )
        result = await _try_blob_streaming_ingest("tool_argument_blob", raw)
        assert result is not None
        assert result["_chunk_ingested"] is True
        assert result["blob_id"] == blob_id
        assert result["_ingested_bytes"] > 0

    async def test_streaming_ingest_create_and_finalize(self) -> None:
        from leagent.agent.deps import _try_blob_streaming_ingest

        raw = (
            '{"action":"create_and_finalize",'
            '"chunk":"<p style="font-size:12px">Hello</p>"}'
        )
        result = await _try_blob_streaming_ingest("tool_argument_blob", raw)
        assert result is not None
        assert result["action"] == "create_and_finalize"
        assert result["_chunk_ingested"] is True
        assert "blob_id" in result

    async def test_streaming_ingest_ignores_non_blob_tool(self) -> None:
        from leagent.agent.deps import _try_blob_streaming_ingest

        result = await _try_blob_streaming_ingest("code_execution", '{"source":"x"}')
        assert result is None

    async def test_streaming_ingest_ignores_non_append_action(self) -> None:
        from leagent.agent.deps import _try_blob_streaming_ingest

        result = await _try_blob_streaming_ingest(
            "tool_argument_blob", '{"action":"finalize","blob_id":"x"}',
        )
        assert result is None

    async def test_streaming_ingest_truncated_base64_partial_blob(self) -> None:
        """Truncated base64 in create_and_finalize saves partial content, not finalized."""
        from leagent.agent.deps import _try_blob_streaming_ingest

        full_html = "<p>Hello world from truncated ingest</p>"
        valid_b64 = base64.b64encode(full_html.encode()).decode()
        # Simulate LLM output cut mid-base64 (invalid padding / incomplete group)
        truncated_b64 = valid_b64[: len(valid_b64) - 3]
        raw = (
            '{"action":"create_and_finalize",'
            f'"chunk_base64":"{truncated_b64}"'
        )
        result = await _try_blob_streaming_ingest("tool_argument_blob", raw)
        assert result is not None
        assert result.get("_truncated") is True
        assert result.get("_chunk_ingested") is True
        blob_id = result["blob_id"]
        # Blob must exist but not be finalized (take without finalize returns None)
        sid = "__streaming_ingest__"
        text = await ToolArgumentBlobStore.take_utf8_text(sid, blob_id)
        assert text is None


# ---------------------------------------------------------------------------
# find_session_for_blob
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFindSessionForBlob:
    def setup_method(self, method: Any = None) -> None:
        ToolArgumentBlobStore._blobs.clear()

    async def test_finds_existing_blob(self) -> None:
        sid = "find-session-test"
        blob_id = await ToolArgumentBlobStore.create(sid)
        found = await ToolArgumentBlobStore.find_session_for_blob(blob_id)
        assert found == sid

    async def test_returns_none_for_finalized_blob(self) -> None:
        sid = "finalized-test"
        blob_id = await ToolArgumentBlobStore.create(sid)
        await ToolArgumentBlobStore.append(sid, blob_id, "data")
        await ToolArgumentBlobStore.finalize(sid, blob_id)
        found = await ToolArgumentBlobStore.find_session_for_blob(blob_id)
        assert found is None

    async def test_returns_none_for_unknown_blob(self) -> None:
        found = await ToolArgumentBlobStore.find_session_for_blob("nonexistent")
        assert found is None


# ---------------------------------------------------------------------------
# Session-scoped ingest + resolve
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIngestSessionResolution:
    def setup_method(self, method: Any = None) -> None:
        ToolArgumentBlobStore._blobs.clear()

    async def test_direct_content_ingest_resolves_with_real_session(self) -> None:
        sid = "real-session-direct-ingest"
        raw = (
            '{"title":"Landing","mode":"html",'
            '"html":"<html><body>Hello</body></html>"'
        )
        result = await _try_direct_content_ingest(
            "canvas_publish",
            raw,
            session_id=sid,
        )
        assert result is not None
        assert "html_blob_id" in result
        assert "html" not in result
        text = await resolve_blob_text(_ctx(sid), str(result["html_blob_id"]))
        assert "Hello" in text

    async def test_streaming_create_and_finalize_real_session_consumable(self) -> None:
        sid = "real-session-stream-caf"
        html = "<p>Hi</p>"
        b64 = base64.b64encode(html.encode()).decode()
        raw = f'{{"action":"create_and_finalize","chunk_base64":"{b64}"}}'
        result = await _try_blob_streaming_ingest(
            "tool_argument_blob",
            raw,
            session_id=sid,
        )
        assert result is not None
        blob_id = result["blob_id"]
        text = await resolve_blob_text(_ctx(sid), blob_id)
        assert text == html

    async def test_resolve_blob_legacy_streaming_ingest_session(self) -> None:
        legacy_sid = "__streaming_ingest__"
        real_sid = "user-session-legacy"
        blob_id = await ToolArgumentBlobStore.create(legacy_sid)
        await ToolArgumentBlobStore.append(legacy_sid, blob_id, "<p>legacy</p>")
        await ToolArgumentBlobStore.finalize(legacy_sid, blob_id)
        text = await resolve_blob_text(_ctx(real_sid), blob_id)
        assert text == "<p>legacy</p>"

    async def test_find_any_session_for_finalized_blob(self) -> None:
        sid = "finalized-any-session"
        blob_id = await ToolArgumentBlobStore.create(sid)
        await ToolArgumentBlobStore.append(sid, blob_id, "data")
        await ToolArgumentBlobStore.finalize(sid, blob_id)
        found = await ToolArgumentBlobStore.find_any_session_for_blob(blob_id)
        assert found == sid
