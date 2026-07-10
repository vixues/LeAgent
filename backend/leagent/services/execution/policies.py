"""Execution policies for different callers.

Each policy defines resource limits, environment rules, and binary
whitelists that the ExecutionEngine enforces. Agents get conservative
defaults; cron jobs and workflows may use relaxed limits.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from leagent.services.execution.os_sandbox import SandboxSpec


@dataclass(frozen=True)
class ExecutionPolicy:
    """Base execution policy with configurable limits."""
    timeout_sec: float = 120.0
    max_timeout_sec: float = 600.0
    memory_bytes: int = 512 * 1024 * 1024
    file_bytes: int = 128 * 1024 * 1024
    open_files: int = 256
    max_processes: int = 64
    max_output_bytes: int = 200_000
    allowed_binaries: frozenset[str] | None = None
    allow_free_shell: bool = False
    #: Optional OS-level sandbox description (bwrap/Seatbelt). ``None``
    #: preserves legacy direct execution.
    sandbox_spec: "SandboxSpec | None" = None
    env_allowlist: frozenset[str] = frozenset({
        "PATH", "PYTHONPATH", "PYTHONIOENCODING",
        "LC_ALL", "LC_CTYPE", "LANG", "HOME", "TMPDIR",
    })
    extra_env: dict[str, str] = field(default_factory=dict)
    grace_sec: float = 2.0

    @classmethod
    def agent(cls, **overrides: Any) -> "ExecutionPolicy":
        """Policy for LLM-driven agent tool calls."""
        defaults = {
            "timeout_sec": 120.0,
            "max_timeout_sec": 600.0,
            "memory_bytes": 512 * 1024 * 1024,
            "file_bytes": 128 * 1024 * 1024,
            "open_files": 256,
            "max_processes": 64,
            "allowed_binaries": _DEFAULT_AGENT_BINARIES,
            "allow_free_shell": False,
        }
        return cls(**{**defaults, **overrides})

    @classmethod
    def cron(cls, **overrides: Any) -> "ExecutionPolicy":
        """Relaxed policy for trusted scheduled jobs."""
        defaults = {
            "timeout_sec": 300.0,
            "max_timeout_sec": 3600.0,
            "memory_bytes": 512 * 1024 * 1024,
            "allowed_binaries": None,
            "allow_free_shell": True,
        }
        return cls(**{**defaults, **overrides})

    @classmethod
    def workflow(cls, **overrides: Any) -> "ExecutionPolicy":
        """Per-node configurable policy for workflow steps."""
        defaults = {
            "timeout_sec": 180.0,
            "max_timeout_sec": 1800.0,
            "memory_bytes": 512 * 1024 * 1024,
            "allowed_binaries": None,
            "allow_free_shell": False,
        }
        return cls(**{**defaults, **overrides})

    def effective_timeout(self, requested: float | None) -> float:
        if requested is None:
            return self.timeout_sec
        return min(float(requested), self.max_timeout_sec)

    def sanitized_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k in self.env_allowlist}
        if os.name == "nt":
            for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE"):
                val = os.environ.get(key)
                if val:
                    env[key] = val
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.update(self.extra_env)
        if extra:
            env.update(extra)
        return env


_DEFAULT_AGENT_BINARIES: frozenset[str] = frozenset({
    "python", "python3", "py", "pip", "pip3", "pipx", "uv", "poetry",
    "ruff", "black", "mypy", "pyright", "pylint", "pytest", "tox",
    "node", "npm", "pnpm", "yarn", "npx", "tsc", "eslint", "prettier",
    "vitest", "jest", "playwright",
    "cargo", "rustc", "go", "gofmt", "mvn", "gradle", "java", "javac",
    "git", "make", "cmake", "ctest", "bash", "sh", "pwsh", "powershell",
    "dotnet",
    "uvicorn", "hypercorn", "granian", "daphne",
})


def AgentPolicy(**overrides: Any) -> ExecutionPolicy:
    """Compatibility shim for the old subclass constructor."""
    return ExecutionPolicy.agent(**overrides)


def CronPolicy(**overrides: Any) -> ExecutionPolicy:
    """Compatibility shim for the old subclass constructor."""
    return ExecutionPolicy.cron(**overrides)


def WorkflowPolicy(**overrides: Any) -> ExecutionPolicy:
    """Compatibility shim for the old subclass constructor."""
    return ExecutionPolicy.workflow(**overrides)
