"""Async engine construction for the persistence layer.

Single source of truth for building the SQLAlchemy async engine. SQLite uses
WAL mode with ``NullPool`` so every async session gets its own connection;
PostgreSQL uses a pre-pinged connection pool. Both ``DatabaseService`` and the
Alembic environment call :func:`make_async_engine` so engine configuration is
never duplicated.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

if TYPE_CHECKING:
    from leagent.config.settings import DatabaseSettings

logger = logging.getLogger(__name__)


def _sqlite_connect_pragma(dbapi_conn: object, _: object) -> None:
    """Apply SQLite pragmas on each new DBAPI connection."""
    cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def make_async_engine(db_cfg: "DatabaseSettings") -> AsyncEngine:
    """Build the async engine for *db_cfg*.

    Args:
        db_cfg: The ``DatabaseSettings`` describing the target backend.

    Returns:
        A configured :class:`~sqlalchemy.ext.asyncio.AsyncEngine`.
    """
    url = db_cfg.url

    if db_cfg.is_postgresql:
        engine = create_async_engine(
            url,
            echo=db_cfg.echo,
            pool_size=db_cfg.pool_size,
            max_overflow=db_cfg.max_overflow,
            pool_pre_ping=True,
        )
        logger.info("Async engine initialized (PostgreSQL)")
        return engine

    Path(db_cfg._sqlite_file_path()).parent.mkdir(parents=True, exist_ok=True)
    engine = create_async_engine(
        url,
        echo=db_cfg.echo,
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    event.listen(engine.sync_engine, "connect", _sqlite_connect_pragma)
    logger.info("Async engine initialized (SQLite WAL: %s)", db_cfg._sqlite_file_path())
    return engine
