"""Alembic environment configuration with async engine support."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from leagent.config.settings import get_settings
from leagent.db.engine import make_async_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic can detect them for autogenerate.
# Each model module registers its tables on SQLModel.metadata.
try:
    from leagent.db import models as _models  # noqa: F401
except ImportError:
    pass

from sqlmodel import SQLModel

target_metadata = SQLModel.metadata


def _get_url() -> str:
    """Resolve the database URL from application settings."""
    settings = get_settings()
    return settings.database.url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout)."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine."""
    settings = get_settings()
    connectable = make_async_engine(settings.database)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    When invoked via ``alembic.command.upgrade`` with
    ``config.attributes["connection"]`` set (see ``main._run_db_migrations``),
    reuse that sync connection so ``context.configure`` runs inside a proper
    Alembic migration environment. Otherwise use the async engine path (CLI).
    """
    cfg = context.config
    injected = cfg.attributes.get("connection") if cfg is not None else None
    if injected is not None:
        do_run_migrations(injected)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
