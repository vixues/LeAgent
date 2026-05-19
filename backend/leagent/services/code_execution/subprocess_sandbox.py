"""Subprocess-based Python executor for the professional code tier.

The parent process spawns a fresh child via
``python -m leagent.services.code_execution.runner`` per execution,
streams the request on stdin, and reads a single JSON envelope on
stdout.

Properties:

* **Fresh interpreter per call.** No stale imports, no leaked globals.
* **Hard timeout.** The parent waits up to ``timeout_sec + grace`` for
  the child; on expiry it ``SIGKILL``s the process group.
* **Unrestricted execution.** The subprocess runs with the same
  privileges as the host process — no rlimits, no namespace isolation.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import structlog

from leagent.services.execution.engine import (
    get_execution_engine,
)
from leagent.services.execution.policies import ExecutionPolicy
from leagent.utils.cjk_font_discovery import resolve_cjk_regular_path

from .workspace import Workspace

logger = structlog.get_logger(__name__)


def _create_subprocess_kwargs(*, cwd: str, env: dict[str, str]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"env": env, "cwd": cwd}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
    else:
        kwargs["start_new_session"] = True
    return kwargs


_DEFAULT_ALLOWED_ENV: frozenset[str] = frozenset(
    {
        "PATH",
        "PYTHONPATH",
        "PYTHONIOENCODING",
        "LC_ALL",
        "LC_CTYPE",
        "LANG",
        "HOME",
        "TMPDIR",
        "LEAGENT_CJK_FONT",
        "LEAGENT_CJK_FONT_BOLD",
    }
)


class SandboxTimeoutError(RuntimeError):
    """Raised when the subprocess exceeds its wall-clock budget."""


@dataclass
class SandboxResult:
    """Structured result returned by :meth:`SubprocessSandbox.execute`."""

    status: str  # "ok" | "error" | "timeout" | "memory" | "crash"
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    error: str | None = None
    produced_files: list[dict[str, Any]] = field(default_factory=list)
    image_artifacts: list[dict[str, Any]] = field(default_factory=list)
    file_artifacts: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    returncode: int = 0
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class SubprocessSandbox:
    """Entry point for running Python in an isolated subprocess."""

    def __init__(
        self,
        *,
        python_exe: str | None = None,
        default_timeout_sec: float = 30.0,
        default_cpu_sec: float | None = None,
        default_memory_bytes: int = 0,
        default_file_bytes: int = 0,
        default_open_files: int = 0,
        default_max_processes: int = 0,
        grace_sec: float = 2.0,
        allow_env: Iterable[str] = (),
        extra_import_roots: tuple[str, ...] = (),
        import_tier: str = "unrestricted",
        isolation_mode: str = "none",
    ) -> None:
        self._python = python_exe or sys.executable
        self._default_timeout = default_timeout_sec
        self._default_cpu = default_cpu_sec
        self._default_memory = default_memory_bytes
        self._default_file_bytes = default_file_bytes
        self._default_open_files = default_open_files
        self._default_max_processes = default_max_processes
        self._grace = grace_sec
        self._allow_env = frozenset(_DEFAULT_ALLOWED_ENV | set(allow_env))
        self._extra_import_roots = tuple(extra_import_roots)
        self._import_tier = import_tier
        self._isolation_mode = "none"

    def _env(self) -> dict[str, str]:
        env: dict[str, str] = {
            k: v for k, v in os.environ.items() if k in self._allow_env
        }
        if os.name == "nt":
            for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE"):
                val = os.environ.get(key)
                if val:
                    env[key] = val
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        env.setdefault("PYTHONUNBUFFERED", "1")
        return env

    async def execute(
        self,
        source: str,
        *,
        workspace: Workspace,
        globals: dict[str, Any] | None = None,
        timeout_sec: float | None = None,
        cpu_sec: float | None = None,
        memory_bytes: int | None = None,
        file_bytes: int | None = None,
        import_tier: str | None = None,
        extra_scan_roots: Iterable[str | os.PathLike[str]] = (),
    ) -> SandboxResult:
        """Run ``source`` inside the subprocess against ``workspace``.

        Files newly created under ``workspace`` *or* under any directory in
        ``extra_scan_roots`` are reported in :attr:`SandboxResult.produced_files`.
        Workspace files use relative paths; files under extra roots use
        absolute paths so the parent controller can ingest them.
        """
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be a non-empty string")
        if workspace is None or not isinstance(workspace, Workspace):
            raise ValueError("workspace is required")

        workspace.ensure()

        timeout = float(timeout_sec if timeout_sec is not None else self._default_timeout)
        extra_env: dict[str, str] = {}
        cjk_font = resolve_cjk_regular_path()
        if cjk_font:
            extra_env["LEAGENT_CJK_FONT"] = cjk_font

        policy = ExecutionPolicy(
            timeout_sec=timeout,
            max_timeout_sec=timeout,
            memory_bytes=0,
            file_bytes=0,
            open_files=0,
            max_processes=0,
            env_allowlist=self._allow_env,
            extra_env=extra_env,
            grace_sec=self._grace,
        )
        scan_roots = tuple(str(Path(r).expanduser()) for r in extra_scan_roots if r)
        result = await get_execution_engine().python_sandbox(
            source,
            workspace=str(workspace.path),
            policy=policy,
            timeout_sec=timeout,
            python_exe=self._python,
            globals_in=globals,
            import_tier="unrestricted",
            extra_import_roots=self._extra_import_roots,
            isolation_mode="none",
            session_id=workspace.session_id,
            extra_scan_roots=scan_roots,
        )

        produced_files = result.produced_files
        image_artifacts, file_artifacts = _split_artifacts(produced_files)
        return SandboxResult(
            status=result.status,
            stdout=result.stdout,
            stderr=result.stderr,
            result=result.metadata.get("result"),
            error=result.error,
            produced_files=produced_files,
            image_artifacts=image_artifacts,
            file_artifacts=file_artifacts,
            duration_ms=result.duration_ms,
            returncode=result.returncode,
            stdout_truncated=bool(result.metadata.get("stdout_truncated")),
            stderr_truncated=bool(result.metadata.get("stderr_truncated")),
        )


def _split_artifacts(
    produced_files: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    images: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    for entry in produced_files:
        if not isinstance(entry, dict):
            continue
        mime = str(entry.get("mime") or "")
        if mime.startswith("image/"):
            images.append(entry)
        else:
            files.append(entry)
    return images, files


def _parse_envelope(raw: bytes) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    last_line = text.splitlines()[-1]
    try:
        return json.loads(last_line)
    except json.JSONDecodeError:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    """Kill the process group (best effort)."""
    pid = proc.pid
    if pid is None:
        return
    if hasattr(os, "killpg") and hasattr(os, "getpgid"):
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except ProcessLookupError:
        return
