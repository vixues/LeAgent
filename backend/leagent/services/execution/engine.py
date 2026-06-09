"""Unified execution engine for subprocess workloads.

All subprocess-based execution (Python sandbox, shell commands, cron
scripts) routes through :class:`ExecutionEngine`. The engine provides
consistent process group management, resource limiting, environment
sanitization, output capture/truncation, and concurrency control.
"""

from __future__ import annotations

import asyncio
import json as _json
import os
import signal
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import structlog

from leagent.services.execution.policies import (
    AgentPolicy,
    CronPolicy,
    ExecutionPolicy,
)
from leagent.services.python_env.resolve import backend_root

logger = structlog.get_logger(__name__)


class ExecutionMode(str, Enum):
    PYTHON_SANDBOX = "python_sandbox"
    SHELL_COMMAND = "shell_command"
    SHELL_SCRIPT = "shell_script"


@dataclass
class ExecutionResult:
    """Unified result from any execution mode."""
    status: str  # "ok", "error", "timeout", "crash", "denied"
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    duration_ms: int = 0
    error: str | None = None
    produced_files: list[dict[str, Any]] = field(default_factory=list)
    mode: ExecutionMode = ExecutionMode.SHELL_COMMAND
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "returncode": self.returncode,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "produced_files": self.produced_files,
            "mode": self.mode.value,
            "metadata": self.metadata,
        }


def _create_subprocess_kwargs(*, cwd: str, env: dict[str, str]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"env": env, "cwd": cwd}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200,
        )
    else:
        kwargs["start_new_session"] = True
    return kwargs


def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
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
        pass


def _sandbox_argv(
    *,
    python: str,
    workspace: Path,
    isolation_mode: str,
) -> list[str]:
    """Build the Python runner argv — direct execution, no namespace isolation."""
    return [python, "-m", "leagent.code.runner"]


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n... [truncated]", True


def _record_sandbox_metric(result: ExecutionResult, *, isolation_mode: str) -> None:
    try:
        from leagent.utils.metrics import get_metrics

        get_metrics().record_sandbox_execution(
            status=result.status,
            isolation_mode=(isolation_mode or "auto").strip().lower(),
            duration=result.duration_ms / 1000.0,
        )
    except Exception:  # noqa: BLE001
        logger.debug("sandbox_prometheus_metrics_failed", status=result.status)


