"""``project_shell`` — run build/test/git commands inside the project root.

Real coding work needs to talk to package managers, linters, type
checkers, test runners, and ``git``. Letting the LLM exec arbitrary
shell commands is a known-bad idea, so this tool ships with a curated
whitelist of binaries and runs every invocation through the same
``SubprocessSandbox`` plumbing the existing ``code_execution`` tool
uses (sanitised env, hard timeout, ``start_new_session=True`` on POSIX
so a SIGKILL reaps the whole process group).

Two modes:

* **Curated (default).** ``argv[0]`` must match :data:`DEFAULT_ALLOW`
  (or the comma-separated ``LEAGENT_CODING_SHELL_ALLOW`` env). Each
  command is exec'd directly — no shell interpolation, no ``rm -rf /``
  one-liners.
* **Free-form (opt-in).** When the operator sets
  ``LEAGENT_CODING_AGENT_FREE_SHELL=1`` the tool also accepts a
  ``shell`` string that is run through the system shell. This is for
  trusted single-tenant deployments where the agent needs full
  flexibility (e.g. for piping commands together).

Output is captured and truncated to the tool's ``max_result_size_chars``
so a runaway test log can't blow up the context window. The exit code,
duration, and a "command_summary" (first arg + first three args) are
always returned so the agent can quickly tell success from failure.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ToolResult
from leagent.project.fs import (
    select_project_root,
)

logger = structlog.get_logger(__name__)


#: Default whitelist of binaries the coding agent may invoke. Operators
#: override or extend with comma-separated ``LEAGENT_CODING_SHELL_ALLOW``.
DEFAULT_ALLOW: tuple[str, ...] = (
    # Python
    "python", "python3", "py", "pip", "pip3", "pipx", "uv", "poetry",
    "ruff", "black", "mypy", "pyright", "pylint", "pytest", "tox",
    # Node / TS
    "node", "npm", "pnpm", "yarn", "npx", "tsc", "eslint", "prettier",
    "vitest", "jest", "playwright",
    # Rust / Go / JVM
    "cargo", "rustc", "go", "gofmt", "mvn", "gradle", "java", "javac",
    # Generic
    "git", "make", "cmake", "ctest", "bash", "sh", "pwsh", "powershell",
    "dotnet",
    # Local app servers (single-machine / dev)
    "uvicorn", "hypercorn", "granian", "daphne",
)

#: Hard wall-clock cap regardless of what the LLM passes in.
MAX_TIMEOUT_SEC: float = 600.0
#: Default timeout for one invocation.
DEFAULT_TIMEOUT_SEC: float = 120.0
#: Bytes of stdout/stderr we keep before truncating.
MAX_OUTPUT_BYTES: int = 200_000


def _allowed_binaries() -> set[str]:
    """Resolve the active whitelist from env, falling back to the default."""
    raw = os.environ.get("LEAGENT_CODING_SHELL_ALLOW", "")
    if raw.strip():
        return {tok.strip().lower() for tok in raw.split(",") if tok.strip()}
    return {b.lower() for b in DEFAULT_ALLOW}


def _free_shell_enabled() -> bool:
    raw = os.environ.get("LEAGENT_CODING_AGENT_FREE_SHELL", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    try:
        from leagent.config.settings import get_settings

        return bool(get_settings().coding_agent_free_shell)
    except Exception:  # noqa: BLE001
        return False


def _binary_basename(arg0: str) -> str:
    """Strip directory + extension so ``/usr/bin/python3`` matches ``python3``."""
    leaf = Path(arg0).name.lower()
    if leaf.endswith((".exe", ".cmd", ".bat", ".ps1")):
        leaf = leaf.rsplit(".", 1)[0]
    return leaf


def _resolve_argv_executable(argv: list[str]) -> list[str]:
    """Return argv with ``python``/``python3`` falling back to this interpreter.

    Some Linux distributions intentionally do not install a ``python`` shim,
    while tests and starter templates commonly use ``python -c``. Using the
    active interpreter keeps behaviour deterministic inside ``backend/.venv``
    without broadening the shell allow-list.
    """
    if not argv:
        return argv
    arg0 = argv[0]
    if shutil.which(arg0):
        return argv
    if _binary_basename(arg0) in {"python", "python3", "py"}:
        candidate = Path(sys.executable)
        if candidate.exists():
            return [str(candidate), *argv[1:]]
    return argv


def _sandbox_env() -> dict[str, str]:
    """Build the env dict for the child process.

    Mirrors :class:`leagent.services.code_execution.SubprocessSandbox._env`
    so behaviour is consistent: minimal allow-list on POSIX, full
    parent env on Windows (Winsock breaks otherwise), with utf-8
    forced and bytecode writes disabled.
    """
    allow = {
        "PATH", "PYTHONPATH", "PYTHONIOENCODING", "LC_ALL", "LC_CTYPE",
        "LANG", "HOME", "TMPDIR", "USER", "USERNAME",
    }
    env: dict[str, str] = {k: v for k, v in os.environ.items() if k in allow}
    if os.name == "nt":
        for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE",
                    "APPDATA", "LOCALAPPDATA", "PROGRAMFILES",
                    "PROGRAMFILES(X86)", "COMSPEC", "PATHEXT"):
            val = os.environ.get(key)
            if val:
                env[key] = val
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("CI", "1")
    return env


class ProjectShellTool(BaseTool):
    """Run a curated build/test/git command inside the project root."""

    name = "project_shell"
    description = (
        "Run a command inside the active project root. By default only "
        "a curated whitelist of binaries is allowed (python, pip, npm, "
        "node, pytest, ruff, eslint, git, make, cargo, go, …). Set "
        "LEAGENT_CODING_AGENT_FREE_SHELL=1 in the deployment env to "
        "enable free-form shell. Each call has a wall-clock timeout, a "
        "sanitised environment, and runs in its own process group so a "
        "hung child is reliably reaped. Stdout/stderr are returned "
        "truncated; write large output to a file in the project."
    )
    category = ToolCategory.CODE
    aliases = ["shell", "run_command", "code_shell"]
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 220_000
    timeout_sec = int(MAX_TIMEOUT_SEC) + 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "argv": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Command and arguments as a list. The first "
                        "element must match the curated whitelist "
                        "unless free-form shell is enabled."
                    ),
                    "minItems": 1,
                },
                "shell": {
                    "type": "string",
                    "description": (
                        "Free-form shell command. Only honoured when "
                        "LEAGENT_CODING_AGENT_FREE_SHELL=1; rejected "
                        "otherwise. Mutually exclusive with `argv`."
                    ),
                },
                "cwd": {
                    "type": "string",
                    "description": (
                        "Subdirectory of the project root to run in. "
                        "Defaults to the project root itself."
                    ),
                },
                "timeout_sec": {
                    "type": "number",
                    "description": "Wall-clock timeout in seconds.",
                    "minimum": 1,
                    "maximum": MAX_TIMEOUT_SEC,
                    "default": DEFAULT_TIMEOUT_SEC,
                },
                "env": {
                    "type": "object",
                    "description": (
                        "Extra env vars to set for this call only. The "
                        "base env is sanitised; values set here are "
                        "merged on top."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "stdin": {
                    "type": "string",
                    "description": "Optional stdin to pipe into the command.",
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Optional override of the active project root."
                    ),
                },
            },
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        argv = (params or {}).get("argv") or []
        if argv:
            return f"Running {argv[0]}"
        if (params or {}).get("shell"):
            return "Running shell command"
        return "Running command"

    def coerce_tool_result(self, raw: Any, *, duration_ms: int, attempt: int) -> ToolResult:
        if isinstance(raw, dict):
            if raw.get("error") and "status" not in raw:
                err = str(raw["error"])
                return ToolResult.fail(err, duration_ms=duration_ms, data=raw, attempts=attempt)
            status = str(raw.get("status") or "")
            if status in {"error", "timeout"}:
                err = str(raw.get("error") or status)
                return ToolResult.fail(err, duration_ms=duration_ms, data=raw, attempts=attempt)
            rc = raw.get("returncode")
            if isinstance(rc, int) and rc != 0:
                err = str(raw.get("error") or f"command exited with code {rc}")
                return ToolResult.fail(err, duration_ms=duration_ms, data=raw, attempts=attempt)
        return ToolResult.ok(raw, duration_ms=duration_ms, attempts=attempt)

    async def execute(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        root = select_project_root(
            context, explicit=params.get("project_path"),
        )
        cwd_rel = (params.get("cwd") or "").strip()
        cwd_abs = root if not cwd_rel else (root / cwd_rel).resolve()
        try:
            cwd_abs.relative_to(root)
        except ValueError:
            return {"error": f"`cwd` {cwd_rel!r} escapes project root."}
        if not cwd_abs.is_dir():
            return {"error": f"`cwd` {cwd_rel!r} is not a directory."}

        argv = params.get("argv")
        shell_cmd = params.get("shell")
        if argv and shell_cmd:
            return {"error": "Provide either `argv` or `shell`, not both."}
        if not argv and not shell_cmd:
            return {"error": "One of `argv` or `shell` is required."}

        timeout = float(params.get("timeout_sec") or DEFAULT_TIMEOUT_SEC)
        timeout = max(1.0, min(MAX_TIMEOUT_SEC, timeout))
        extra_env = params.get("env") or {}
        if not isinstance(extra_env, dict):
            return {"error": "`env` must be an object."}
        env = _sandbox_env()
        for k, v in extra_env.items():
            if isinstance(k, str) and isinstance(v, str):
                env[k] = v

        stdin_data = params.get("stdin") or ""

        free_shell = _free_shell_enabled()
        allow = _allowed_binaries()

        if shell_cmd:
            if not free_shell:
                return {
                    "error": (
                        "Free-form `shell` is disabled. Set "
                        "LEAGENT_CODING_AGENT_FREE_SHELL=1 in the "
                        "deployment env or use `argv` with a curated "
                        "binary."
                    ),
                }
            return await _run_shell(
                shell_cmd, cwd=cwd_abs, env=env, timeout=timeout,
                stdin=stdin_data,
            )

        if not isinstance(argv, list) or not argv or not all(
            isinstance(a, str) for a in argv
        ):
            return {"error": "`argv` must be a non-empty list of strings."}

        binary = _binary_basename(argv[0])
        if not free_shell and binary not in allow:
            return {
                "error": (
                    f"Binary {argv[0]!r} (resolved to {binary!r}) is not "
                    "in the curated whitelist. Allowed: " +
                    ", ".join(sorted(allow))
                ),
            }

        return await _run_argv(
            _resolve_argv_executable(argv),
            cwd=cwd_abs,
            env=env,
            timeout=timeout,
            stdin=stdin_data,
        )


async def _run_argv(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    stdin: str,
) -> dict[str, Any]:
    """Spawn ``argv`` directly without going through the shell."""
    started = time.monotonic()
    try:
        # Avoid stdin=PIPE when there is nothing to send: on Windows (Proactor)
        # asyncio + PIPE can surface empty BrokenPipeError/ConnectionResetError
        # from communicate(); DEVNULL matches "no stdin" without a pipe pair.
        use_stdin_pipe = bool((stdin or "").strip())
        kwargs: dict[str, Any] = dict(
            stdin=asyncio.subprocess.PIPE if use_stdin_pipe else subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=str(cwd),
        )
        if os.name != "nt":
            kwargs["start_new_session"] = True
        proc = await asyncio.create_subprocess_exec(*argv, **kwargs)
    except FileNotFoundError:
        return {
            "error": (
                f"Command not found on PATH: {argv[0]!r}. Install the "
                "binary or use a different one."
            ),
            "argv": argv,
        }
    except OSError as exc:
        return {"error": f"Failed to spawn {argv[0]!r}: {exc}", "argv": argv}

    return await _await_proc(
        proc, argv=argv, started=started, timeout=timeout, stdin=stdin,
    )


async def _run_shell(
    cmd: str,
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    stdin: str,
) -> dict[str, Any]:
    """Run ``cmd`` through the system shell (only when opt-in is on)."""
    started = time.monotonic()
    use_stdin_pipe = bool((stdin or "").strip())
    kwargs: dict[str, Any] = dict(
        stdin=asyncio.subprocess.PIPE if use_stdin_pipe else subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=str(cwd),
    )
    if os.name != "nt":
        kwargs["start_new_session"] = True
    proc = await asyncio.create_subprocess_shell(cmd, **kwargs)
    return await _await_proc(
        proc,
        argv=shlex.split(cmd) if os.name != "nt" else [cmd],
        started=started,
        timeout=timeout,
        stdin=stdin,
    )


async def _await_proc(
    proc: asyncio.subprocess.Process,
    *,
    argv: list[str],
    started: float,
    timeout: float,
    stdin: str,
) -> dict[str, Any]:
    """Common timeout + capture path used by both spawn modes."""
    try:
        if (stdin or "").strip():
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin.encode("utf-8")),
                timeout=timeout,
            )
        else:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
    except asyncio.TimeoutError:
        _kill(proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "status": "timeout",
            "argv": argv,
            "duration_ms": duration_ms,
            "error": f"Command timed out after {timeout:.0f}s",
        }
    except Exception as exc:
        _kill(proc)
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        duration_ms = int((time.monotonic() - started) * 1000)
        detail = f"{type(exc).__name__}: {exc!s}" if str(exc) else repr(exc)
        return {
            "status": "error",
            "argv": argv,
            "duration_ms": duration_ms,
            "error": f"Failed while running subprocess: {detail}",
        }

    duration_ms = int((time.monotonic() - started) * 1000)
    rc = proc.returncode if proc.returncode is not None else -1
    out_text, out_truncated = _decode_capped(stdout)
    err_text, err_truncated = _decode_capped(stderr)
    out: dict[str, Any] = {
        "status": "ok" if rc == 0 else "error",
        "argv": argv,
        "returncode": rc,
        "duration_ms": duration_ms,
        "stdout": out_text,
        "stderr": err_text,
        "stdout_truncated": out_truncated,
        "stderr_truncated": err_truncated,
    }
    try:
        from leagent.services.diagnostics_parsers import extract_shell_diagnostics

        src, diags = extract_shell_diagnostics(argv, out_text, err_text)
        if src and diags:
            out["diagnostics_source"] = src
            out["diagnostics"] = diags
    except Exception:  # noqa: BLE001 — never fail the shell tool on parser bugs
        logger.debug("shell_diagnostics_parse_skipped", exc_info=True)
    return out


def _decode_capped(buf: bytes) -> tuple[str, bool]:
    """Decode UTF-8 with replacement and cap to ``MAX_OUTPUT_BYTES``."""
    if len(buf) > MAX_OUTPUT_BYTES:
        return (
            buf[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            + "\n... [truncated]",
            True,
        )
    return buf.decode("utf-8", errors="replace"), False


def _kill(proc: asyncio.subprocess.Process) -> None:
    """Kill the child process group on POSIX, the process on Windows."""
    pid = proc.pid
    if pid is None:
        return
    if hasattr(os, "killpg") and hasattr(os, "getpgid"):
        try:
            import signal as _signal
            os.killpg(os.getpgid(pid), _signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass
