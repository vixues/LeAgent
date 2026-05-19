"""In-process Alembic migrations using ``command.upgrade`` + injected connection.

Calling :func:`alembic.context.configure` outside the CLI raises a proxy
``NameError``; delegating to ``command.upgrade`` ensures ``env.py`` runs under
a proper Alembic environment. ``env.run_migrations_online`` reads
``config.attributes["connection"]`` when present.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


def run_sync_migrations(connection: "Connection") -> None:
    """Run ``alembic upgrade head`` on an existing sync SQLAlchemy connection."""
    from alembic import command

    from leagent.config.settings import get_settings

    from leagent.alembic.runtime_config import load_alembic_config

    settings = get_settings()
    cfg = load_alembic_config(sqlalchemy_url=settings.database.sync_url)
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")
