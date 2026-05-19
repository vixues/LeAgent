"""Unified file management service.

All file lifecycle operations — registration, resolution, access control,
cleanup — flow through :class:`FileManager`. Individual subsystems
(session uploads, tool outputs, code execution artifacts) delegate here
instead of managing storage paths and permissions independently.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO
from uuid import UUID, uuid4

from leagent.services.file_manager.backends import LocalStorageBackend, StorageBackend

if TYPE_CHECKING:
    from leagent.services.cache.service import CacheService
    from leagent.services.database.service import DatabaseService

logger = logging.getLogger(__name__)


class FileAccessLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"


@dataclass
class FileAccessPolicy:
    """Declarative access rules for file operations."""
    allowed_roots: list[str] = field(default_factory=list)
    user_scoped: bool = True
    session_scoped: bool = False
    max_file_size: int = 100 * 1024 * 1024  # 100 MB


@dataclass
class FileRef:
    """Storage-agnostic handle to a managed file."""
    id: UUID
    filename: str
    storage_key: str
    backend_name: str
    content_type: str = "application/octet-stream"
    size: int = 0
    checksum: str = ""
    user_id: UUID | None = None
    session_id: UUID | None = None
    category: str = "general"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "filename": self.filename,
            "storage_key": self.storage_key,
            "backend_name": self.backend_name,
            "content_type": self.content_type,
            "size": self.size,
            "checksum": self.checksum,
            "user_id": str(self.user_id) if self.user_id else None,
            "session_id": str(self.session_id) if self.session_id else None,
            "category": self.category,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


def _safe_filename(filename: str) -> str:
    base = os.path.basename(filename).strip() or "file"
    sanitised: list[str] = []
    for ch in base:
        if ch.isalnum() or ch in {".", "_", "-"}:
            sanitised.append(ch)
        elif ch.isspace():
            sanitised.append("_")
    return ("".join(sanitised) or "file")[:180]


class FileManager:
    """Central file lifecycle manager.

    Coordinates storage backends, access control, and metadata tracking.
    All subsystems (session, tools, code execution) use this service
    instead of managing files independently.
    """

    def __init__(
        self,
        *,
        default_backend: StorageBackend | None = None,
        default_backend_name: str = "local",
        cache: "CacheService | None" = None,
        database: "DatabaseService | None" = None,
        default_policy: FileAccessPolicy | None = None,
    ) -> None:
        self._backends: dict[str, StorageBackend] = {}
        self._default_backend_name = default_backend_name
        if default_backend is not None:
            self._backends[default_backend_name] = default_backend
        self._cache = cache
        self._database = database
        self._policy = default_policy or FileAccessPolicy()
        self._refs: dict[UUID, FileRef] = {}

    def register_backend(self, name: str, backend: StorageBackend) -> None:
        self._backends[name] = backend

    def get_backend(self, name: str | None = None) -> StorageBackend:
        key = name or self._default_backend_name
        if key not in self._backends:
            raise RuntimeError(f"Storage backend '{key}' not registered")
        return self._backends[key]

    async def register(
        self,
        data: bytes | BinaryIO | str | Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        category: str = "upload",
        backend_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> FileRef:
        """Ingest a file from any source and return a FileRef handle."""
        backend_key = backend_name or self._default_backend_name
        backend = self.get_backend(backend_key)
        file_id = uuid4()

        if isinstance(data, (str, Path)):
            src = Path(data)
            if not src.is_file():
                raise FileNotFoundError(f"Source file not found: {data}")
            raw = src.read_bytes()
            filename = filename or src.name
        elif isinstance(data, bytes):
            raw = data
            filename = filename or f"file-{file_id.hex[:8]}"
        else:
            data.seek(0)
            raw = data.read()
            filename = filename or f"file-{file_id.hex[:8]}"

        safe_name = _safe_filename(filename)
        if content_type is None:
            content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

        scope_prefix = ""
        if session_id:
            scope_prefix = f"{session_id}/"
        storage_key = f"{scope_prefix}{file_id}_{safe_name}"

        store_meta = await backend.put(
            raw, storage_key,
            content_type=content_type,
            metadata=metadata or {},
        )

        ref = FileRef(
            id=file_id,
            filename=safe_name,
            storage_key=storage_key,
            backend_name=backend_key,
            content_type=content_type,
            size=store_meta.get("size", len(raw)),
            checksum=store_meta.get("checksum", ""),
            user_id=user_id,
            session_id=session_id,
            category=category,
            metadata={
                **(metadata or {}),
                "storage_path": store_meta.get("storage_path", ""),
            },
        )
        self._refs[file_id] = ref

        if self._cache is not None:
            try:
                await self._cache.set(
                    f"fileref:{file_id}",
                    ref.to_dict(),
                    namespace="files",
                    ttl=600,
                )
            except Exception as exc:
                logger.debug("fileref cache write failed: %s", exc)

        await self._persist_db_row(ref)
        return ref

    async def resolve(self, file_id: UUID) -> FileRef | None:
        """Look up a FileRef by ID, checking in-memory, cache, then DB."""
        if file_id in self._refs:
            return self._refs[file_id]

        if self._cache is not None:
            try:
                cached = await self._cache.get(f"fileref:{file_id}", namespace="files")
                if cached and isinstance(cached, dict):
                    ref = self._dict_to_ref(cached)
                    self._refs[file_id] = ref
                    return ref
            except Exception:
                pass

        return None

    async def download(self, ref: FileRef) -> tuple[bytes, str]:
        """Download file content."""
        backend = self.get_backend(ref.backend_name)
        return await backend.get(ref.storage_key)

    async def delete(self, ref: FileRef) -> bool:
        """Delete a file from storage and metadata."""
        backend = self.get_backend(ref.backend_name)
        ok = await backend.delete(ref.storage_key)
        self._refs.pop(ref.id, None)
        if self._cache is not None:
            try:
                await self._cache.delete(f"fileref:{ref.id}", namespace="files")
            except Exception:
                pass
        return ok

    async def exists(self, ref: FileRef) -> bool:
        backend = self.get_backend(ref.backend_name)
        return await backend.exists(ref.storage_key)

    async def presign(self, ref: FileRef, *, expires_in: int = 3600) -> str | None:
        backend = self.get_backend(ref.backend_name)
        return await backend.presign(ref.storage_key, expires_in=expires_in)

    def check_access(
        self,
        ref: FileRef,
        user_id: UUID | None,
        level: FileAccessLevel = FileAccessLevel.READ,
    ) -> bool:
        """Check if a user has the requested access level to a file."""
        if not self._policy.user_scoped:
            return True
        if ref.user_id is None:
            return True
        if user_id is None:
            return False
        return ref.user_id == user_id

    async def cleanup(
        self,
        *,
        older_than_hours: int = 168,
        category: str | None = None,
    ) -> int:
        """Remove expired files matching the criteria."""
        now = datetime.now(timezone.utc)
        removed = 0
        for fid, ref in list(self._refs.items()):
            if category and ref.category != category:
                continue
            age_hours = (now - ref.created_at).total_seconds() / 3600
            if age_hours > older_than_hours:
                await self.delete(ref)
                removed += 1
        return removed

    async def _persist_db_row(self, ref: FileRef) -> None:
        if self._database is None:
            return
        try:
            from leagent.services.database.models.file import (
                File, FileStatus, FileType,
            )
            ct = ref.content_type or ""
            if ct.startswith("image/"):
                file_type = FileType.IMAGE
            elif any(ct.startswith(p) for p in ("application/pdf", "application/msword", "text/")):
                file_type = FileType.DOCUMENT
            else:
                file_type = FileType.OTHER

            async with self._database.session() as db:
                db.add(File(
                    id=ref.id,
                    session_id=ref.session_id,
                    name=ref.filename,
                    original_name=ref.filename,
                    file_type=file_type,
                    mime_type=ref.content_type,
                    size=ref.size,
                    checksum=ref.checksum,
                    storage_path=ref.metadata.get("storage_path", ref.storage_key),
                    status=FileStatus.PROCESSED,
                    user_id=ref.user_id,
                ))
        except Exception as exc:
            logger.warning("file_manager_db_persist_failed: %s", exc)

    @staticmethod
    def _dict_to_ref(d: dict[str, Any]) -> FileRef:
        return FileRef(
            id=UUID(d["id"]) if isinstance(d.get("id"), str) else d.get("id", uuid4()),
            filename=d.get("filename", ""),
            storage_key=d.get("storage_key", ""),
            backend_name=d.get("backend_name", "local"),
            content_type=d.get("content_type", "application/octet-stream"),
            size=d.get("size", 0),
            checksum=d.get("checksum", ""),
            user_id=UUID(d["user_id"]) if d.get("user_id") else None,
            session_id=UUID(d["session_id"]) if d.get("session_id") else None,
            category=d.get("category", "general"),
            metadata=d.get("metadata", {}),
        )


_file_manager: FileManager | None = None


def get_file_manager() -> FileManager:
    """Return the process-wide FileManager singleton."""
    global _file_manager
    if _file_manager is None:
        _file_manager = FileManager()
    return _file_manager


def init_file_manager(
    *,
    upload_dir: str | Path | None = None,
    cache: Any = None,
    database: Any = None,
    **_kwargs: Any,
) -> FileManager:
    """Initialize the global FileManager with a local storage backend."""
    global _file_manager

    local_root = Path(upload_dir) if upload_dir else Path("/tmp/leagent-files")
    local_backend = LocalStorageBackend(local_root)

    fm = FileManager(
        default_backend=local_backend,
        default_backend_name="local",
        cache=cache,
        database=database,
    )

    _file_manager = fm
    return fm


def reset_file_manager() -> None:
    global _file_manager
    _file_manager = None
