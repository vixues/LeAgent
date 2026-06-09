"""Local-filesystem storage backend."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, BinaryIO

logger = __import__("logging").getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


class LocalStorageBackend:
    """Filesystem-based storage backend.

    Files are stored under ``root_dir`` using the provided key as a
    relative path.  Directories are created on demand.
    """

    def __init__(self, root_dir: str | Path) -> None:
        self._root = Path(root_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _resolve(self, key: str) -> Path:
        safe = Path(key)
        if safe.is_absolute():
            safe = Path(*safe.parts[1:]) if len(safe.parts) > 1 else Path(safe.name)
        resolved = (self._root / safe).resolve()
        if not str(resolved).startswith(str(self._root.resolve())):
            raise PermissionError(f"Path escapes storage root: {key}")
        return resolved

    async def put(
        self,
        data: bytes | BinaryIO,
        key: str,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, bytes):
            raw = data
        else:
            data.seek(0)
            raw = data.read()

        sha = hashlib.sha256(raw).hexdigest()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, target.write_bytes, raw)

        return {
            "size": len(raw),
            "checksum": sha,
            "storage_path": str(target),
            "content_type": content_type,
        }

    async def get(self, key: str) -> tuple[bytes, str]:
        target = self._resolve(key)
        if not target.is_file():
            raise FileNotFoundError(f"Not found: {key}")
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(_executor, target.read_bytes)
        ct = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        return data, ct

    async def delete(self, key: str) -> bool:
        target = self._resolve(key)
        try:
            target.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    async def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    async def presign(self, key: str, *, expires_in: int = 3600) -> str | None:
        return None
