"""SQLAlchemy async engine factory for SQLite (aiosqlite)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class EngineConfig:
    url: str
    echo: bool = False


def make_async_engine(config: EngineConfig) -> Any:
    """Create an ``AsyncEngine`` for SQLite with WAL mode."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        config.url,
        echo=config.echo,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    return engine


def make_sessionmaker(engine: Any) -> Any:
    """Return an async sessionmaker bound to ``engine``."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


__all__ = ["EngineConfig", "make_async_engine", "make_sessionmaker"]
