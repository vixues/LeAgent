"""SQLAlchemy async engine factory for SQLite and PostgreSQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EngineConfig:
    url: str
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10


def make_async_engine(config: EngineConfig) -> Any:
    """Create an ``AsyncEngine`` for SQLite (WAL) or PostgreSQL."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    if "postgresql" in config.url:
        return create_async_engine(
            config.url,
            echo=config.echo,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_pre_ping=True,
        )

    return create_async_engine(
        config.url,
        echo=config.echo,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )


def make_sessionmaker(engine: Any) -> Any:
    """Return an async sessionmaker bound to ``engine``."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


__all__ = ["EngineConfig", "make_async_engine", "make_sessionmaker"]
