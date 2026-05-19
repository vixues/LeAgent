"""Tests for the PathSandbox and tool-level path enforcement.

Verifies that tools reject paths outside the configured sandbox roots
and allow paths within them. Also tests the env-var override mechanism.
"""

from __future__ import annotations

import pytest

# Standalone desktop builds use unrestricted path resolution (see paths.py).
pytestmark = pytest.mark.skip(
    reason="Path sandbox strict-mode tests do not apply to unrestricted standalone builds.",
)

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from leagent.tools._sandbox.paths import PathSandbox, reset_roots
from leagent.tools.base import ToolContext, ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(attachments: list[str] | None = None) -> ToolContext:
    ctx = ToolContext(user_id="u1", session_id="s1")
    if attachments:
        ctx.extra["attachments"] = attachments
    return ctx


def _ctx_with_lookup(
    *,
    attachments: list[str] | None = None,
    by_id: dict[str, str] | None = None,
    by_name: dict[str, str] | None = None,
) -> ToolContext:
    ctx = _ctx(attachments=attachments)
    ctx.extra["attachment_lookup"] = {
        "by_id": by_id or {},
        "by_name": by_name or {},
    }
    return ctx


@pytest.fixture(autouse=True)
def _reset_sandbox():
    """Save/restore LEAGENT_TOOL_FILE_ROOTS so tests don't leak env state."""
    saved = os.environ.get("LEAGENT_TOOL_FILE_ROOTS")
    reset_roots()
    yield
    if saved is None:
        os.environ.pop("LEAGENT_TOOL_FILE_ROOTS", None)
    else:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = saved
    reset_roots()


# ===========================================================================
# PathSandbox unit tests
# ===========================================================================


