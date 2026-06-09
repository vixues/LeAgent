"""Tests for leagent.file.service — the unified FileService."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from leagent.file.primitives import FileScope
from leagent.file.service import FileRef, FileService
from leagent.file.storage.local import LocalStorageBackend


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    root = tmp_path / "storage"
    root.mkdir()
    return root


@pytest.fixture
def file_service(storage_root: Path) -> FileService:
    backend = LocalStorageBackend(storage_root)
    return FileService(default_backend=backend)


@pytest.mark.asyncio
async def test_register_bytes(file_service: FileService):
    ref = await file_service.register(
        b"hello world",
        filename="greeting.txt",
        scope=FileScope.SESSION,
    )
    assert isinstance(ref, FileRef)
    assert ref.filename == "greeting.txt"
    assert ref.size == 11
    assert ref.checksum  # sha256 hex digest
    assert ref.scope == FileScope.SESSION


@pytest.mark.asyncio
async def test_register_from_path(file_service: FileService, tmp_path: Path):
    src = tmp_path / "source.txt"
    src.write_text("test content")
    ref = await file_service.register(data=src, scope=FileScope.OUTPUT)
    assert ref.filename == "source.txt"
    assert ref.size == 12


@pytest.mark.asyncio
async def test_download(file_service: FileService):
    ref = await file_service.register(b"payload", filename="dl.bin")
    data, ct = await file_service.download(ref)
    assert data == b"payload"


@pytest.mark.asyncio
async def test_resolve_in_memory(file_service: FileService):
    ref = await file_service.register(b"x", filename="tiny.txt")
    resolved = await file_service.resolve(ref.id)
    assert resolved is not None
    assert resolved.id == ref.id


@pytest.mark.asyncio
async def test_resolve_unknown_returns_none(file_service: FileService):
    result = await file_service.resolve(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_delete(file_service: FileService):
    ref = await file_service.register(b"data", filename="del.txt")
    assert await file_service.exists(ref) is True
    assert await file_service.delete(ref) is True
    assert await file_service.exists(ref) is False


@pytest.mark.asyncio
async def test_scope_in_ref(file_service: FileService):
    ref = await file_service.register(
        b"k", filename="doc.pdf", scope=FileScope.KNOWLEDGE,
    )
    assert ref.scope == FileScope.KNOWLEDGE
    d = ref.to_dict()
    assert d["scope"] == "knowledge"


@pytest.mark.asyncio
async def test_size_limit_enforcement(storage_root: Path):
    from leagent.file.service import FileAccessPolicy

    backend = LocalStorageBackend(storage_root)
    svc = FileService(
        default_backend=backend,
        default_policy=FileAccessPolicy(max_file_size=10),
    )
    with pytest.raises(ValueError, match="exceeds limit"):
        await svc.register(b"x" * 20, filename="big.bin")
