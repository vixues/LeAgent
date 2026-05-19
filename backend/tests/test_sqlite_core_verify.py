"""SQLite-only parity: empty DB can run the full Alembic migration chain."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_alembic_upgrade_head_on_empty_sqlite() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        dbpath = tf.name
    try:
        env = os.environ.copy()
        env["DB_DRIVER"] = "sqlite+aiosqlite"
        env["DB_SQLITE_PATH"] = dbpath
        cp = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(BACKEND_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert cp.returncode == 0, f"{cp.stdout}\n{cp.stderr}"
    finally:
        Path(dbpath).unlink(missing_ok=True)
