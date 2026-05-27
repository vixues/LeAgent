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
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    from leagent.config.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=SQLModel)


def _sqlite_connect_pragma(dbapi_conn: object, _: object) -> None:
    """Apply SQLite pragmas on each new DBAPI connection."""
    cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


class DatabaseService:
    """Service for managing database connections and operations."""

    def __init__(self, settings: "Settings") -> None:
        self.settings = settings
        db_cfg = settings.database
        url = db_cfg.url

        if db_cfg.is_postgresql:
            self._engine = create_async_engine(
                url,
                echo=db_cfg.echo,
                pool_size=db_cfg.pool_size,
                max_overflow=db_cfg.max_overflow,
                pool_pre_ping=True,
            )
            logger.info("DatabaseService initialized (PostgreSQL)")
        else:
            Path(db_cfg._sqlite_file_path()).parent.mkdir(parents=True, exist_ok=True)
            self._engine = create_async_engine(
                url,
                echo=db_cfg.echo,
                poolclass=NullPool,
                connect_args={"check_same_thread": False},
            )
            event.listen(self._engine.sync_engine, "connect", _sqlite_connect_pragma)
            logger.info("DatabaseService initialized (SQLite WAL: %s)", db_cfg._sqlite_file_path())

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

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
        from leagent.services.database import models as _models  # noqa: F401

        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        logger.info("Database tables created")
        await self.ensure_identity_stubs()

    async def ensure_identity_stubs(self) -> None:
        """Insert minimal ``users`` / ``workspaces`` rows for FK targets (messages, pet_projects, …)."""
        from leagent.services.auth.service import LOCAL_USER_ID
        from leagent.services.database.models.identity_stub import UserStub, WorkspaceStub

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
