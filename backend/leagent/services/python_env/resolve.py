"""Resolve the Python interpreter used by backend-managed tooling."""

from __future__ import annotations

import os
import sys
from pathlib import Path


# backend/leagent/services/python_env/resolve.py -> parents[3] == backend root.
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


def backend_root() -> Path:
    """Return the backend project root."""

    return _BACKEND_ROOT


def _existing_file(path: Path) -> str | None:
    """Return a usable path if it exists; do not resolve symlinks.

    ``Path.resolve()`` follows the venv's ``python`` → ``python3`` chain to the
    system interpreter, which drops the virtualenv and breaks imports.
    """
    try:
        candidate = path.expanduser().absolute()
    except OSError:
        return None
    try:
        if candidate.is_file():
            return str(candidate)
    except OSError:
        return None
    return None


def _venv_python(venv_dir: Path) -> str | None:
    candidates = (
        venv_dir / "Scripts" / "python.exe",
        venv_dir / "Scripts" / "python",
        venv_dir / "bin" / "python",
        venv_dir / "bin" / "python3",
    )
    for candidate in candidates:
        resolved = _existing_file(candidate)
        if resolved:
            return resolved
    return None


def _python_from_value(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None

    path = Path(value).expanduser()
    if path.is_dir():
        return _venv_python(path)
    return _existing_file(path)


def resolve_backend_python_executable() -> str:
    """Resolve the interpreter used by code execution and dependency installs.

    Priority:
    1. LEAGENT_BACKEND_PYTHON / Settings.backend_python_executable.
    2. VIRTUAL_ENV venv from the running backend process.
    3. UV_PROJECT_ENVIRONMENT venv.
    4. backend/.venv.
    5. The current process interpreter.
    """

    explicit = os.environ.get("LEAGENT_BACKEND_PYTHON")
    if explicit is None:
        try:
            from leagent.config.settings import get_settings

            explicit = getattr(get_settings(), "backend_python_executable", "")
        except Exception:  # noqa: BLE001
            explicit = ""

    for raw in (
        explicit,
        os.environ.get("VIRTUAL_ENV"),
        os.environ.get("UV_PROJECT_ENVIRONMENT"),
        str(backend_root() / ".venv"),
    ):
        resolved = _python_from_value(raw)
        if resolved:
            return resolved

    try:
        return str(Path(sys.executable).resolve())
    except OSError:
        return sys.executable
