"""``project_shell`` — run build/test/git commands inside the project root.

Real coding work needs to talk to package managers, linters, type
checkers, test runners, and ``git``. Letting the LLM exec arbitrary
shell commands is a known-bad idea, so this tool ships with a curated
whitelist of binaries and routes every invocation through the unified
:class:`~leagent.services.execution.engine.ExecutionEngine` — the same
spawn site as ``code_execution`` — so sanitised env, hard timeout,
process-group reaping **and the optional OS-level sandbox wrapper
(bwrap / Seatbelt)** apply consistently.

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

import os
import shlex
import shutil
import sys
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


def _effective_max_timeout_sec(context: ToolContext) -> float:
    """Wall-clock cap for one ``project_shell`` invocation."""

    try:
        extra = getattr(context, "extra", None) or {}
        profile = extra.get("runtime_profile")
        if profile:
            from leagent.agent.runtime_profile import resolve_runtime_budget

            budget = resolve_runtime_budget(profile)
            if budget.name in ("coding_long", "coding_extended"):
                return float(budget.task_timeout_sec)
    except Exception:  # noqa: BLE001
        pass
    return MAX_TIMEOUT_SEC


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
        max_timeout = _effective_max_timeout_sec(context)
        timeout = max(1.0, min(max_timeout, timeout))
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

        session_id = getattr(context, "session_id", None)
        output_meta = {
            "tool_call_id": str(context.extra.get("current_tool_call_id") or ""),
            "tool_name": self.name,
            "source": "shell",
        }

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
            return await _run_via_engine(
                shell_script=shell_cmd,
                cwd=cwd_abs,
                env=env,
                timeout=timeout,
                stdin=stdin_data,
                session_id=str(session_id) if session_id else None,
                project_root=root,
                output_meta=output_meta,
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

        return await _run_via_engine(
            argv=_resolve_argv_executable(argv),
            cwd=cwd_abs,
            env=env,
            timeout=timeout,
            stdin=stdin_data,
            session_id=str(session_id) if session_id else None,
            project_root=root,
            output_meta=output_meta,
        )


def _build_engine_policy(
    *,
    env: dict[str, str],
    timeout: float,
    project_root: Path,
    free_shell: bool,
) -> "Any":
    """Build the per-call :class:`ExecutionPolicy` for the engine.

    The whitelist is enforced by the tool itself (with basename
    normalisation + interpreter fallback), so the engine-level binary
    check is disabled. The fully-built env is passed as ``extra_env``
    on an empty allowlist to reproduce the tool's historic env exactly.
    The OS sandbox spec (workspace-write over the project root) rides
    on the policy so ``ExecutionEngine`` wraps the argv when enabled.
    """
    from leagent.services.execution.os_sandbox import (
        SandboxSpec,
        default_writable_roots,
        resolve_sandbox_mode,
    )
    from leagent.services.execution.policies import ExecutionPolicy

    mode = resolve_sandbox_mode(None)
    network_raw = os.environ.get("LEAGENT_SANDBOX_NETWORK", "").strip().lower()
    network_access = network_raw not in ("0", "false", "no", "off")
    spec = SandboxSpec(
        mode=mode,
        writable_roots=default_writable_roots(str(project_root)),
        network_access=network_access,
    )
    return ExecutionPolicy(
        timeout_sec=timeout,
        max_timeout_sec=timeout,
        max_output_bytes=MAX_OUTPUT_BYTES,
        allowed_binaries=None,
        allow_free_shell=free_shell,
        env_allowlist=frozenset(),
        extra_env=env,
        sandbox_spec=spec,
    )


async def _run_via_engine(
    *,
    argv: list[str] | None = None,
    shell_script: str | None = None,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    stdin: str,
    session_id: str | None,
    project_root: Path,
    output_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Route the command through the unified :class:`ExecutionEngine`."""
    from leagent.services.execution.engine import get_execution_engine

    policy = _build_engine_policy(
        env=env,
        timeout=timeout,
        project_root=project_root,
        free_shell=shell_script is not None,
    )
    stdin_data = stdin.encode("utf-8") if (stdin or "").strip() else None
    engine = get_execution_engine()

    if shell_script is not None:
        result = await engine.shell_script(
            shell_script,
            cwd=str(cwd),
            policy=policy,
            timeout_sec=timeout,
            stdin_data=stdin_data,
            session_id=session_id,
            output_meta=output_meta,
        )
        display_argv = shlex.split(shell_script) if os.name != "nt" else [shell_script]
    else:
        assert argv is not None
        result = await engine.shell_command(
            argv,
            cwd=str(cwd),
            policy=policy,
            timeout_sec=timeout,
            stdin_data=stdin_data,
            session_id=session_id,
            output_meta=output_meta,
        )
        display_argv = argv

    if result.metadata.get("not_found"):
        return {
            "error": (
                f"Command not found on PATH: {display_argv[0]!r}. Install "
                "the binary or use a different one."
            ),
            "argv": display_argv,
        }
    if result.status == "crash":
        return {
            "status": "error",
            "argv": display_argv,
            "duration_ms": result.duration_ms,
            "error": f"Failed while running subprocess: {result.error}",
        }
    if result.status == "timeout":
        return {
            "status": "timeout",
            "argv": display_argv,
            "duration_ms": result.duration_ms,
            "error": f"Command timed out after {timeout:.0f}s",
        }

    out: dict[str, Any] = {
        "status": "ok" if result.returncode == 0 else "error",
        "argv": display_argv,
        "returncode": result.returncode,
        "duration_ms": result.duration_ms,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "stdout_truncated": bool(result.metadata.get("stdout_truncated")),
        "stderr_truncated": bool(result.metadata.get("stderr_truncated")),
    }
    if result.metadata.get("sandbox_applied"):
        out["sandbox"] = {
            "backend": result.metadata.get("sandbox_backend"),
            "network_isolated": bool(result.metadata.get("sandbox_network_isolated")),
        }
    try:
        from leagent.services.diagnostics_parsers import extract_shell_diagnostics

        src, diags = extract_shell_diagnostics(display_argv, result.stdout, result.stderr)
        if src and diags:
            out["diagnostics_source"] = src
            out["diagnostics"] = diags
    except Exception:  # noqa: BLE001 — never fail the shell tool on parser bugs
        logger.debug("shell_diagnostics_parse_skipped", exc_info=True)
    return out