class ExecutionEngine:
    """Central engine for all subprocess-based execution."""

    def __init__(
        self,
        *,
        default_policy: ExecutionPolicy | None = None,
        max_concurrent: int = 20,
        max_per_session: int = 5,
    ) -> None:
        self._default_policy = default_policy or AgentPolicy()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_count = 0
        self._total_executions = 0
        self._max_per_session = max_per_session
        self._session_exec_counts: dict[str, int] = {}
        self._active_procs: dict[str, list[asyncio.subprocess.Process]] = {}

    @property
    def active_count(self) -> int:
        return self._active_count

    @property
    def total_executions(self) -> int:
        return self._total_executions

    def _register_proc(self, session_id: str | None, proc: asyncio.subprocess.Process) -> None:
        if session_id:
            self._active_procs.setdefault(session_id, []).append(proc)

    def _unregister_proc(self, session_id: str | None, proc: asyncio.subprocess.Process) -> None:
        if session_id and session_id in self._active_procs:
            try:
                self._active_procs[session_id].remove(proc)
            except ValueError:
                pass
            if not self._active_procs[session_id]:
                self._active_procs.pop(session_id, None)

    def _check_session_quota(self, session_id: str | None) -> bool:
        """Return True if the session is within its per-session execution quota."""
        if not session_id or self._max_per_session <= 0:
            return True
        return self._session_exec_counts.get(session_id, 0) < self._max_per_session

    def _inc_session_count(self, session_id: str | None) -> None:
        if session_id:
            self._session_exec_counts[session_id] = self._session_exec_counts.get(session_id, 0) + 1

    def _dec_session_count(self, session_id: str | None) -> None:
        if session_id and session_id in self._session_exec_counts:
            self._session_exec_counts[session_id] -= 1
            if self._session_exec_counts[session_id] <= 0:
                self._session_exec_counts.pop(session_id, None)

    async def cancel_session(self, session_id: str) -> int:
        """Kill all active subprocesses for a session. Returns number of processes killed."""
        keys = [
            key
            for key in list(self._active_procs)
            if key == session_id or key.endswith(f"__{session_id}")
        ]
        procs: list[asyncio.subprocess.Process] = []
        for key in keys:
            procs.extend(self._active_procs.pop(key, []))
        killed = 0
        for proc in procs:
            try:
                _kill_process_group(proc)
                killed += 1
            except Exception:  # noqa: BLE001
                pass
        for key in keys:
            self._session_exec_counts.pop(key, None)
        return killed

    async def python_sandbox(
        self,
        source: str,
        *,
        workspace: str | None = None,
        policy: ExecutionPolicy | None = None,
        timeout_sec: float | None = None,
        python_exe: str | None = None,
        globals_in: dict[str, Any] | None = None,
        import_tier: str = "stdlib",
        extra_import_roots: tuple[str, ...] = (),
        isolation_mode: str = "auto",
        session_id: str | None = None,
        extra_scan_roots: tuple[str, ...] = (),
    ) -> ExecutionResult:
        """Run Python source in a sandboxed subprocess."""
        if not self._check_session_quota(session_id):
            return ExecutionResult(
                status="denied",
                error=f"Session exceeded max concurrent executions ({self._max_per_session})",
                mode=ExecutionMode.PYTHON_SANDBOX,
            )
        pol = policy or self._default_policy
        effective_timeout = pol.effective_timeout(timeout_sec)
        env = pol.sanitized_env()
        python = python_exe or sys.executable
        # Runner cwd is the session workspace, not the backend tree; without this,
        # ``python -m leagent.services.code_execution.runner`` cannot resolve ``leagent``.
        try:
            _br = str(backend_root().resolve())
        except OSError:
            _br = str(backend_root())
        _prev = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{_br}{os.pathsep}{_prev}" if _prev else _br
        )

        payload = {
            "source": source,
            "globals": globals_in or {},
            "timeout_sec": effective_timeout,
            "cpu_sec": effective_timeout,
            "memory_bytes": pol.memory_bytes,
            "file_bytes": pol.file_bytes,
            "open_files": pol.open_files,
            "max_processes": pol.max_processes,
            "workspace": workspace,
            "extra_import_roots": list(extra_import_roots),
            "import_tier": import_tier,
            "extra_scan_roots": list(extra_scan_roots),
        }
        from leagent.code.runner import build_runner_stdin

        payload_bytes = build_runner_stdin(payload)

        cwd = workspace or os.getcwd()
        argv = _sandbox_argv(
            python=python,
            workspace=Path(cwd),
            isolation_mode=isolation_mode,
        )
        result = await self._run_subprocess(
            argv,
            stdin_data=payload_bytes,
            cwd=cwd,
            env=env,
            timeout=effective_timeout + pol.grace_sec,
            policy=pol,
            mode=ExecutionMode.PYTHON_SANDBOX,
            parse_json_envelope=True,
            session_id=session_id,
        )
        _record_sandbox_metric(result, isolation_mode=isolation_mode)
        return result

    async def shell_command(
        self,
        argv: list[str],
        *,
        cwd: str | None = None,
        policy: ExecutionPolicy | None = None,
        timeout_sec: float | None = None,
        extra_env: dict[str, str] | None = None,
        stdin_data: bytes | None = None,
        session_id: str | None = None,
    ) -> ExecutionResult:
        """Run a whitelisted shell command."""
        pol = policy or self._default_policy
        effective_timeout = pol.effective_timeout(timeout_sec)

        if pol.allowed_binaries is not None and argv:
            binary = Path(argv[0]).name
            if binary not in pol.allowed_binaries:
                resolved = shutil.which(argv[0])
                if resolved:
                    binary = Path(resolved).name
                if binary not in pol.allowed_binaries:
                    return ExecutionResult(
                        status="denied",
                        error=f"Binary '{argv[0]}' not in allowed list",
                        mode=ExecutionMode.SHELL_COMMAND,
                    )

        env = pol.sanitized_env(extra_env)
        working_dir = cwd or os.getcwd()

        return await self._run_subprocess(
            argv,
            cwd=working_dir,
            env=env,
            timeout=effective_timeout + pol.grace_sec,
            policy=pol,
            mode=ExecutionMode.SHELL_COMMAND,
            stdin_data=stdin_data,
            session_id=session_id,
        )

    async def shell_script(
        self,
        script: str,
        *,
        cwd: str | None = None,
        policy: ExecutionPolicy | None = None,
        timeout_sec: float | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> ExecutionResult:
        """Run a free-form shell script (requires policy.allow_free_shell)."""
        pol = policy or self._default_policy
        if not pol.allow_free_shell:
            return ExecutionResult(
                status="denied",
                error="Free-form shell scripts are not allowed by current policy",
                mode=ExecutionMode.SHELL_SCRIPT,
            )

        effective_timeout = pol.effective_timeout(timeout_sec)
        env = pol.sanitized_env(extra_env)
        working_dir = cwd or os.getcwd()

        return await self._run_shell_script(
            script,
            cwd=working_dir,
            env=env,
            timeout=effective_timeout + pol.grace_sec,
            policy=pol,
        )

    async def _run_subprocess(
        self,
        argv: list[str],
        *,
        cwd: str,
        env: dict[str, str],
        timeout: float,
        policy: ExecutionPolicy,
        mode: ExecutionMode,
        stdin_data: bytes | None = None,
        parse_json_envelope: bool = False,
        session_id: str | None = None,
    ) -> ExecutionResult:
        async with self._semaphore:
            self._active_count += 1
            self._total_executions += 1
            self._inc_session_count(session_id)
            started = time.monotonic()
            proc: asyncio.subprocess.Process | None = None
            try:
                spawn_kw = _create_subprocess_kwargs(cwd=cwd, env=env)
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    stdin=asyncio.subprocess.PIPE if stdin_data is not None else None,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **spawn_kw,
                )
                self._register_proc(session_id, proc)

                try:
                    stdout_raw, stderr_raw = await asyncio.wait_for(
                        proc.communicate(input=stdin_data),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    _kill_process_group(proc)
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                    duration_ms = int((time.monotonic() - started) * 1000)
                    logger.warning("execution_timeout", argv=argv[:3], timeout=timeout)
                    return ExecutionResult(
                        status="timeout",
                        error=f"Execution exceeded {timeout:.0f}s wall-clock",
                        duration_ms=duration_ms,
                        mode=mode,
                    )

                returncode = proc.returncode if proc.returncode is not None else -1
                duration_ms = int((time.monotonic() - started) * 1000)

                stdout_text = stdout_raw.decode("utf-8", errors="replace") if stdout_raw else ""
                stderr_text = stderr_raw.decode("utf-8", errors="replace") if stderr_raw else ""

                if parse_json_envelope:
                    return self._parse_sandbox_envelope(
                        stdout_text, stderr_text, returncode, duration_ms, mode,
                    )

                stdout_text, _ = _truncate(stdout_text, policy.max_output_bytes)
                stderr_text, _ = _truncate(stderr_text, policy.max_output_bytes)

                status = "ok" if returncode == 0 else "error"
                return ExecutionResult(
                    status=status,
                    stdout=stdout_text,
                    stderr=stderr_text,
                    returncode=returncode,
                    duration_ms=duration_ms,
                    error=None if returncode == 0 else f"Exit code {returncode}",
                    mode=mode,
                )

            except Exception as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                logger.error("execution_crash", error=str(exc), argv=argv[:3])
                return ExecutionResult(
                    status="crash",
                    error=str(exc),
                    duration_ms=duration_ms,
                    mode=mode,
                )
            finally:
                if proc is not None:
                    self._unregister_proc(session_id, proc)
                self._dec_session_count(session_id)
                self._active_count -= 1

    async def _run_shell_script(
        self,
        script: str,
        *,
        cwd: str,
        env: dict[str, str],
        timeout: float,
        policy: ExecutionPolicy,
    ) -> ExecutionResult:
        async with self._semaphore:
            self._active_count += 1
            self._total_executions += 1
            started = time.monotonic()
            try:
                spawn_kw = _create_subprocess_kwargs(cwd=cwd, env=env)
                spawn_kw.pop("start_new_session", None)
                proc = await asyncio.create_subprocess_shell(
                    script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    **spawn_kw,
                )

                try:
                    stdout_raw, stderr_raw = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=timeout,
                    )
                except asyncio.TimeoutError:
                    _kill_process_group(proc)
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        pass
                    duration_ms = int((time.monotonic() - started) * 1000)
                    return ExecutionResult(
                        status="timeout",
                        error=f"Script exceeded {timeout:.0f}s",
                        duration_ms=duration_ms,
                        mode=ExecutionMode.SHELL_SCRIPT,
                    )

                returncode = proc.returncode if proc.returncode is not None else -1
                duration_ms = int((time.monotonic() - started) * 1000)

                stdout_text = stdout_raw.decode("utf-8", errors="replace") if stdout_raw else ""
                stderr_text = stderr_raw.decode("utf-8", errors="replace") if stderr_raw else ""
                stdout_text, _ = _truncate(stdout_text, policy.max_output_bytes)
                stderr_text, _ = _truncate(stderr_text, policy.max_output_bytes)

                status = "ok" if returncode == 0 else "error"
                return ExecutionResult(
                    status=status,
                    stdout=stdout_text,
                    stderr=stderr_text,
                    returncode=returncode,
                    duration_ms=duration_ms,
                    error=None if returncode == 0 else f"Exit code {returncode}",
                    mode=ExecutionMode.SHELL_SCRIPT,
                )
            except Exception as exc:
                duration_ms = int((time.monotonic() - started) * 1000)
                return ExecutionResult(
                    status="crash",
                    error=str(exc),
                    duration_ms=duration_ms,
                    mode=ExecutionMode.SHELL_SCRIPT,
                )
            finally:
                self._active_count -= 1

    def _parse_sandbox_envelope(
        self,
        stdout: str,
        stderr: str,
        returncode: int,
        duration_ms: int,
        mode: ExecutionMode,
    ) -> ExecutionResult:
        if not stdout.strip():
            return ExecutionResult(
                status="crash",
                error=f"Sandbox subprocess exited with {returncode}",
                stderr=stderr,
                returncode=returncode,
                duration_ms=duration_ms,
                mode=mode,
            )
        last_line = stdout.strip().splitlines()[-1]
        try:
            envelope = _json.loads(last_line)
        except _json.JSONDecodeError:
            try:
                envelope = _json.loads(stdout.strip())
            except _json.JSONDecodeError:
                return ExecutionResult(
                    status="crash",
                    error=f"Could not parse sandbox output (rc={returncode})",
                    stderr=stderr[:500],
                    returncode=returncode,
                    duration_ms=duration_ms,
                    mode=mode,
                )

        return ExecutionResult(
            status=envelope.get("status", "error"),
            stdout=envelope.get("stdout", ""),
            stderr=envelope.get("stderr", ""),
            returncode=returncode,
            duration_ms=int(envelope.get("duration_ms") or duration_ms),
            error=envelope.get("error"),
            produced_files=list(envelope.get("produced_files") or []),
            mode=mode,
            metadata={
                "result": envelope.get("result"),
                "stdout_truncated": bool(envelope.get("stdout_truncated")),
                "stderr_truncated": bool(envelope.get("stderr_truncated")),
            },
        )


_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    global _engine
    if _engine is None:
        max_per_session = 5
        try:
            from leagent.config.settings import get_settings

            max_per_session = get_settings().agent.max_executions_per_session
        except Exception:  # noqa: BLE001
            pass
        _engine = ExecutionEngine(max_per_session=max_per_session)
    return _engine


def init_execution_engine(
    *,
    default_policy: ExecutionPolicy | None = None,
    max_concurrent: int = 20,
    max_per_session: int = 5,
) -> ExecutionEngine:
    global _engine
    _engine = ExecutionEngine(
        default_policy=default_policy,
        max_concurrent=max_concurrent,
        max_per_session=max_per_session,
    )
    return _engine
