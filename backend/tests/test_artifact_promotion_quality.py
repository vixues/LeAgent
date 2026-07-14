"""Tests for artifact promotion overwrite detection and content quality gates."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest


def test_runner_listing_emits_modified_files(tmp_path: Path) -> None:
    from leagent.code.runner import _listing, _scan_files

    target = tmp_path / "report.xlsx"
    target.write_bytes(b"v1-empty-header")
    before = _scan_files(tmp_path)
    # Ensure mtime advances on filesystems with coarse timestamp resolution.
    time.sleep(0.02)
    target.write_bytes(b"v2-with-data-rows-xxxxxx")
    produced = _listing(tmp_path, before)
    paths = {e.get("file_path") or e.get("path") for e in produced}
    assert "report.xlsx" in paths
    entry = next(e for e in produced if (e.get("file_path") or e.get("path")) == "report.xlsx")
    assert entry.get("change") == "modified"


def test_runner_listing_skips_unchanged_files(tmp_path: Path) -> None:
    from leagent.code.runner import _listing, _scan_files

    target = tmp_path / "stable.txt"
    target.write_text("same")
    before = _scan_files(tmp_path)
    produced = _listing(tmp_path, before)
    assert produced == []


def test_assess_xlsx_header_only_fails(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    from leagent.file.quality import assess_artifact_quality

    path = tmp_path / "header_only.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["姓名", "部门", "签名"])
    wb.save(path)
    verdict = assess_artifact_quality(path)
    assert verdict is not None
    assert verdict.passed is False
    assert "header" in verdict.message.lower() or "data" in verdict.message.lower()


def test_assess_xlsx_with_data_passes(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    from leagent.file.quality import assess_artifact_quality

    path = tmp_path / "filled.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["姓名", "部门"])
    ws.append(["张三", "一室"])
    ws.append(["李四", "二室"])
    wb.save(path)
    verdict = assess_artifact_quality(path)
    assert verdict is not None
    assert verdict.passed is True


def test_artifact_tracker_marks_spreadsheet_quality_failure() -> None:
    from leagent.context.artifact_error_tracker import ArtifactErrorTracker

    tracker = ArtifactErrorTracker()
    tracker.record_from_tool_result(
        tool_name="excel_generator",
        tool_call_id="tc-1",
        success=True,
        error_text="",
        quality_passed=False,
        artifact_type_hint="spreadsheet",
    )
    assert tracker.has_dirty_artifacts()
    directives = tracker.get_regeneration_directives()
    assert directives
    assert any("quality" in d.lower() or "file_id" in d for d in directives)


def test_artifact_tracker_code_quality_passed_false() -> None:
    from leagent.context.artifact_error_tracker import ArtifactErrorTracker

    tracker = ArtifactErrorTracker()
    tracker.record_from_tool_result(
        tool_name="code_execution",
        tool_call_id="tc-2",
        success=True,
        error_text="spreadsheet appears header-only",
        quality_passed=False,
    )
    assert tracker.has_dirty_artifacts()
    assert tracker.needs_workspace_reset


@pytest.mark.asyncio
async def test_register_external_file_versions_on_content_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same source_tool_path + different sha256 must mint a new attachment id."""
    from leagent.config.settings import get_settings
    from leagent.services.session.manager import SessionManager
    from leagent.services.session.state import SessionState

    monkeypatch.setattr(
        "leagent.file.sandbox._get_allowed_roots",
        lambda: (tmp_path.resolve(),),
    )

    class _MemoryStore:
        def __init__(self) -> None:
            self._states: dict[UUID, SessionState] = {}

        async def load(self, session_id: UUID) -> SessionState | None:
            return self._states.get(session_id)

        async def save(self, state: SessionState) -> None:
            self._states[state.session_id] = state

    @dataclass
    class _FakeRef:
        id: UUID
        filename: str
        content_type: str
        size: int
        checksum: str
        storage_key: str
        metadata: dict[str, Any]

    class _FakeFileService:
        def __init__(self) -> None:
            self._n = 0

        async def register(self, data: Any, **kwargs: Any) -> _FakeRef:
            self._n += 1
            if hasattr(data, "read_bytes"):
                raw = data.read_bytes()
                name = Path(getattr(data, "name", "f.bin")).name
            else:
                raw = bytes(data) if isinstance(data, (bytes, bytearray)) else b""
                name = kwargs.get("filename") or "f.bin"
            checksum = hashlib.sha256(raw).hexdigest()
            storage = tmp_path / f"managed_{self._n}_{name}"
            storage.write_bytes(raw)
            return _FakeRef(
                id=uuid4(),
                filename=name,
                content_type="application/octet-stream",
                size=len(raw),
                checksum=checksum,
                storage_key=str(storage),
                metadata={"storage_path": str(storage)},
            )

    settings = get_settings()
    manager = SessionManager(settings, cache=None, database=None)
    store = _MemoryStore()
    manager._store = store  # type: ignore[attr-defined]
    manager._ensure_file_service = lambda: _FakeFileService()  # type: ignore[method-assign]

    session_id = uuid4()
    await store.save(SessionState(session_id=session_id))

    src = tmp_path / "out.xlsx"
    src.write_bytes(b"empty-header-only-v1")
    first = await manager.register_external_file(
        session_id, None, str(src), display_name="out.xlsx"
    )
    assert first is not None
    first_id = first["id"]

    src.write_bytes(b"filled-with-real-data-rows-v2")
    second = await manager.register_external_file(
        session_id, None, str(src), display_name="out.xlsx"
    )
    assert second is not None
    assert second["id"] != first_id
    assert second.get("version") == 2
    assert second.get("is_latest") is True

    atts = await manager.list_attachments(session_id)
    superseded = [a for a in atts if str(a.id) == first_id]
    assert superseded
    assert superseded[0].extra.get("is_latest") is False
    assert superseded[0].extra.get("superseded_by") == second["id"]


