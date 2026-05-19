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
