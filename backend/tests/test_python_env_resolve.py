"""Tests for backend Python interpreter resolution."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def _touch_python(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/usr/bin/env python\n", encoding="utf-8")
    if os.name != "nt":
        path.chmod(0o755)
    return path


def test_resolve_prefers_explicit_backend_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from leagent.services.python_env import resolve as mod

    explicit = _touch_python(tmp_path / "custom" / "python")
    uv_python = _touch_python(tmp_path / "uv-env" / "bin" / "python")
    monkeypatch.setenv("LEAGENT_BACKEND_PYTHON", str(explicit))
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(uv_python.parent.parent))

    assert mod.resolve_backend_python_executable() == str(explicit.resolve())


def test_resolve_uses_uv_project_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from leagent.services.python_env import resolve as mod

    uv_python = _touch_python(tmp_path / "uv-env" / "bin" / "python")
    monkeypatch.delenv("LEAGENT_BACKEND_PYTHON", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(uv_python.parent.parent))
    monkeypatch.setattr(mod, "_BACKEND_ROOT", tmp_path / "backend")

    assert mod.resolve_backend_python_executable() == str(uv_python.resolve())


def test_resolve_prefers_virtual_env_over_uv_project_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from leagent.services.python_env import resolve as mod

    virtual_env_python = _touch_python(tmp_path / "virtual-env" / "bin" / "python")
    uv_python = _touch_python(tmp_path / "uv-env" / "bin" / "python")
    monkeypatch.delenv("LEAGENT_BACKEND_PYTHON", raising=False)
    monkeypatch.setenv("VIRTUAL_ENV", str(virtual_env_python.parent.parent))
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(uv_python.parent.parent))
    monkeypatch.setattr(mod, "_BACKEND_ROOT", tmp_path / "backend")

    assert mod.resolve_backend_python_executable() == str(virtual_env_python.resolve())


def test_resolve_uses_backend_dot_venv(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from leagent.services.python_env import resolve as mod

    backend = tmp_path / "backend"
    default_python = _touch_python(backend / ".venv" / "bin" / "python")
    monkeypatch.delenv("LEAGENT_BACKEND_PYTHON", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)
    monkeypatch.setattr(mod, "_BACKEND_ROOT", backend)

    assert mod.resolve_backend_python_executable() == str(default_python.resolve())


def test_resolve_falls_back_to_process_python(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from leagent.services.python_env import resolve as mod

    monkeypatch.delenv("LEAGENT_BACKEND_PYTHON", raising=False)
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.delenv("UV_PROJECT_ENVIRONMENT", raising=False)
    monkeypatch.setattr(mod, "_BACKEND_ROOT", tmp_path / "backend")

    assert mod.resolve_backend_python_executable() == str(Path(sys.executable).resolve())
