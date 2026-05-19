"""Load the official pack registry and drive ``uv`` / ``pip`` installs."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from leagent.config.constants import LEAGENT_HOME

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parent / "official_registry.json"
_INSTALLED_PATH = LEAGENT_HOME / "extensions" / "installed.json"


@dataclass(frozen=True, slots=True)
class ExtensionPack:
    id: str
    name: str
    description: str
    extras: list[str]
    uninstall_packages: list[str]
    playwright_install: tuple[str, ...] = ()
    playwright_install_deps: bool = False


def _load_registry() -> list[ExtensionPack]:
    raw = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    packs: list[ExtensionPack] = []
    for row in raw.get("packs", []):
        pid = str(row["id"])
        raw_pw = row.get("playwright_install")
        if isinstance(raw_pw, list):
            pw_tuple = tuple(str(x) for x in raw_pw)
        elif pid == "browser":
            pw_tuple = ("chromium",)
        else:
            pw_tuple = ()
        packs.append(
            ExtensionPack(
                id=pid,
                name=str(row.get("name", pid)),
                description=str(row.get("description", "")),
                extras=list(row.get("extras", [])),
                uninstall_packages=list(row.get("uninstall_packages", [])),
                playwright_install=pw_tuple,
                playwright_install_deps=bool(row.get("playwright_install_deps", False)),
            )
        )
    return packs


def _load_installed() -> dict[str, Any]:
    if not _INSTALLED_PATH.is_file():
        return {}
    try:
        return json.loads(_INSTALLED_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_installed(data: dict[str, Any]) -> None:
    _INSTALLED_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INSTALLED_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _uv_or_pip_prefix() -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "install"]
    return [sys.executable, "-m", "pip", "install"]


def _uv_or_pip_uninstall_prefix() -> list[str]:
    uv = shutil.which("uv")
    if uv:
        return [uv, "pip", "uninstall", "-y"]
    return [sys.executable, "-m", "pip", "uninstall", "-y"]


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_playwright_install(pack: ExtensionPack) -> tuple[str, bool]:
    """Download Playwright browser binaries; returns (combined log, success)."""
    if not pack.playwright_install:
        return "", True

    backend_dir = _backend_dir()
    uv = shutil.which("uv")
    if uv:
        base = [uv, "run", "--directory", str(backend_dir), "playwright", "install", *pack.playwright_install]
    else:
        base = [sys.executable, "-m", "playwright", "install", *pack.playwright_install]

    env = os.environ.copy()
    if not env.get("PLAYWRIGHT_DOWNLOAD_HOST") and env.get("LEAGENT_PLAYWRIGHT_MIRROR", "").strip() in (
        "1",
        "true",
        "yes",
    ):
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright/"

    logs: list[str] = []
    proc = subprocess.run(
        base,
        check=False,
        capture_output=True,
        text=True,
        cwd=str(backend_dir),
        env=env,
    )
    logs.append(proc.stdout + proc.stderr)
    if proc.returncode != 0:
        return "\n".join(logs), False

    if pack.playwright_install_deps:
        deps_cmd: list[str]
        if uv:
            deps_cmd = [
                uv,
                "run",
                "--directory",
                str(backend_dir),
                "playwright",
                "install-deps",
                *pack.playwright_install,
            ]
        else:
            deps_cmd = [sys.executable, "-m", "playwright", "install-deps", *pack.playwright_install]
        proc2 = subprocess.run(
            deps_cmd,
            check=False,
            capture_output=True,
            text=True,
            cwd=str(backend_dir),
            env=env,
        )
        logs.append(proc2.stdout + proc2.stderr)

    return "\n".join(logs), True


class ExtensionManager:
    """Registry + install state for official extension packs."""

    def list_packs(self) -> list[dict[str, Any]]:
        installed = _load_installed()
        out: list[dict[str, Any]] = []
        for pack in _load_registry():
            meta = installed.get(pack.id, {})
            out.append(
                {
                    "id": pack.id,
                    "name": pack.name,
                    "description": pack.description,
                    "extras": pack.extras,
                    "installed": bool(meta.get("installed")),
                    "version": meta.get("version"),
                    "installed_at": meta.get("installed_at"),
                }
            )
        return out

    def install_pack(self, pack_id: str) -> dict[str, Any]:
        pack = next((p for p in _load_registry() if p.id == pack_id), None)
        if pack is None:
            raise ValueError(f"Unknown extension pack: {pack_id}")

        extra_spec = ",".join(pack.extras)
        backend_dir = _backend_dir()
        pyproject = backend_dir / "pyproject.toml"
        cwd: str | None = None
        if pyproject.is_file():
            cmd = [*_uv_or_pip_prefix(), "-e", f".[{extra_spec}]"]
            cwd = str(backend_dir)
        else:
            cmd = [*_uv_or_pip_prefix(), f"leagent[{extra_spec}]"]

        if shutil.which("uv"):
            cmd.extend(["--index-strategy", "unsafe-best-match"])

        logger.info("Installing extension pack %s via: %s", pack_id, " ".join(cmd))
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        log_parts = [proc.stdout + proc.stderr]
        if proc.returncode != 0:
            logger.error("extension_install_failed pack=%s stderr=%s", pack_id, proc.stderr)
            raise RuntimeError(proc.stderr or proc.stdout or f"exit {proc.returncode}")

        pw_log = ""
        pw_ok = True
        if pack.playwright_install:
            pw_log, pw_ok = _run_playwright_install(pack)
            if pw_log:
                log_parts.append(pw_log)
            if not pw_ok:
                logger.error("extension_playwright_install_failed pack=%s", pack_id)

        installed = _load_installed()
        installed[pack.id] = {
            "installed": True,
            "version": "latest",
            "installed_at": datetime.now(timezone.utc).isoformat(),
        }
        _save_installed(installed)
        full_log = "\n".join(log_parts)
        return {
            "ok": True,
            "pack_id": pack_id,
            "log": full_log,
            "playwright_install_ok": pw_ok,
            "needs_backend_restart": False,
        }

    def uninstall_pack(self, pack_id: str) -> dict[str, Any]:
        pack = next((p for p in _load_registry() if p.id == pack_id), None)
        if pack is None:
            raise ValueError(f"Unknown extension pack: {pack_id}")
        if not pack.uninstall_packages:
            installed = _load_installed()
            installed.pop(pack_id, None)
            _save_installed(installed)
            return {"ok": True, "pack_id": pack_id, "note": "metadata cleared"}

        cmd = [*_uv_or_pip_uninstall_prefix(), *pack.uninstall_packages]
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        installed = _load_installed()
        installed.pop(pack_id, None)
        _save_installed(installed)
        return {
            "ok": proc.returncode == 0,
            "pack_id": pack_id,
            "log": proc.stdout + proc.stderr,
            "returncode": proc.returncode,
        }
