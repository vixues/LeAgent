"""Alembic :class:`~alembic.config.Config` construction for dev trees and wheels.

The repository keeps ``backend/alembic.ini`` for manual CLI runs from that directory.
Runtime code (server startup, ``leagent upgrade``, uv/pip installs) must not depend on
that file being present next to the interpreter — use this module instead.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config


def alembic_script_dir() -> Path:
    """Directory containing ``env.py`` and ``versions/`` (inside the ``leagent`` package)."""
    return Path(__file__).resolve().parent


def load_alembic_config(*, sqlalchemy_url: str | None = None) -> Config:
    """Build an Alembic config with ``script_location`` set to the packaged migrations tree."""
    cfg = Config()
    cfg.set_main_option("script_location", str(alembic_script_dir()))
    if sqlalchemy_url is not None:
        cfg.set_main_option("sqlalchemy.url", sqlalchemy_url)
    return cfg
