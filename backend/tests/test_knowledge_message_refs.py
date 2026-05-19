"""Tests for @knowledge references in chat messages."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from leagent.api.v1 import chat as chat_api


def test_parse_knowledge_line_payload_uuid_suffix() -> None:
    uid = uuid4()
    fid, name = chat_api._parse_knowledge_line_payload(f"需求清单.docx#{uid}")
    assert fid == uid
    assert name == "需求清单.docx"


def test_parse_knowledge_line_payload_name_only() -> None:
    fid, name = chat_api._parse_knowledge_line_payload("doc only.docx")
    assert fid is None
    assert name == "doc only.docx"


def test_parse_knowledge_line_payload_hash_in_name() -> None:
    uid = uuid4()
    fid, name = chat_api._parse_knowledge_line_payload(f"part#v2.docx#{uid}")
    assert fid == uid
    assert name == "part#v2.docx"


@pytest.mark.asyncio
async def test_resolve_knowledge_message_paths_by_file_id(tmp_path: Path) -> None:
    user_id = uuid4()
    file_id = uuid4()
    p = tmp_path / "stored.txt"
    p.write_text("x")

    fake_row = MagicMock()
    fake_row.storage_path = str(p)

    fake_result = MagicMock()
    fake_result.first = MagicMock(return_value=fake_row)

    fake_sess = MagicMock()
    fake_sess.exec = AsyncMock(return_value=fake_result)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_sess)
    cm.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.session = MagicMock(return_value=cm)

    msg = f"see @knowledge:ignored.txt#{file_id}"
    out = await chat_api._resolve_knowledge_message_paths(user_id, db, msg)
    assert len(out) == 1
    assert Path(out[0]) == p.resolve()


@pytest.mark.asyncio
async def test_resolve_knowledge_message_paths_by_original_name(tmp_path: Path) -> None:
    user_id = uuid4()
    p = tmp_path / "b.txt"
    p.write_text("y")

    fake_row = MagicMock()
    fake_row.storage_path = str(p)

    fake_result = MagicMock()
    fake_result.first = MagicMock(return_value=None)
    fake_result.all = MagicMock(return_value=[fake_row])

    fake_sess = MagicMock()
    fake_sess.exec = AsyncMock(return_value=fake_result)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_sess)
    cm.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.session = MagicMock(return_value=cm)

    out = await chat_api._resolve_knowledge_message_paths(
        user_id, db, "read @knowledge:UniqueName.docx please",
    )
    assert len(out) == 1
    assert Path(out[0]) == p.resolve()


def test_merge_agent_attachment_paths_dedupes() -> None:
    a = str(Path("/tmp/a.txt"))
    b = str(Path("/tmp/b.txt"))
    m = chat_api._merge_agent_attachment_paths([a], [a, b])
    assert m is not None
    assert len(m) == 2


@pytest.mark.asyncio
async def test_resolve_folder_context_file_ids_returns_paths(tmp_path: Path) -> None:
    """Explicit ``file_ids`` on chat requests must resolve to storage paths."""
    user_id = uuid4()
    file_id = uuid4()
    p = tmp_path / "kb.csv"
    p.write_text("a\n1")

    fake_row = MagicMock()
    fake_row.storage_path = str(p)
    fake_row.original_name = "kb.csv"
    fake_row.extracted_text = None

    fake_result = MagicMock()
    fake_result.all = MagicMock(return_value=[fake_row])

    fake_sess = MagicMock()
    fake_sess.exec = AsyncMock(return_value=fake_result)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_sess)
    cm.__aexit__ = AsyncMock(return_value=None)

    db = MagicMock()
    db.session = MagicMock(return_value=cm)

    out = await chat_api._resolve_folder_context(
        user_id,
        db,
        folder_id=None,
        file_ids_csv=str(file_id),
    )
    assert len(out) == 1
    assert Path(out[0][0]).resolve() == p.resolve()
    assert out[0][1] == "kb.csv"
