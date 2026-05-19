"""Thin Milvus collection wrapper used by memory stores.

Every cognitive store (episodic, semantic, procedural) owns one Milvus
collection with an identical schema:

* ``id`` (VARCHAR primary key) — the ORM row UUID as a string.
* ``vector`` (FLOAT_VECTOR) — the embedding.
* a pair of scalar fields for filtered lookups (``user_id``, ``scope``).

``MilvusCollection`` wraps the CRUD operations the stores need. If Milvus
is unavailable (import fails, server down, collection creation errors) the
wrapper switches into a :class:`_NullBackend` that returns empty search
results — callers then fall back to BM25 / ILIKE via the recall pipeline.

Keeping this one-file wrapper means the stores don't need to import
``pymilvus`` directly; tests can swap the backend with a fake.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MilvusConnectionConfig:
    """Connection settings used by memory-owned Milvus collections."""

    alias: str = "default"
    host: str = "localhost"
    port: int = 19530
    uri: str | None = None
    token: str | None = None
    secure: bool | None = None
    enabled: bool = False
    connect_timeout_seconds: float = 1.0
    retry_interval_seconds: float = 60.0
    startup_error: str | None = None


@dataclass(frozen=True)
class VectorWriteResult:
    """Outcome of a best-effort vector write."""

    written: bool
    degraded: bool = False
    error: str | None = None


@runtime_checkable
class VectorBackend(Protocol):
    """Subset of the Milvus API memory stores rely on."""

    available: bool

    async def upsert(
        self,
        *,
        row_id: str,
        vector: list[float],
        user_id: str | None = None,
        scope: str | None = None,
    ) -> VectorWriteResult:
        ...

    async def delete(self, row_id: str) -> None:
        ...

    async def search(
        self,
        *,
        vector: list[float],
        limit: int,
        user_id: str | None = None,
        scope: str | None = None,
    ) -> list[tuple[str, float]]:
        ...


class _NullBackend:
    """Fallback implementation when Milvus is not available."""

    available = False

    async def upsert(self, **_: Any) -> VectorWriteResult:
        return VectorWriteResult(written=False, degraded=True, error="vector_backend_unavailable")

    async def delete(self, row_id: str) -> None:
        return None

    async def search(self, **_: Any) -> list[tuple[str, float]]:
        return []


class MilvusCollection:
    """Lazy-initialised Milvus collection bound to a fixed schema."""

    def __init__(
        self,
        *,
        name: str,
        dimension: int,
        description: str = "",
        connection: MilvusConnectionConfig | None = None,
    ) -> None:
        self._name = name
        self._dimension = max(8, int(dimension))
        self._description = description
        self._connection = connection
        self._collection: Any | None = None
        self._ensured = False
        self.available = False
        self.last_error: str | None = None
        self._failure_count = 0
        self._next_retry_at = 0.0
        if connection is not None and connection.enabled and connection.startup_error:
            self.mark_unavailable(connection.startup_error)

    @property
    def enabled(self) -> bool:
        return self._connection is None or self._connection.enabled

    @property
    def degraded(self) -> bool:
        return not self.available

    @property
    def retry_due(self) -> bool:
        return time.monotonic() >= self._next_retry_at

    @property
    def can_search(self) -> bool:
        return self.enabled and self.available and self._collection is not None

    @property
    def can_write(self) -> bool:
        return self.enabled and (self.can_search or self.last_error is None or self.retry_due)

    def mark_unavailable(self, reason: str = "milvus_unavailable") -> None:
        self._collection = None
        self._ensured = False
        self.available = False
        self.last_error = reason
        self._failure_count += 1
        retry_after = (
            self._connection.retry_interval_seconds
            if self._connection is not None
            else 60.0
        )
        self._next_retry_at = time.monotonic() + max(1.0, float(retry_after))

    @property
    def name(self) -> str:
        return self._name

    def _disabled_result(self) -> VectorWriteResult:
        return VectorWriteResult(
            written=False,
            degraded=True,
            error=self.last_error or "milvus_optional_off",
        )

    def _retry_suppressed(self) -> bool:
        return not self.enabled or (self.last_error is not None and not self.retry_due)

    def _ensure_connection(self, connections: Any) -> bool:
        if self._connection is None:
            try:
                return bool(connections.has_connection("default"))
            except Exception:  # noqa: BLE001
                return False

        cfg = self._connection
        try:
            if connections.has_connection(cfg.alias):
                return True
        except Exception:  # noqa: BLE001
            pass

        kwargs: dict[str, Any] = {"alias": cfg.alias}
        if cfg.uri:
            kwargs["uri"] = cfg.uri
            if cfg.token:
                kwargs["token"] = cfg.token
            if cfg.secure is not None:
                kwargs["secure"] = cfg.secure
        else:
            kwargs["host"] = cfg.host
            kwargs["port"] = str(cfg.port)
        kwargs["timeout"] = max(0.1, float(cfg.connect_timeout_seconds))

        connections.connect(**kwargs)
        return True

    def _ensure(self) -> bool:
        """Lazily create / load the collection. ``False`` on any failure."""
        if not self.enabled:
            self.last_error = "milvus_optional_off"
            return False
        if self._retry_suppressed():
            return False
        if self._ensured:
            return self.available
        try:
            from pymilvus import (
                Collection,
                CollectionSchema,
                DataType,
                FieldSchema,
                connections,
                utility,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("milvus_not_installed: %s", exc)
            self.mark_unavailable("pymilvus_not_installed")
            return False

        try:
            self._ensure_connection(connections)
            using = self._connection.alias if self._connection is not None else "default"
            if utility.has_collection(self._name, using=using):
                collection = Collection(name=self._name, using=using)
            else:
                fields = [
                    FieldSchema(
                        name="id",
                        dtype=DataType.VARCHAR,
                        max_length=64,
                        is_primary=True,
                        auto_id=False,
                    ),
                    FieldSchema(
                        name="vector",
                        dtype=DataType.FLOAT_VECTOR,
                        dim=self._dimension,
                    ),
                    FieldSchema(
                        name="user_id", dtype=DataType.VARCHAR, max_length=64
                    ),
                    FieldSchema(
                        name="scope", dtype=DataType.VARCHAR, max_length=64
                    ),
                ]
                schema = CollectionSchema(
                    fields=fields,
                    description=self._description or self._name,
                )
                collection = Collection(name=self._name, schema=schema, using=using)
                collection.create_index(
                    field_name="vector",
                    index_params={
                        "metric_type": "COSINE",
                        "index_type": "IVF_FLAT",
                        "params": {"nlist": 128},
                    },
                )
            try:
                collection.load()
            except Exception as exc:  # noqa: BLE001
                logger.debug("milvus_collection_load_failed: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("milvus_collection_init_failed: %s", exc)
            self.mark_unavailable(str(exc))
            return False

        self._collection = collection
        self._ensured = True
        self.available = True
        self.last_error = None
        self._failure_count = 0
        self._next_retry_at = 0.0
        return True

    async def upsert(
        self,
        *,
        row_id: str,
        vector: list[float],
        user_id: str | None = None,
        scope: str | None = None,
    ) -> VectorWriteResult:
        if not self._ensure() or self._collection is None:
            return self._disabled_result()
        try:
            await asyncio.to_thread(
                self._collection.upsert,
                [
                    [row_id],
                    [vector],
                    [user_id or ""],
                    [scope or ""],
                ],
            )
            return VectorWriteResult(written=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("milvus_upsert_failed: %s", exc)
            self.mark_unavailable(str(exc))
            return VectorWriteResult(written=False, degraded=True, error=str(exc))

    async def delete(self, row_id: str) -> None:
        if not self.can_search and (not self.retry_due or not self._ensure()):
            return
        try:
            await asyncio.to_thread(
                self._collection.delete, f'id == "{row_id}"'
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("milvus_delete_failed: %s", exc)

    async def search(
        self,
        *,
        vector: list[float],
        limit: int,
        user_id: str | None = None,
        scope: str | None = None,
    ) -> list[tuple[str, float]]:
        if not self.can_search:
            return []
        expr_parts: list[str] = []
        if user_id:
            expr_parts.append(f'user_id == "{user_id}"')
        if scope:
            expr_parts.append(f'scope == "{scope}"')
        expr = " and ".join(expr_parts) if expr_parts else None
        try:

            def _do_search():
                return self._collection.search(
                    data=[vector],
                    anns_field="vector",
                    param={"metric_type": "COSINE", "params": {"nprobe": 12}},
                    limit=max(1, int(limit)),
                    expr=expr,
                    output_fields=["id"],
                )

            results = await asyncio.to_thread(_do_search)
        except Exception as exc:  # noqa: BLE001
            logger.warning("milvus_search_failed: %s", exc)
            return []

        out: list[tuple[str, float]] = []
        for hits in results or []:
            for hit in hits:
                row_id = getattr(hit, "id", None) or hit.entity.get("id")
                score = float(getattr(hit, "distance", 0.0) or 0.0)
                if row_id:
                    out.append((str(row_id), score))
        return out


__all__ = [
    "MilvusCollection",
    "MilvusConnectionConfig",
    "VectorBackend",
    "VectorWriteResult",
    "_NullBackend",
]
