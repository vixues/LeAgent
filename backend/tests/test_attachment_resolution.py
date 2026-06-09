from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from leagent.api.v1 import chat as chat_api
from leagent.services.session.state import SessionAttachment
from leagent.file.attachment_context import (
    build_attachment_lookup,
    normalise_attachment_alias,
    normalize_attachment_paths,
)


@pytest.mark.asyncio
async def test_resolve_request_attachment_paths_maps_id_and_name(monkeypatch, tmp_path: Path) -> None:
    session_id = uuid4()
    attachment_id = uuid4()
    stored = tmp_path / f"{attachment_id}_budget.xlsx"
    stored.write_text("demo")

    att = SessionAttachment(
        id=attachment_id,
        session_id=session_id,
        filename="budget.xlsx",
        storage_path=str(stored),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        kind="document",
        size=4,
        sha256="abc123",
    )

    class _SessionManager:
        async def list_attachments(self, _sid):
            return [att]

    fake_sm = SimpleNamespace(session_manager=_SessionManager())
    monkeypatch.setattr("leagent.main.get_service_manager", lambda: fake_sm)

    resolved = await chat_api._resolve_request_attachment_paths(
        session_id,
        [str(attachment_id), "budget.xlsx", "missing.txt"],
    )
    assert str(stored.resolve()) in resolved
    # Unknown refs are passed through but normalized only when resolvable.
    assert all(Path(p).is_absolute() for p in resolved)


def test_normalize_attachment_paths_filters_and_dedupes(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")

    normalized = normalize_attachment_paths([
        "relative-id-like-value",
        str(f),
        str(f),
    ])
    assert normalized == [str(f.resolve())]


def test_build_attachment_lookup_from_session_rows(tmp_path: Path) -> None:
    session_id = uuid4()
    attachment_id = uuid4()
    stored = tmp_path / f"{attachment_id}_budget_report.xlsx"
    stored.write_text("x")
    attachment = SessionAttachment(
        id=attachment_id,
        session_id=session_id,
        filename="Budget Report.xlsx",
        storage_path=str(stored),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        kind="document",
        size=1,
        sha256="abc",
    )

    lookup = build_attachment_lookup(
        session_attachments=[attachment],
        normalized_attachments=[str(stored.resolve())],
    )
    assert lookup["by_id"][str(attachment_id)] == str(stored.resolve())
    assert lookup["by_name"]["budgetreportxlsx"] == str(stored.resolve())
    assert lookup["by_name"]["budgetreport"] == str(stored.resolve())


def test_lookup_registers_uuid_from_knowledge_storage_basename(
    tmp_path: Path,
) -> None:
    """Merged knowledge paths use ``<file_uuid>_<name>`` on disk — expose *file_uuid* in by_id."""
    kid = uuid4()
    stored = tmp_path / f"{kid}_文章.doc"
    stored.write_text("x")
    lookup = build_attachment_lookup(
        session_attachments=[],
        normalized_attachments=[str(stored.resolve())],
    )
    assert lookup["by_id"][str(kid).lower()] == str(stored.resolve())


def test_lookup_maps_bare_original_name_for_uuid_prefixed_file(
    tmp_path: Path,
) -> None:
    """Bare ``工作簿1.csv`` must match ``<uuid>_工作簿1.csv`` via by_name (CJK-safe)."""
    kid = uuid4()
    stored = tmp_path / f"{kid}_工作簿1.csv"
    stored.write_text("x")
    lookup = build_attachment_lookup(
        session_attachments=[],
        normalized_attachments=[str(stored.resolve())],
    )
    key = normalise_attachment_alias("工作簿1.csv")
    assert key
    assert lookup["by_name"][key] == str(stored.resolve())
