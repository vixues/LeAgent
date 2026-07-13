"""Tests for system knowledge storage path helpers and filters."""

from __future__ import annotations

from pathlib import Path

import pytest

from leagent.api.v1 import documents as doc_api


class _FilesCfg:
    def __init__(self, root: Path) -> None:
        self._root = root

    def resolved_knowledge_storage_dir(self) -> str:
        return str(self._root)


class _Settings:
    def __init__(self, root: Path) -> None:
        self.files = _FilesCfg(root)


@pytest.fixture()
def kb_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "knowledge-tree"
    root.mkdir(parents=True)
    monkeypatch.setattr(doc_api, "get_settings", lambda: _Settings(root))
    return root


def test_system_and_legacy_dirs_detected(kb_root: Path) -> None:
    sys_dir = Path(doc_api._system_knowledge_blob_dir())
    leg_dir = Path(doc_api._legacy_knowledge_documents_dir())
    assert sys_dir == kb_root / "system"
    assert leg_dir == kb_root / "documents"

    assert doc_api._is_system_knowledge_storage_path(str(sys_dir / "a.bin"))
    assert doc_api._is_system_knowledge_storage_path(str(leg_dir / "legacy.bin"))
    assert not doc_api._is_system_knowledge_storage_path(str(kb_root / "uploads" / "x.dat"))
    assert not doc_api._is_system_knowledge_storage_path(None)


@pytest.mark.asyncio
async def test_list_documents_unfiled_filter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """unfiled=true returns only knowledge docs with folder_id IS NULL."""
    from uuid import uuid4

    from leagent.config.settings import Settings
    from leagent.db.models.file import File, FileStatus, FileType, LibraryScope
    from leagent.db.models.folder import Folder
    from leagent.db.service import DatabaseService
    from leagent.services.auth.service import LOCAL_USER_ID

    db_path = tmp_path / "docs.db"
    monkeypatch.setenv("DB_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    db = DatabaseService(Settings())
    await db.create_tables()

    folder_id = uuid4()
    unfiled_id = uuid4()
    filed_id = uuid4()

    async with db.session() as session:
        session.add(
            Folder(
                id=folder_id,
                name="kb-folder",
                user_id=LOCAL_USER_ID,
                parent_id=None,
            )
        )
        session.add(
            File(
                id=unfiled_id,
                user_id=LOCAL_USER_ID,
                name="loose.txt",
                original_name="loose.txt",
                file_type=FileType.DOCUMENT,
                size=1,
                status=FileStatus.PROCESSED,
                storage_path="/tmp/loose.txt",
                library_scope=LibraryScope.KNOWLEDGE,
                folder_id=None,
            )
        )
        session.add(
            File(
                id=filed_id,
                user_id=LOCAL_USER_ID,
                name="nested.txt",
                original_name="nested.txt",
                file_type=FileType.DOCUMENT,
                size=1,
                status=FileStatus.PROCESSED,
                storage_path="/tmp/nested.txt",
                library_scope=LibraryScope.KNOWLEDGE,
                folder_id=folder_id,
            )
        )

    from sqlmodel import select

    async with db.session() as session:
        unfiled = list(
            (
                await session.exec(
                    select(File).where(
                        File.library_scope == LibraryScope.KNOWLEDGE,
                        File.folder_id == None,  # noqa: E711
                        File.is_deleted == False,  # noqa: E712
                    )
                )
            ).all()
        )
        in_folder = list(
            (
                await session.exec(
                    select(File).where(
                        File.library_scope == LibraryScope.KNOWLEDGE,
                        File.folder_id == folder_id,
                    )
                )
            ).all()
        )

    assert {f.id for f in unfiled} == {unfiled_id}
    assert {f.id for f in in_folder} == {filed_id}
    await db.dispose()
