"""Database service for managing database connections and sessions.

Supports SQLite (default, zero-config) and PostgreSQL (opt-in via
``DB_DATABASE_URL``).  SQLite uses WAL mode with ``NullPool`` so every
async session gets its own connection — concurrent reads no longer
serialize behind a single ``StaticPool`` connection.
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator, TypeVar

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from leagent.db.engine import make_async_engine

if TYPE_CHECKING:
    from leagent.config.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=SQLModel)


class DatabaseService:
    """Service for managing database connections and operations."""

    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        self._engine = make_async_engine(settings.database)

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._repositories: Any | None = None

    @property
    def repositories(self) -> Any:
        """Lazy per-domain repository accessor (files, tasks, chat, …)."""
        if self._repositories is None:
            from leagent.db.repositories import Repositories

            self._repositories = Repositories(self)
        return self._repositories

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        started = time.perf_counter()
        status_label = "success"
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except (Exception, asyncio.CancelledError):
                status_label = "error"
                await session.rollback()
                raise
            finally:
                try:
                    from leagent.utils.metrics import get_metrics

                    get_metrics().record_db_query(
                        f"session_{status_label}",
                        "*",
                        time.perf_counter() - started,
                    )
                    pool = self._engine.sync_engine.pool
                    checked_in = getattr(pool, "checkedin", None)
                    checked_out = getattr(pool, "checkedout", None)
                    if callable(checked_in):
                        get_metrics().db_connection_pool_size.labels(state="checked_in").set(checked_in())
                    if callable(checked_out):
                        get_metrics().db_connection_pool_size.labels(state="checked_out").set(checked_out())
                except Exception:
                    logger.debug("database_metrics_failed", exc_info=True)

    async def create_tables(self) -> None:
        # Ensure all SQLModel classes are imported before create_all() so
        # metadata contains every table.
        from leagent.db import models as _models  # noqa: F401

        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
            await self._ensure_document_chunk_fts(conn)
        logger.info("Database tables created")
        await self.ensure_identity_stubs()

    async def _ensure_document_chunk_fts(self, conn: Any) -> None:
        """Create the SQLite FTS5 chunk index when using the metadata path.

        Alembic migration ``0006_document_chunks`` installs this on migrated
        deployments; ``create_tables`` (the zero-config SQLite bootstrap) must
        mirror it so knowledge search has a BM25 index either way. No-op on
        PostgreSQL, which uses the lexical fallback.
        """
        if self._engine.dialect.name != "sqlite":
            return
        try:
            from sqlalchemy import text as _sa_text

            from leagent.library.fts import FTS_DDL

            for ddl in FTS_DDL:
                await conn.execute(_sa_text(ddl))
        except Exception as exc:  # noqa: BLE001
            logger.warning("document_chunks_fts bootstrap skipped: %s", exc)

    async def ensure_identity_stubs(self) -> None:
        """Insert minimal ``users`` / ``workspaces`` rows for FK targets (messages, pet_projects, …)."""
        from leagent.services.auth.service import LOCAL_USER_ID
        from leagent.db.models.identity_stub import UserStub, WorkspaceStub

        async with self.session() as session:
            existing_user = await session.get(UserStub, LOCAL_USER_ID)
            if existing_user is None:
                session.add(UserStub(id=LOCAL_USER_ID))
            existing_ws = await session.get(WorkspaceStub, LOCAL_USER_ID)
            if existing_ws is None:
                session.add(WorkspaceStub(id=LOCAL_USER_ID))
        logger.debug(
            "identity_stubs_ready",
            user_id=str(LOCAL_USER_ID),
            workspace_id=str(LOCAL_USER_ID),
        )

    async def drop_tables(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        logger.warning("Database tables dropped")

    async def dispose(self) -> None:
        await self._engine.dispose()
        logger.info("Database engine disposed")

    async def get_by_id(self, model: type[T], id: Any) -> T | None:
        async with self.session() as session:
            return await session.get(model, id)

    async def get_all(
        self, model: type[T], *, offset: int = 0, limit: int = 100
    ) -> list[T]:
        async with self.session() as session:
            result = await session.exec(
                select(model).offset(offset).limit(limit)
            )
            return list(result.all())

    async def create(self, obj: T) -> T:
        async with self.session() as session:
            session.add(obj)
            await session.flush()
            await session.refresh(obj)
            return obj

    async def update(self, obj: T) -> T:
        async with self.session() as session:
            session.add(obj)
            await session.flush()
            await session.refresh(obj)
            return obj

    async def delete(self, obj: T) -> None:
        async with self.session() as session:
            await session.delete(obj)

    async def soft_delete(self, obj: Any) -> None:
        from datetime import datetime
        obj.is_deleted = True
        obj.deleted_at = datetime.utcnow()
        await self.update(obj)

    async def execute(self, statement: Any) -> Any:
        async with self.session() as session:
            result = await session.execute(statement)
            return result

    async def health_check(self) -> bool:
        try:
            async with self.session() as session:
                await session.execute(select(1))
            return True
        except Exception as e:
            logger.error("Database health check failed: %s", e)
            return False


_database_service: DatabaseService | None = None


def get_database_service() -> DatabaseService:
    if _database_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is unavailable.",
        )
    return _database_service


def init_database_service(settings: "Settings") -> DatabaseService:
    global _database_service
    _database_service = DatabaseService(settings)
    return _database_service
