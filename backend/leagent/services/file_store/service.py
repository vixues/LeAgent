"""File store service backed by local filesystem."""

from __future__ import annotations

import hashlib
import io
import logging
import mimetypes
import os
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from leagent.services.base import Service, ServiceType, service_factory

if TYPE_CHECKING:
    from leagent.config.settings import Settings

logger = logging.getLogger(__name__)

METADATA_CACHE_TTL = 300
DEFAULT_URL_EXPIRY = 3600


class FileCategory(str, Enum):
    UPLOAD = "upload"
    OUTPUT = "output"
    TEMPLATE = "template"
    ATTACHMENT = "attachment"
    TEMP = "temp"


class FileMetadata(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    filename: str
    original_filename: str
    bucket: str
    object_name: str
    size: int
    content_type: str
    category: FileCategory = FileCategory.UPLOAD
    checksum: str | None = None
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    uploaded_by: UUID | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _storage_root() -> Path:
    from leagent.config.constants import LEAGENT_HOME
    return LEAGENT_HOME / "storage"


@service_factory(ServiceType.FILE_STORE)
class FileStoreService(Service):
    """Local filesystem file store."""

    def __init__(self, settings: "Settings", cache: Any | None = None) -> None:
        super().__init__(settings)
        self._root = _storage_root()
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "FileStoreService"

    async def _do_start(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        for cat in FileCategory:
            (self._root / cat.value).mkdir(exist_ok=True)
        logger.info("FileStoreService ready at %s", self._root)

    async def _do_stop(self) -> None:
        pass

    async def _do_health_check(self) -> dict[str, Any]:
        return {"root": str(self._root), "exists": self._root.is_dir()}

    def _bucket_dir(self, bucket: str) -> Path:
        d = self._root / bucket
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def upload_file(
        self,
        file_data: bytes | BinaryIO,
        *,
        filename: str | None = None,
        original_filename: str | None = None,
        content_type: str | None = None,
        category: FileCategory = FileCategory.UPLOAD,
        uploaded_by: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        bucket: str | None = None,
    ) -> FileMetadata:
        file_id = uuid4()
        orig = original_filename or filename or "unnamed"
        ext = Path(orig).suffix
        stored_name = f"{file_id}{ext}"
        ct = content_type or mimetypes.guess_type(orig)[0] or "application/octet-stream"
        target_bucket = bucket or category.value
        dest = self._bucket_dir(target_bucket) / stored_name

        if isinstance(file_data, bytes):
            data = file_data
        else:
            data = file_data.read()

        dest.write_bytes(data)
        checksum = hashlib.md5(data).hexdigest()

        return FileMetadata(
            id=file_id,
            filename=stored_name,
            original_filename=orig,
            bucket=target_bucket,
            object_name=stored_name,
            size=len(data),
            content_type=ct,
            category=category,
            checksum=checksum,
            uploaded_by=uploaded_by,
            metadata=metadata or {},
        )

    async def download_file(
        self, bucket: str, object_name: str
    ) -> bytes | None:
        path = self._bucket_dir(bucket) / object_name
        if not path.is_file():
            return None
        return path.read_bytes()

    async def download_file_stream(
        self, bucket: str, object_name: str
    ) -> BinaryIO | None:
        path = self._bucket_dir(bucket) / object_name
        if not path.is_file():
            return None
        return io.BytesIO(path.read_bytes())

    async def delete_file(self, bucket: str, object_name: str) -> bool:
        path = self._bucket_dir(bucket) / object_name
        if path.is_file():
            path.unlink()
            return True
        return False

    async def get_file_info(
        self, bucket: str, object_name: str
    ) -> dict[str, Any] | None:
        path = self._bucket_dir(bucket) / object_name
        if not path.is_file():
            return None
        stat = path.stat()
        ct = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return {
            "bucket": bucket,
            "object_name": object_name,
            "size": stat.st_size,
            "content_type": ct,
            "last_modified": datetime.fromtimestamp(stat.st_mtime),
        }

    async def file_exists(self, bucket: str, object_name: str) -> bool:
        return (self._bucket_dir(bucket) / object_name).is_file()

    async def list_files(
        self,
        bucket: str,
        prefix: str = "",
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        d = self._bucket_dir(bucket)
        items: list[dict[str, Any]] = []
        for f in sorted(d.iterdir()):
            if not f.is_file():
                continue
            if prefix and not f.name.startswith(prefix):
                continue
            items.append({
                "name": f.name,
                "size": f.stat().st_size,
                "content_type": mimetypes.guess_type(f.name)[0] or "application/octet-stream",
            })
            if len(items) >= limit:
                break
        return items

    async def get_presigned_url(
        self, bucket: str, object_name: str, expiry: int = DEFAULT_URL_EXPIRY
    ) -> str | None:
        path = self._bucket_dir(bucket) / object_name
        if not path.is_file():
            return None
        return f"/api/v1/files/storage/{bucket}/{object_name}"

    async def copy_file(
        self, src_bucket: str, src_name: str, dst_bucket: str, dst_name: str
    ) -> bool:
        src = self._bucket_dir(src_bucket) / src_name
        if not src.is_file():
            return False
        dst = self._bucket_dir(dst_bucket) / dst_name
        shutil.copy2(str(src), str(dst))
        return True


_file_store: FileStoreService | None = None


def get_file_store() -> FileStoreService:
    if _file_store is None:
        raise RuntimeError("FileStoreService not initialized")
    return _file_store


async def init_file_store(settings: "Settings", cache: Any | None = None) -> FileStoreService:
    global _file_store
    _file_store = FileStoreService(settings, cache)
    await _file_store.start()
    return _file_store
