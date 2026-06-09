"""Storage backend protocol.

All persistent blob I/O flows through implementations of
:class:`StorageBackend`.  The protocol is deliberately minimal so that
swapping local-filesystem for S3 / GCS / MinIO later requires only a
new concrete class and no changes to :class:`~leagent.file.service.FileService`.
"""

from __future__ import annotations

from typing import Any, BinaryIO, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Protocol for pluggable storage backends."""

    async def put(
        self,
        data: bytes | BinaryIO,
        key: str,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        ...

    async def get(self, key: str) -> tuple[bytes, str]:
        ...

    async def delete(self, key: str) -> bool:
        ...

    async def exists(self, key: str) -> bool:
        ...

    async def presign(self, key: str, *, expires_in: int = 3600) -> str | None:
        ...