class TestPathSandbox:
    def test_empty_path_rejected(self):
        with pytest.raises(PermissionError, match="Empty path"):
            PathSandbox.resolve_safe("", context=_ctx())

    def test_dot_rejected(self):
        with pytest.raises(PermissionError, match="not allowed"):
            PathSandbox.resolve_safe(".", context=_ctx())

    def test_slash_rejected(self):
        with pytest.raises(PermissionError, match="not allowed"):
            PathSandbox.resolve_safe("/", context=_ctx())

    def test_dotdot_rejected(self):
        with pytest.raises(PermissionError, match="not allowed"):
            PathSandbox.resolve_safe("..", context=_ctx())

    def test_path_outside_sandbox_rejected(self):
        with pytest.raises(PermissionError, match="outside the allowed sandbox"):
            PathSandbox.resolve_safe("/etc/passwd", context=_ctx())

    def test_project_source_rejected(self):
        with pytest.raises(PermissionError):
            PathSandbox.resolve_safe(
                "/home/user/project/backend/leagent/main.py",
                context=_ctx(),
            )

    def test_path_inside_default_root_allowed(self, tmp_path: Path):
        test_file = tmp_path / "test.xlsx"
        test_file.write_text("hello")

        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        result = PathSandbox.resolve_safe(str(test_file), context=_ctx())
        assert result == test_file.resolve()

    def test_path_inside_default_root_subdir(self, tmp_path: Path):
        subdir = tmp_path / "sub" / "deep"
        subdir.mkdir(parents=True)
        test_file = subdir / "data.csv"
        test_file.write_text("a,b,c")

        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        result = PathSandbox.resolve_safe(str(test_file), context=_ctx())
        assert result == test_file.resolve()

    def test_attachment_path_allowed(self, tmp_path: Path):
        att_file = tmp_path / "attachment.pdf"
        att_file.write_text("pdf bytes")

        ctx = _ctx(attachments=[str(att_file)])
        result = PathSandbox.resolve_safe(str(att_file), context=ctx)
        assert result == att_file.resolve()

    def test_env_override_multiple_roots(self, tmp_path: Path):
        root_a = tmp_path / "a"
        root_b = tmp_path / "b"
        root_a.mkdir()
        root_b.mkdir()
        file_a = root_a / "f.txt"
        file_b = root_b / "g.txt"
        file_a.write_text("a")
        file_b.write_text("b")

        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = f"{root_a},{root_b}"
        reset_roots()

        assert PathSandbox.resolve_safe(str(file_a), context=_ctx()) == file_a.resolve()
        assert PathSandbox.resolve_safe(str(file_b), context=_ctx()) == file_b.resolve()

    def test_is_safe_mirror(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        f = tmp_path / "ok.txt"
        f.write_text("ok")

        assert PathSandbox.is_safe(str(f), context=_ctx()) is True
        assert PathSandbox.is_safe("/etc/shadow", context=_ctx()) is False

    def test_allow_create_for_new_file(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        new_file = tmp_path / "output" / "result.docx"
        result = PathSandbox.resolve_safe(
            str(new_file), context=_ctx(), allow_create=True,
        )
        assert result == new_file.resolve()

    def test_bare_filename_resolved_to_session_dir(self, tmp_path: Path):
        """A bare filename like '工作簿1.csv' resolves inside the session upload dir."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()
        target = session_dir / "data.csv"
        target.write_text("a,b")

        result = PathSandbox.resolve_safe("data.csv", context=_ctx())
        assert result == target.resolve()

    def test_bare_filename_not_found_rejected(self, tmp_path: Path):
        """A bare filename that doesn't exist under any root is rejected."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        with pytest.raises(PermissionError):
            PathSandbox.resolve_safe("nonexistent.csv", context=_ctx())

    def test_attachment_uuid_prefixed_name_alias_resolves(self, tmp_path: Path):
        """Original uploaded filename resolves to UUID-prefixed storage path."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()
        stored = session_dir / "123e4567_notes.txt"
        stored.write_text("attachment content")

        ctx = _ctx(attachments=[str(stored)])
        result = PathSandbox.resolve_safe("notes.txt", context=ctx)
        assert result == stored.resolve()

    def test_attachment_alias_case_and_punctuation_drift_resolves(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()
        stored = session_dir / "123e4567_Budget_Report_2026.xlsx"
        stored.write_text("attachment content")

        ctx = _ctx(attachments=[str(stored)])
        result = PathSandbox.resolve_safe("budget report 2026.xlsx", context=ctx)
        assert result == stored.resolve()

    def test_non_path_attachment_context_entries_ignored(self, tmp_path: Path):
        """Non-path entries (e.g. IDs) in context.attachments are ignored."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()
        stored = session_dir / "123e4567_report.xlsx"
        stored.write_text("xlsx content")

        # Simulate upstream contract violation: mixed IDs and paths.
        ctx = _ctx(attachments=["66d0522f-0f8d-4a65-a0dd-a657d0db3856", str(stored)])
        result = PathSandbox.resolve_safe("report.xlsx", context=ctx)
        assert result == stored.resolve()

    def test_attachment_id_lookup_resolves(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()
        stored = session_dir / "123e4567_report.xlsx"
        stored.write_text("xlsx content")

        ctx = _ctx_with_lookup(
            attachments=[str(stored)],
            by_id={"f-123": str(stored)},
        )
        result = PathSandbox.resolve_safe("f-123", context=ctx)
        assert result == stored.resolve()

    def test_file_reference_token_with_id_resolves(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()
        stored = session_dir / "123e4567_budget.xlsx"
        stored.write_text("xlsx content")

        ctx = _ctx_with_lookup(
            attachments=[str(stored)],
            by_id={"file-42": str(stored)},
            by_name={"budgetxlsx": str(stored)},
        )
        result = PathSandbox.resolve_safe("@file:budget.xlsx#file-42", context=ctx)
        assert result == stored.resolve()

    def test_knowledge_reference_token_resolves(self, tmp_path: Path):
        """@knowledge:name#uuid resolves via attachment_lookup.by_id (knowledge merge)."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        kid = uuid.uuid4()
        stored = tmp_path / f"{kid}_article.doc"
        stored.write_text("hello")

        ctx = _ctx_with_lookup(
            attachments=[str(stored)],
            by_id={str(kid): str(stored)},
        )
        result = PathSandbox.resolve_safe(
            f"@knowledge:article.doc#{kid}",
            context=ctx,
        )
        assert result == stored.resolve()

    def test_bare_cjk_filename_resolves_via_controller_suffix_aliases(
        self, tmp_path: Path,
    ) -> None:
        """Bare original name matches ``<uuid>_原名`` when lookup built like AgentController."""
        from unittest.mock import MagicMock

        from leagent.tools.session_attachment_context import build_attachment_lookup

        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        kid = uuid.uuid4()
        stored = (tmp_path / f"{kid}_工作簿1.csv").resolve()
        stored.write_text("a,b\n1,2")

        lookup = build_attachment_lookup(
            session_attachments=[],
            normalized_attachments=[str(stored)],
        )
        ctx = _ctx_with_lookup(
            attachments=[str(stored)],
            by_id=lookup.get("by_id") or {},
            by_name=lookup.get("by_name") or {},
        )
        result = PathSandbox.resolve_safe("工作簿1.csv", context=ctx)
        assert result == stored

    def test_bare_filename_with_allow_create(self, tmp_path: Path):
        """A bare filename with allow_create resolves even if file doesn't exist."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()

        result = PathSandbox.resolve_safe(
            "output.xlsx", context=_ctx(), allow_create=True,
        )
        assert result == (session_dir / "output.xlsx").resolve()

    def test_bare_filename_allow_create_prefers_uuid_stored_file(
        self, tmp_path: Path,
    ) -> None:
        """allow_create on read-style tools must not skip ``uuid_<name>`` on disk."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        session_dir = (tmp_path / sid).resolve()
        session_dir.mkdir(parents=True)
        kid = uuid.uuid4()
        stored = session_dir / f"{kid}_工作簿1.csv"
        stored.write_text("a,b")

        ctx = ToolContext(user_id="u1", session_id=sid)
        out = PathSandbox.resolve_safe("工作簿1.csv", context=ctx, allow_create=True)
        assert out == stored.resolve()

    def test_bare_file_uuid_resolves_uuid_prefixed_filename(
        self, tmp_path: Path,
    ) -> None:
        """Bare document UUID (no extension) maps to ``<uuid>_<name>`` without by_id."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        sid = "891e5d6f-c0a2-442a-bcbf-5d45cc55ed51"
        session_dir = (tmp_path / sid).resolve()
        session_dir.mkdir(parents=True)
        kid = uuid.UUID("ab2faf02-fff5-47e3-8548-cc05cb6bf614")
        stored = session_dir / f"{kid}_工作簿1.csv"
        stored.write_text("a,b")

        ctx = ToolContext(user_id="u1", session_id=sid)
        out = PathSandbox.resolve_safe(str(kid), context=ctx, allow_create=False)
        assert out == stored.resolve()

    def test_absolute_logical_path_maps_uuid_prefixed_session_file(
        self, tmp_path: Path,
    ) -> None:
        """Model passes ``uploads/<sid>/<name>`` but disk has ``<sid>/<uuid>_<name>``."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        sid = "76e97645-9cfe-4c15-8c57-38318563909e"
        session_dir = (tmp_path / sid).resolve()
        session_dir.mkdir(parents=True)
        kid = uuid.uuid4()
        stored = session_dir / f"{kid}_工作簿1.csv"
        stored.write_text("a,b\n1,2")

        logical = (session_dir / "工作簿1.csv").resolve()
        assert not logical.is_file()

        ctx = ToolContext(user_id="u1", session_id=sid)
        out = PathSandbox.resolve_safe(str(logical), context=ctx, allow_create=False)
        assert out == stored.resolve()

    def test_authorized_roots_allow_nested_file(self, tmp_path: Path):
        """Session ``authorized_roots`` widens the sandbox like ``project_roots``."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()
        granted = tmp_path / "granted"
        granted.mkdir()
        inner = granted / "inner.txt"
        inner.write_text("ok")
        ctx = ToolContext(user_id="u1", session_id=str(uuid.uuid4()))
        ctx.extra["authorized_roots"] = [str(granted.resolve())]
        out = PathSandbox.resolve_safe(str(inner), context=ctx, allow_create=False)
        assert out == inner.resolve()


# ===========================================================================
# Tool-level sandbox enforcement (file_manager and text_processor)
# ===========================================================================


async def _run_file_manager(params: dict[str, Any], ctx: ToolContext) -> ToolResult:
    from leagent.tools.util.file_manager import FileManagerTool
    tool = FileManagerTool()
    return await tool.run(params, ctx)


async def _run_text_processor(params: dict[str, Any], ctx: ToolContext) -> ToolResult:
    from leagent.tools.doc.text_processor import TextFileProcessorTool
    tool = TextFileProcessorTool()
    return await tool.run(params, ctx)


@pytest.mark.asyncio
class TestFileManagerSandbox:
    async def test_tree_on_virtual_root_resolves_to_session_dir(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir(exist_ok=True)
        (session_dir / "a.txt").write_text("a")

        result = await _run_file_manager(
            {"operation": "tree", "path": "."}, _ctx(),
        )
        assert result.success

    async def test_list_on_slash_resolves_to_session_dir(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir(exist_ok=True)
        (session_dir / "data.csv").write_text("x,y")

        result = await _run_file_manager(
            {"operation": "list", "path": "/"}, _ctx(),
        )
        assert result.success
        names = [e["name"] for e in result.data["entries"]]
        assert "data.csv" in names

    async def test_tree_on_allowed_dir(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        (tmp_path / "a.txt").write_text("a")
        result = await _run_file_manager(
            {"operation": "tree", "path": str(tmp_path)}, _ctx(),
        )
        assert result.success

    async def test_list_outside_denied(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        result = await _run_file_manager(
            {"operation": "list", "path": "/tmp"}, _ctx(),
        )
        assert not result.success

    async def test_info_on_etc_denied(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        result = await _run_file_manager(
            {"operation": "info", "path": "/etc/passwd"}, _ctx(),
        )
        assert not result.success

    async def test_copy_denied_when_dest_outside(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        src = tmp_path / "src.txt"
        src.write_text("data")

        result = await _run_file_manager(
            {"operation": "copy", "path": str(src), "destination": "/tmp/evil.txt"},
            _ctx(),
        )
        assert not result.success

    async def test_mkdir_creates_new_path_under_session(self, tmp_path: Path):
        """mkdir target must resolve even when the leaf directory does not exist yet."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir(exist_ok=True)
        new_dir = session_dir / "nested" / "leaf"
        assert not new_dir.exists()

        result = await _run_file_manager(
            {"operation": "mkdir", "path": str(new_dir), "recursive": True},
            _ctx(),
        )
        assert result.success
        assert new_dir.is_dir()


@pytest.mark.asyncio
class TestTextProcessorSandbox:
    async def test_read_etc_passwd_denied(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        result = await _run_text_processor(
            {"operation": "read", "file_path": "/etc/passwd"}, _ctx(),
        )
        assert not result.success
        assert "sandbox" in (result.error or "").lower()

    async def test_read_project_source_denied(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        result = await _run_text_processor(
            {"operation": "read", "file_path": "/home/yqc/Desktop/leagent/backend/pyproject.toml"},
            _ctx(),
        )
        assert not result.success

    async def test_read_allowed_file(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        f = tmp_path / "notes.txt"
        f.write_text("hello world")

        result = await _run_text_processor(
            {"operation": "read", "file_path": str(f)}, _ctx(),
        )
        assert result.success
        assert "hello world" in result.data["text"]

    async def test_read_attachment_allowed(self, tmp_path: Path):
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = "/nonexistent"
        reset_roots()

        f = tmp_path / "att.txt"
        f.write_text("attached content")

        ctx = _ctx(attachments=[str(f)])
        result = await _run_text_processor(
            {"operation": "read", "file_path": str(f)}, ctx,
        )
        assert result.success

    async def test_read_bare_filename_resolves(self, tmp_path: Path):
        """text_processor can read a file by bare name from session dir."""
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()
        (session_dir / "notes.txt").write_text("session content")

        result = await _run_text_processor(
            {"operation": "read", "file_path": "notes.txt"}, _ctx(),
        )
        assert result.success
        assert "session content" in result.data["text"]

    async def test_write_bare_filename_in_session(self, tmp_path: Path) -> None:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session_dir = tmp_path / "s1"
        session_dir.mkdir()

        payload = "1. intro\n2. more\n"
        result = await _run_text_processor(
            {
                "operation": "write",
                "file_path": "LeAgent能力介绍.txt",
                "data": payload,
            },
            _ctx(),
        )
        assert result.success
        out = session_dir / "LeAgent能力介绍.txt"
        assert out.is_file()
        assert out.read_text(encoding="utf-8") == payload

    async def test_write_etc_passwd_denied(self, tmp_path: Path) -> None:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        result = await _run_text_processor(
            {
                "operation": "write",
                "file_path": "/etc/passwd",
                "data": "x",
            },
            _ctx(),
        )
        assert not result.success
        assert "sandbox" in (result.error or "").lower()