def test_builtin_office_skills_present() -> None:
    root = Path(__file__).resolve().parents[1] / "leagent" / "skills" / "builtin"
    for name in (
        "attendance-signin-sheet",
        "travel-expense-audit",
        "procurement-audit",
    ):
        skill = root / name / "SKILL.md"
        assert skill.is_file(), skill
        text = skill.read_text(encoding="utf-8")
        assert "ask_user" in text


@pytest.mark.asyncio
async def test_promote_tool_output_path_and_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SessionManager.promote_tool_output is the unified path/bytes entry."""
    import hashlib
    from dataclasses import dataclass
    from typing import Any
    from uuid import UUID, uuid4

    from leagent.config.settings import get_settings
    from leagent.services.session.manager import SessionManager
    from leagent.services.session.state import SessionState

    monkeypatch.setattr(
        "leagent.file.sandbox._get_allowed_roots",
        lambda: (tmp_path.resolve(),),
    )

    class _MemoryStore:
        def __init__(self) -> None:
            self._states: dict[UUID, SessionState] = {}

        async def load(self, session_id: UUID) -> SessionState | None:
            return self._states.get(session_id)

        async def save(self, state: SessionState) -> None:
            self._states[state.session_id] = state

    @dataclass
    class _FakeRef:
        id: UUID
        filename: str
        content_type: str
        size: int
        checksum: str
        storage_key: str
        metadata: dict[str, Any]

    class _FakeFileService:
        def __init__(self) -> None:
            self._n = 0

        async def register(self, data: Any, **kwargs: Any) -> _FakeRef:
            self._n += 1
            if hasattr(data, "read_bytes"):
                raw = data.read_bytes()
                name = Path(getattr(data, "name", "f.bin")).name
            else:
                raw = bytes(data) if isinstance(data, (bytes, bytearray)) else b""
                name = kwargs.get("filename") or "f.bin"
            checksum = hashlib.sha256(raw).hexdigest()
            storage = tmp_path / f"managed_{self._n}_{name}"
            storage.write_bytes(raw)
            return _FakeRef(
                id=uuid4(),
                filename=name,
                content_type=kwargs.get("content_type") or "application/octet-stream",
                size=len(raw),
                checksum=checksum,
                storage_key=str(storage),
                metadata={"storage_path": str(storage)},
            )

    settings = get_settings()
    manager = SessionManager(settings, cache=None, database=None)
    store = _MemoryStore()
    manager._store = store  # type: ignore[attr-defined]
    manager._ensure_file_service = lambda: _FakeFileService()  # type: ignore[method-assign]

    session_id = uuid4()
    await store.save(SessionState(session_id=session_id))

    src = tmp_path / "sheet.xlsx"
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["a", "b"])
    wb.save(src)

    via_path = await manager.promote_tool_output(
        session_id, None, path=str(src), filename="sheet.xlsx"
    )
    assert via_path is not None
    assert via_path.get("id")
    # Header-only xlsx must fail quality at SessionManager promotion.
    assert via_path.get("quality_passed") is False

    filled = b"png-not-really"
    via_bytes = await manager.promote_tool_output(
        session_id,
        None,
        data=filled,
        filename="chart.png",
        source_tool_path=str(tmp_path / "chart.png"),
    )
    assert via_bytes is not None
    assert via_bytes.get("source_tool_path")
    assert via_bytes.get("version") == 1
