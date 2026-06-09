"""Tests for ``tools.code.operations`` — Pydantic operation models + journal."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from leagent.code.operations import (
    CodeExecOp,
    FileEditOp,
    FilePatchOp,
    FileWriteOp,
    JournalEntry,
    OperationJournal,
    PatchedFile,
    JOURNAL_CONTEXT_KEY,
)


# ---------------------------------------------------------------------------
# FileWriteOp
# ---------------------------------------------------------------------------


class TestFileWriteOp:
    def test_round_trip_defaults(self) -> None:
        op = FileWriteOp(path="src/app.py")
        d = op.model_dump()
        assert d["path"] == "src/app.py"
        assert d["bytes_written"] == 0
        assert d["created"] is False
        assert d["artifact_id"] is None
        rebuilt = FileWriteOp.model_validate(d)
        assert rebuilt == op

    def test_full_fields(self) -> None:
        op = FileWriteOp(
            path="src/app.py",
            bytes_written=123,
            lines=10,
            created=True,
            overwrite=False,
            source_length=123,
            artifact_id="art-1",
            syntax_valid=True,
            language="python",
            kind="file_write",
            target_path="src/app.py",
        )
        d = op.model_dump()
        assert d["syntax_valid"] is True
        assert d["language"] == "python"


# ---------------------------------------------------------------------------
# FileEditOp
# ---------------------------------------------------------------------------


class TestFileEditOp:
    def test_round_trip(self) -> None:
        op = FileEditOp(
            path="src/util.py",
            replacements=2,
            new_size=456,
            diff="--- a\n+++ b\n@@ ...",
        )
        d = op.model_dump()
        assert d["replacements"] == 2
        rebuilt = FileEditOp.model_validate(d)
        assert rebuilt.diff == op.diff


# ---------------------------------------------------------------------------
# FilePatchOp
# ---------------------------------------------------------------------------


class TestFilePatchOp:
    def test_round_trip(self) -> None:
        op = FilePatchOp(
            files=[
                PatchedFile(path="a.py", is_new=True),
                PatchedFile(path="b.py", is_deleted=True),
            ],
            count=2,
        )
        d = op.model_dump()
        assert len(d["files"]) == 2
        assert d["files"][0]["is_new"] is True
        rebuilt = FilePatchOp.model_validate(d)
        assert rebuilt.count == 2


# ---------------------------------------------------------------------------
# CodeExecOp
# ---------------------------------------------------------------------------


class TestCodeExecOp:
    def test_round_trip(self) -> None:
        op = CodeExecOp(
            status="ok",
            stdout="hello\n",
            duration_ms=42,
            workspace="/tmp/ws",
        )
        d = op.model_dump()
        assert d["status"] == "ok"
        assert d["stdout"] == "hello\n"

    def test_error_fields(self) -> None:
        op = CodeExecOp(
            status="error",
            error="NameError: x",
            error_type="runtime",
        )
        d = op.model_dump()
        assert d["error_type"] == "runtime"


# ---------------------------------------------------------------------------
# JournalEntry
# ---------------------------------------------------------------------------


class TestJournalEntry:
    def test_timestamp_auto_filled(self) -> None:
        before = time.time()
        entry = JournalEntry(tool="project_write", kind="file_write")
        after = time.time()
        assert before <= entry.timestamp <= after

    def test_explicit_fields(self) -> None:
        entry = JournalEntry(
            tool="project_edit",
            kind="file_edit",
            path="src/app.py",
            summary="2 replacement(s)",
            success=True,
            artifact_id="art-2",
            verification="passed",
        )
        assert entry.verification == "passed"


# ---------------------------------------------------------------------------
# OperationJournal
# ---------------------------------------------------------------------------


class TestOperationJournal:
    def test_append_increments_seq(self) -> None:
        journal = OperationJournal()
        e1 = journal.append(JournalEntry(tool="a", kind="x"))
        e2 = journal.append(JournalEntry(tool="b", kind="y"))
        assert e1.seq == 1
        assert e2.seq == 2
        assert len(journal) == 2

    def test_truncation(self) -> None:
        journal = OperationJournal(max_entries=3)
        for i in range(10):
            journal.append(JournalEntry(tool=f"t{i}", kind="k"))
        assert len(journal) == 3
        recent = journal.recent(10)
        assert recent[0].tool == "t7"
        assert recent[-1].tool == "t9"

    def test_recent_returns_copy(self) -> None:
        journal = OperationJournal()
        journal.append(JournalEntry(tool="a", kind="x"))
        r1 = journal.recent()
        r2 = journal.recent()
        assert r1 is not r2
        assert r1 == r2

    def test_summary_text_empty(self) -> None:
        journal = OperationJournal()
        assert journal.summary_text() == ""

    def test_summary_text_formatting(self) -> None:
        journal = OperationJournal()
        journal.append(JournalEntry(
            tool="project_write", kind="file_write",
            path="src/app.py", success=True,
        ))
        journal.append(JournalEntry(
            tool="code_execution", kind="execute",
            success=False, verification="syntax_error",
        ))
        text = journal.summary_text()
        assert "## Recent operations" in text
        assert "`project_write`" in text
        assert "FAIL" in text
        assert "[syntax_error]" in text

    def test_context_key_is_string(self) -> None:
        assert isinstance(JOURNAL_CONTEXT_KEY, str)
        assert JOURNAL_CONTEXT_KEY.startswith("_")


# ---------------------------------------------------------------------------
# resolve_content helper
# ---------------------------------------------------------------------------


class TestResolveContent:
    @pytest.mark.asyncio
    async def test_inline_content(self) -> None:
        from leagent.project.fs import resolve_content

        ctx = SimpleNamespace(extra={})
        text = await resolve_content(
            {"content": "hello world"}, ctx,
        )
        assert text == "hello world"

    @pytest.mark.asyncio
    async def test_empty_raises(self) -> None:
        from leagent.project.fs import resolve_content

        ctx = SimpleNamespace(extra={})
        with pytest.raises(ValueError, match="non-empty"):
            await resolve_content({"content": ""}, ctx)

    @pytest.mark.asyncio
    async def test_allow_empty(self) -> None:
        from leagent.project.fs import resolve_content

        ctx = SimpleNamespace(extra={})
        text = await resolve_content(
            {"content": ""}, ctx, allow_empty=True,
        )
        assert text == ""

    @pytest.mark.asyncio
    async def test_custom_keys(self) -> None:
        from leagent.project.fs import resolve_content

        ctx = SimpleNamespace(extra={})
        text = await resolve_content(
            {"source": "print(1)"}, ctx,
            inline_key="source", blob_key="source_blob_id",
        )
        assert text == "print(1)"

    @pytest.mark.asyncio
    async def test_missing_both_raises(self) -> None:
        from leagent.project.fs import resolve_content

        ctx = SimpleNamespace(extra={})
        with pytest.raises(ValueError):
            await resolve_content({}, ctx)


# ---------------------------------------------------------------------------
# record_operation helper
# ---------------------------------------------------------------------------


class TestRecordOperation:
    def test_records_to_journal(self) -> None:
        from leagent.code.pipeline import record_operation

        journal = OperationJournal()
        ctx = SimpleNamespace(extra={JOURNAL_CONTEXT_KEY: journal})
        record_operation(
            ctx,
            tool="project_write",
            kind="file_write",
            path="src/app.py",
            summary="created (100 bytes)",
        )
        assert len(journal) == 1
        entry = journal.recent()[0]
        assert entry.tool == "project_write"
        assert entry.path == "src/app.py"

    def test_noop_without_journal(self) -> None:
        from leagent.code.pipeline import record_operation

        ctx = SimpleNamespace(extra={})
        record_operation(ctx, tool="x", kind="y")


# ---------------------------------------------------------------------------
# SessionArtifactsSource with journal
# ---------------------------------------------------------------------------


class TestSessionArtifactsSourceWithJournal:
    @pytest.mark.asyncio
    async def test_includes_journal_text(self) -> None:
        from leagent.context.sources.session_artifacts import (
            SessionArtifactsSource,
        )
        from leagent.context.sources.base import ResolveContext

        journal = OperationJournal()
        journal.append(JournalEntry(
            tool="project_write", kind="file_write",
            path="foo.py", success=True,
        ))
        ctx = ResolveContext(
            session_id=uuid4(),
            operation_journal=journal,
        )
        source = SessionArtifactsSource()
        block = await source.resolve(ctx)
        assert block is not None
        assert "Recent operations" in block.body
        assert "`project_write`" in block.body

    @pytest.mark.asyncio
    async def test_returns_none_when_empty(self) -> None:
        from leagent.context.sources.session_artifacts import (
            SessionArtifactsSource,
        )
        from leagent.context.sources.base import ResolveContext

        ctx = ResolveContext(session_id=uuid4())
        source = SessionArtifactsSource()
        block = await source.resolve(ctx)
        assert block is None
