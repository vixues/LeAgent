"""Drive ``uv`` project commands (add/remove/sync/tree) against the backend project.

Falls back to ``uv pip`` / ``pip`` when the project lacks a ``pyproject.toml``
or ``uv`` is not installed.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path  # noqa: TC003 — used at runtime
from typing import Any

from leagent.services.python_env.resolve import (
    backend_root as default_backend_root,
)
from leagent.services.python_env.resolve import (
    resolve_backend_python_executable,
)

logger = logging.getLogger(__name__)

_DIST_NAME_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,253}[A-Za-z0-9])?$"
)

_SUBPROCESS_TIMEOUT = 120


def _has_uv() -> bool:
    return shutil.which("uv") is not None


def _validate_distribution_name(name: str) -> None:
    if not name or len(name) > 255:
        raise ValueError("Invalid distribution name")
    if _DIST_NAME_RE.fullmatch(name.strip()) is None:
        raise ValueError("Invalid distribution name")


def _validate_install_spec(spec: str) -> None:
    if not spec or len(spec) > 512:
        raise ValueError("Invalid package spec")
    for ch in spec:
        if ch in ";\n\r\x00`":
            raise ValueError("Invalid characters in package spec")


def _run(
    cmd: list[str],
    cwd: str,
    *,
    timeout: int = _SUBPROCESS_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


class PythonEnvManager:
    """List / install / uninstall / sync / tree packages in the backend project."""

    def __init__(self, backend_root: Path | None = None) -> None:
        self._backend_root = backend_root or default_backend_root()
        self._uses_uv = _has_uv()
        self._has_pyproject = (self._backend_root / "pyproject.toml").is_file()

    @property
    def _project_mode(self) -> bool:
        return self._uses_uv and self._has_pyproject

    def _cwd(self) -> str:
        return str(self._backend_root)

    def _uv(self) -> str:
        uv = shutil.which("uv")
        assert uv is not None
        return uv

    def info(self) -> dict[str, Any]:
        python_executable = resolve_backend_python_executable()
        has_lockfile = (self._backend_root / "uv.lock").is_file()
        return {
            "python_executable": python_executable,
            "process_python_executable": sys.executable,
            "backend_root": str(self._backend_root.resolve()),
            "uses_uv": self._uses_uv,
            "project_mode": self._project_mode,
            "has_lockfile": has_lockfile,
        }

    def list_packages(self) -> list[dict[str, str]]:
        python_executable = resolve_backend_python_executable()
        if self._uses_uv:
            cmd = [self._uv(), "pip", "list", "--python", python_executable, "--format=json"]
        else:
            cmd = [python_executable, "-m", "pip", "list", "--format=json"]

        proc = _run(cmd, self._cwd())
        if proc.returncode != 0:
            logger.error("pip_list_failed stderr=%s", proc.stderr)
            raise RuntimeError(proc.stderr or proc.stdout or f"exit {proc.returncode}")

        raw = json.loads(proc.stdout)
        out: list[dict[str, str]] = []
        for row in raw:
            if isinstance(row, dict):
                name = row.get("name")
                version = row.get("version")
                if isinstance(name, str) and isinstance(version, str):
                    out.append({"name": name, "version": version})
        return out

    def list_outdated(self) -> list[dict[str, str]]:
        """Return packages with newer versions available."""
        python_executable = resolve_backend_python_executable()
        if self._uses_uv:
            cmd = [
                self._uv(), "pip", "list", "--python", python_executable,
                "--outdated", "--format=json",
            ]
        else:
            cmd = [python_executable, "-m", "pip", "list", "--outdated", "--format=json"]

        proc = _run(cmd, self._cwd(), timeout=180)
        if proc.returncode != 0:
            logger.error("pip_list_outdated_failed stderr=%s", proc.stderr)
            raise RuntimeError(proc.stderr or proc.stdout or f"exit {proc.returncode}")

        raw = json.loads(proc.stdout)
        out: list[dict[str, str]] = []
        for row in raw:
            if isinstance(row, dict):
                name = row.get("name")
                version = row.get("version")
                latest = row.get("latest_version", "")
                if isinstance(name, str) and isinstance(version, str):
                    out.append({
                        "name": name,
                        "version": version,
                        "latest_version": latest or version,
                    })
        return out

    def install(self, spec: str) -> dict[str, Any]:
        _validate_install_spec(spec.strip())
        spec = spec.strip()
        python_executable = resolve_backend_python_executable()

        if self._project_mode:
            cmd = [self._uv(), "add", "--project", self._cwd(), spec]
        elif self._uses_uv:
            cmd = [
                self._uv(), "pip", "install",
                "--python", python_executable,
                spec,
                "--index-strategy", "unsafe-best-match",
            ]
        else:
            cmd = [python_executable, "-m", "pip", "install", spec]

        proc = _run(cmd, self._cwd())
        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            logger.error("install_failed spec=%s stderr=%s", spec, proc.stderr)
            raise RuntimeError(log or f"exit {proc.returncode}")
        return {"ok": True, "log": log}

    def uninstall(self, package: str) -> dict[str, Any]:
        name = package.strip()
        _validate_distribution_name(name)
        python_executable = resolve_backend_python_executable()

        if self._project_mode:
            cmd = [self._uv(), "remove", "--project", self._cwd(), name]
        elif self._uses_uv:
            cmd = [self._uv(), "pip", "uninstall", "--python", python_executable, "-y", name]
        else:
            cmd = [python_executable, "-m", "pip", "uninstall", "-y", name]

        proc = _run(cmd, self._cwd())
        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            logger.error("uninstall_failed package=%s stderr=%s", name, proc.stderr)
            raise RuntimeError(log or f"exit {proc.returncode}")
        return {"ok": True, "log": log}

    def upgrade(self, package: str) -> dict[str, Any]:
        """Upgrade a single package to the latest version."""
        name = package.strip()
        _validate_distribution_name(name)
        python_executable = resolve_backend_python_executable()

        if self._project_mode:
            cmd = [self._uv(), "add", "--project", self._cwd(), "--upgrade-package", name, name]
        elif self._uses_uv:
            cmd = [
                self._uv(), "pip", "install",
                "--python", python_executable,
                "--upgrade", name,
            ]
        else:
            cmd = [python_executable, "-m", "pip", "install", "--upgrade", name]

        proc = _run(cmd, self._cwd())
        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            logger.error("upgrade_failed package=%s stderr=%s", name, proc.stderr)
            raise RuntimeError(log or f"exit {proc.returncode}")
        return {"ok": True, "log": log}

    def sync(self) -> dict[str, Any]:
        """Sync the virtualenv with pyproject.toml / uv.lock."""
        if not self._project_mode:
            raise ValueError("uv project mode is not available (no uv or no pyproject.toml)")

        cmd = [self._uv(), "sync", "--project", self._cwd()]
        proc = _run(cmd, self._cwd(), timeout=300)
        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            logger.error("sync_failed stderr=%s", proc.stderr)
            raise RuntimeError(log or f"exit {proc.returncode}")
        return {"ok": True, "log": log}

    def tree(self) -> dict[str, Any]:
        """Return the dependency tree."""
        if not self._project_mode:
            raise ValueError("uv project mode is not available")

        cmd = [self._uv(), "tree", "--project", self._cwd(), "--no-dedupe"]
        proc = _run(cmd, self._cwd())
        log = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            logger.error("tree_failed stderr=%s", proc.stderr)
            raise RuntimeError(log or f"exit {proc.returncode}")
        return {"tree": proc.stdout.strip()}

    def direct_dependencies(self) -> list[str]:
        """Return the list of direct dependency names from pyproject.toml."""
        if not self._has_pyproject:
            return []
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

        pyproject = self._backend_root / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        deps: list[str] = data.get("project", {}).get("dependencies", [])
        names: list[str] = []
        for dep in deps:
            m = re.match(r"^([A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)", dep)
            if m:
                names.append(m.group(1).lower().replace("-", "_").replace(".", "_"))
        return names
