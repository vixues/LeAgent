"""SQLAlchemy engine factory with remote URL gating."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine  # noqa: TC002

REMOTE_ENV = "LEAGENT_DATABASE_TOOL_REMOTE"

_ALLOWED_REMOTE_SCHEMES = frozenset({
    "postgresql",
    "postgresql+psycopg2",
    "postgresql+psycopg",
    "mysql",
    "mysql+pymysql",
    "mysql+mysqldb",
    "mariadb",
    "mariadb+pymysql",
    "mariadb+mysqldb",
})


def _remote_enabled() -> bool:
    return os.environ.get(REMOTE_ENV, "").strip() in ("1", "true", "yes", "on")


def _scheme_ok(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    scheme = (p.scheme or "").lower()
    if "+" in scheme:
        return scheme in _ALLOWED_REMOTE_SCHEMES
    base = scheme.split("+", 1)[0]
    return base in ("postgresql", "mysql", "mariadb")


def build_engine(
    *,
    kind: str,
    sqlite_path: str | None,
    database_url: str | None,
    timeout_seconds: int,
) -> Engine:
    """Create a short-lived sync Engine."""
    k = (kind or "sqlite").lower().strip()
    if k in ("mariadb",):
        k = "mysql"

    if k == "sqlite":
        if not sqlite_path:
            raise ValueError("sqlite_path is required when kind is sqlite")
        path = Path(sqlite_path)
        if not path.is_absolute():
            raise ValueError("sqlite_path must be absolute after sandbox resolution")
        url = f"sqlite:///{path.as_posix()}"
        return create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"timeout": float(timeout_seconds)},
        )

    if not _remote_enabled():
        raise PermissionError(
            f"Remote database URLs are disabled. Set {REMOTE_ENV}=1 to allow "
            "(use only in controlled environments)."
        )
    if not database_url or not str(database_url).strip():
        raise ValueError("database_url is required for non-sqlite kinds")
    url = str(database_url).strip()
    if not _scheme_ok(url):
        raise ValueError(
            f"database_url scheme not allowed. Permitted: {sorted(_ALLOWED_REMOTE_SCHEMES)}"
        )

    if k == "postgresql":
        try:
            import psycopg2  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "PostgreSQL driver not installed. Install optional extra: pip install "
                "'leagent[postgresql]' (psycopg2-binary or asyncpg stack)."
            ) from e
        return create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": timeout_seconds},
        )

    if k in ("mysql", "mariadb"):
        try:
            import pymysql  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "MySQL/MariaDB driver not installed. Install optional extra: pip install 'leagent[mysql]'"
            ) from e
        return create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": timeout_seconds},
        )

    raise ValueError(f"Unsupported kind: {kind!r}")
