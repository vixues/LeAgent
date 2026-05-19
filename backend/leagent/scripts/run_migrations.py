"""Run Alembic migrations once per invocation.

SQLite (default): runs ``alembic upgrade head`` in-process using the packaged
migration environment (works for repo checkouts and ``uv tool install`` wheels).

PostgreSQL (optional): when ``DB_DRIVER`` targets Postgres and ``psycopg2`` is
installed, acquires ``pg_advisory_lock`` so only one Gateway replica upgrades.

Usage::

    python -m leagent.scripts.run_migrations
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

_ADVISORY_LOCK_KEY = 4242_4242_4242  # arbitrary but stable


def _run_sqlite_migrations() -> int:
    try:
        from alembic import command

        from leagent.alembic.runtime_config import load_alembic_config
        from leagent.config.settings import get_settings
    except Exception as exc:  # noqa: BLE001
        logger.error("migration imports failed: %s", exc)
        return 1
    logger.info("running alembic upgrade head (SQLite)")
    settings = get_settings()
    cfg = load_alembic_config(sqlalchemy_url=settings.database.sync_url)
    try:
        command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001
        logger.error("alembic upgrade failed: %s", exc)
        return 1
    logger.info("migrations complete")
    return 0


def _run_postgres_migrations(dsn: str) -> int:
    try:
        import psycopg2
        from alembic import command
    except ImportError as exc:
        logger.error(
            "PostgreSQL migrations require psycopg2. Install optional deps, e.g. "
            "``pip install 'leagent[postgresql]'`` or ``psycopg2-binary``: %s",
            exc,
        )
        return 1

    from leagent.alembic.runtime_config import load_alembic_config

    cfg = load_alembic_config()
    cfg.set_main_option("sqlalchemy.url", dsn)

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        logger.info("acquiring advisory lock %s", _ADVISORY_LOCK_KEY)
        cur.execute("SELECT pg_advisory_lock(%s)", (_ADVISORY_LOCK_KEY,))
        try:
            logger.info("running alembic upgrade head (PostgreSQL)")
            command.upgrade(cfg, "head")
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (_ADVISORY_LOCK_KEY,))
    conn.close()
    logger.info("migrations complete")
    return 0


def _run() -> int:
    logging.basicConfig(level=logging.INFO)

    try:
        from leagent.config.settings import get_settings

        settings = get_settings()
        dsn = settings.database.sync_url
    except Exception:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            logger.error("DATABASE_URL not set and settings import failed")
            return 1

    if dsn.lower().startswith("sqlite"):
        return _run_sqlite_migrations()

    return _run_postgres_migrations(dsn)


def main() -> None:
    sys.exit(_run())


if __name__ == "__main__":
    main()
