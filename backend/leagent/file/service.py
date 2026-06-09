"""Unified file lifecycle service.

:class:`FileService` is the single authoritative blob lifecycle service.
All managed-file operations — registration, resolution, access control,
download, deletion, cleanup — flow through this class.

Subsystems (session uploads, tool outputs, code-execution artifacts, API
endpoints) delegate here instead of managing storage and metadata
independently.
"""

from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO
from uuid import UUID, uuid4

from leagent.file.primitives import FileScope, sanitize_filename
from leagent.file.storage.backend import StorageBackend
from leagent.file.storage.local import LocalStorageBackend

if TYPE_CHECKING:
    from leagent.services.cache.service import CacheService
    from leagent.db.service import DatabaseService

logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────

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
    scope: FileScope = FileScope.SESSION
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
            "scope": self.scope.value,
            "category": self.category,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


# ── FileService ──────────────────────────────────────────────────────

class FileService:
    """Central file lifecycle manager.

    Coordinates storage backends, access control, and metadata tracking.
    All subsystems (session, tools, code execution, API endpoints)
    delegate here instead of managing files independently.
    """

    def __init__(
        self,
        *,
        default_backend: StorageBackend | None = None,
        default_backend_name: str = "local",
        cache: CacheService | None = None,
        database: DatabaseService | None = None,
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

    # ── backend management ───────────────────────────────────────

    def register_backend(self, name: str, backend: StorageBackend) -> None:
        self._backends[name] = backend

    def get_backend(self, name: str | None = None) -> StorageBackend:
        key = name or self._default_backend_name
        if key not in self._backends:
            raise RuntimeError(f"Storage backend '{key}' not registered")
        return self._backends[key]

    # ── core lifecycle ───────────────────────────────────────────

    async def register(
        self,
        data: bytes | BinaryIO | str | Path,
        *,
        filename: str | None = None,
        content_type: str | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        scope: FileScope = FileScope.SESSION,
        category: str = "upload",
        backend_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        persist_db_row: bool = True,
    ) -> FileRef:
        """Ingest a file from any source and return a :class:`FileRef` handle.

        This is the **single ingress** for all managed blobs. Set
        ``persist_db_row=False`` when the caller owns a richer ``File`` row
        (e.g. with folder/workspace linkage) and only needs the blob persisted
        through the storage backend; the caller is then responsible for writing
        the structured-data row keyed on ``FileRef.id``.
        """
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

        if self._policy.max_file_size and len(raw) > self._policy.max_file_size:
            raise ValueError(
                f"File size ({len(raw)}) exceeds limit "
                f"({self._policy.max_file_size})"
            )

        safe_name = sanitize_filename(filename)
        if content_type is None:
            content_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

        scope_prefix = ""
        if session_id:
            scope_prefix = f"{session_id}/"
        storage_key = f"{scope_prefix}{file_id}_{safe_name}"

        store_meta = await backend.put(
            raw,
            storage_key,
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
            scope=scope,
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

        if persist_db_row:
            await self._persist_db_row(ref)
        return ref

    async def resolve(self, file_id: UUID) -> FileRef | None:
        """Look up a FileRef by ID: in-memory → cache → DB."""
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

        ref = await self._resolve_from_db(file_id)
        if ref is not None:
            self._refs[file_id] = ref
        return ref

    async def download(self, ref: FileRef) -> tuple[bytes, str]:
        """Download file content from the backend."""
        backend = self.get_backend(ref.backend_name)
        return await backend.get(ref.storage_key)

    async def delete(self, ref: FileRef) -> bool:
        """Delete a file from storage and all metadata stores."""
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
        """Check whether *user_id* has *level* access to *ref*."""
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

    # ── scope root integration ───────────────────────────────────

    def get_scope_roots(
        self,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
    ) -> dict[FileScope, Path]:
        """Return the canonical disk root for each :class:`FileScope`.

        PathSandbox uses this to populate its allowed-root set without
        independently parsing environment variables.
        """
        from leagent.config.settings import get_settings

        settings = get_settings()

        roots: dict[FileScope, Path] = {}
        upload_dir = Path(settings.files.upload_dir)
        roots[FileScope.SESSION] = upload_dir

        knowledge_dir = settings.files.knowledge_storage_dir
        if knowledge_dir:
            roots[FileScope.KNOWLEDGE] = Path(knowledge_dir)

        roots[FileScope.OUTPUT] = upload_dir
        roots[FileScope.TEMP] = upload_dir / "tmp"

        return roots

    # ── internal helpers ─────────────────────────────────────────

    async def _persist_db_row(self, ref: FileRef) -> None:
        if self._database is None:
            return
        try:
            from leagent.file.primitives import classify_file_kind
            from leagent.db.models.file import (
                File,
                FileStatus,
                FileType,
            )

            kind = classify_file_kind(ref.filename, ref.content_type)
            kind_to_file_type = {
                "image": FileType.IMAGE,
                "document": FileType.DOCUMENT,
                "data": FileType.DATA,
                "audio": FileType.AUDIO,
                "video": FileType.VIDEO,
                "archive": FileType.ARCHIVE,
                "code": FileType.CODE,
                "text": FileType.DOCUMENT,
            }
            file_type = kind_to_file_type.get(kind.value, FileType.OTHER)

            async with self._database.session() as db:
                db.add(
                    File(
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
                    )
                )
        except Exception as exc:
            logger.warning("file_service_db_persist_failed: %s", exc)

    async def _resolve_from_db(self, file_id: UUID) -> FileRef | None:
        """Attempt to reconstruct a FileRef from a DB row."""
        if self._database is None:
            return None
        try:
            from leagent.db.models.file import File

            async with self._database.session() as db:
                from sqlmodel import select

                stmt = select(File).where(File.id == file_id)
                result = await db.execute(stmt)
                row = result.scalars().first()
                if row is None:
                    return None
                return FileRef(
                    id=row.id,
                    filename=row.name,
                    storage_key=row.storage_path or "",
                    backend_name="local",
                    content_type=row.mime_type or "application/octet-stream",
                    size=row.size or 0,
                    checksum=row.checksum or "",
                    user_id=row.user_id,
                    session_id=row.session_id,
                    scope=FileScope.SESSION,
                    category="upload",
                )
        except Exception as exc:
            logger.debug("file_service_db_resolve_failed: %s", exc)
            return None

    @staticmethod
    def _dict_to_ref(d: dict[str, Any]) -> FileRef:
        scope_val = d.get("scope", "session")
        try:
            scope = FileScope(scope_val)
        except ValueError:
            scope = FileScope.SESSION

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
            scope=scope,
            category=d.get("category", "general"),
            metadata=d.get("metadata", {}),
        )
