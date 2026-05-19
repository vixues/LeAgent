"""Install Python packages into the backend interpreter via ``uv pip install``.

``code_execution`` runs ``python -m leagent.services.code_execution.runner`` using
the resolved backend interpreter. Third-party imports (and legacy
``pkg_resources`` from ``setuptools``) therefore require packages to be present
in that environment. This tool runs:

``uv pip install --python <resolved backend Python> …``

— the same mechanism as skill-declared dependencies — with explicit PEP 508
specs and/or a requirements file staged under the session code workspace.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.services.python_env.resolve import resolve_backend_python_executable
from leagent.skills.python_deps import run_uv_pip_install
from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.services.code_execution import WorkspaceManager
from leagent.tools.code.execution import CodeExecutionConfig, build_default_code_execution_config

logger = structlog.get_logger(__name__)

_MAX_PACKAGES = 48
_MAX_SPEC_LEN = 512


def _normalize_packages(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        spec = item.strip()
        if not spec or "\n" in spec or "\r" in spec:
            continue
        if len(spec) > _MAX_SPEC_LEN:
            continue
        out.append(spec)
        if len(out) >= _MAX_PACKAGES:
            break
    return out


class UvPipInstallTool(BaseTool):
    """Expose ``uv pip install`` for the agent-driven code execution interpreter."""

    name = "uv_pip_install"
    description = (
        "Install Python packages into the same interpreter used by code_execution "
        "using uv (`uv pip install --python <backend>`). Use this when sandbox code "
        "fails with ImportError / ModuleNotFoundError (including missing "
        "`pkg_resources` — install `setuptools`). Pass PEP 508 specs such as "
        "`pandas`, `numpy==2.1.0`, or `setuptools>=69`. Optional "
        "`requirements_workspace_path` is relative to the session code workspace "
        "(same root as code_execution cwd). Requires uv on the server PATH. "
        "Mutates the backend environment — use sparingly."
    )
    category = ToolCategory.CODE
    version = "1.0.0"
    search_hint = "uv pip install python package setuptools pkg_resources code_execution"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "deny"
    max_result_size_chars = 120_000

    def __init__(self, *, config: CodeExecutionConfig | None = None) -> None:
        cfg = config if config is not None else build_default_code_execution_config()
        self._config = cfg
        self._workspaces = WorkspaceManager(
            cfg.workspace_root,
            max_workspace_bytes=cfg.max_workspace_bytes,
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "packages": {
                    "type": "array",
                    "description": (
                        "PEP 508 dependency specs to pass to uv (e.g. `httpx`, "
                        "`setuptools`, `somepkg==1.2.3`). Max "
                        f"{_MAX_PACKAGES} entries, each ≤ {_MAX_SPEC_LEN} chars."
                    ),
                    "items": {"type": "string"},
                    "default": [],
                },
                "requirements_workspace_path": {
                    "type": "string",
                    "description": (
                        "Optional path to a requirements file **inside** the session "
                        "code workspace (relative only; same cwd as code_execution). "
                        "Example: `requirements.txt`."
                    ),
                },
            },
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Installing Python packages (uv)"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        from leagent.config.settings import get_settings

        settings = get_settings()
        if not settings.agent_uv_pip_install_enabled:
            return {
                "status": "error",
                "ok": False,
                "error": "uv_pip_install is disabled (LEAGENT_AGENT_UV_PIP_INSTALL_ENABLED=0).",
            }

        packages = _normalize_packages(params.get("packages"))
        req_rel = params.get("requirements_workspace_path")
        req_rel_str = str(req_rel).strip() if isinstance(req_rel, str) else ""

        workspace = self._workspaces.get(
            user_id=context.user_id,
            session_id=context.session_id,
            metadata={
                "user_id": context.user_id or "",
                "session_id": context.session_id or "",
                "task_id": context.task_id or "",
            },
        )
        workspace.ensure()

        req_file: Path | None = None
        if req_rel_str:
            rel = Path(req_rel_str)
            if rel.is_absolute() or ".." in rel.parts:
                return {
                    "status": "error",
                    "ok": False,
                    "error": f"Unsafe workspace-relative path: {req_rel_str!r}",
                }
            candidate = (workspace.path / rel).resolve()
            try:
                if not candidate.is_relative_to(workspace.path.resolve()):
                    return {
                        "status": "error",
                        "ok": False,
                        "error": "requirements path must stay inside the code workspace",
                    }
            except (AttributeError, ValueError):
                return {"status": "error", "ok": False, "error": "invalid requirements path"}
            if not candidate.is_file():
                return {
                    "status": "error",
                    "ok": False,
                    "error": f"requirements file not found: {req_rel_str!r}",
                }
            req_file = candidate

        if not packages and req_file is None:
            return {
                "status": "error",
                "ok": False,
                "error": "Provide at least one package in `packages` or `requirements_workspace_path`.",
            }

        py_resolved = resolve_backend_python_executable()

        timeout = float(settings.skill_python_deps_install_timeout_sec)
        logger.info(
            "agent_uv_pip_install",
            package_count=len(packages),
            has_requirements_file=bool(req_file),
            python=py_resolved,
        )

        result = await run_uv_pip_install(
            python_executable=py_resolved,
            packages=packages,
            requirements_file=req_file,
            timeout_sec=timeout,
        )
        if not result.get("ok"):
            return {
                "status": "error",
                "ok": False,
                "error": str(result.get("error") or "uv pip install failed"),
                "returncode": result.get("returncode"),
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
                "python_executable": py_resolved,
            }

        return {
            "status": "ok",
            "ok": True,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "python_executable": py_resolved,
        }
