"""SkillScriptTool: run_skill_script — Level 4 of progressive disclosure.

Skills may bundle executable scripts under ``scripts/`` that perform
deterministic or side-effectful work (file munging, API calls, ...). The
agent invokes them through this tool; the implementation enforces a
strict safety envelope:

- Scripts must be pre-declared on the skill's manifest (i.e. discovered
  under ``scripts/`` with a permitted extension at load time).
- The resolved path must still live inside the skill directory.
- Execution can be turned off via ``Settings.skill_scripts_enabled`` /
  ``LEAGENT_SKILL_SCRIPTS_ENABLED=0`` for hardened deployments.
- The subprocess runs with a working directory equal to the skill's
  own directory, a configurable timeout and never through a shell.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

ENV_FLAG = "LEAGENT_SKILL_SCRIPTS_ENABLED"
DEFAULT_TIMEOUT_S = 60
MAX_TIMEOUT_S = 600
MAX_OUTPUT_CHARS = 200_000


class SkillScriptTool(BaseTool):
    """Execute a script bundled with an Agent Skill."""

    name = "run_skill_script"
    description = (
        "Run a script bundled with an installed Agent Skill. Use this "
        "only after the skill's SKILL.md instructs you to execute a "
        "specific script. Scripts are launched without a shell and are "
        "constrained to the skill directory."
    )
    category = ToolCategory.SKILLS
    is_read_only = False
    is_destructive = True
    is_concurrency_safe = False
    aliases = ["skill_script"]
    search_hint = "skill script run execute bundled python bash"
    interrupt_behavior = "cancel"
    max_result_size_chars = MAX_OUTPUT_CHARS

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        p = params or {}
        skill = p.get("name", "")
        path = p.get("script_path", "")
        return f"Running skill script: {skill}/{path}" if skill else "Running skill script"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": (
                        "Skill id from the Available skills list (matches SKILL.md name: field)."
                    ),
                },
                "script_path": {
                    "type": "string",
                    "description": "Path relative to the skill directory (e.g. 'scripts/run.py').",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional argument list passed to the script.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": f"Optional timeout in seconds (default {DEFAULT_TIMEOUT_S}, max {MAX_TIMEOUT_S}).",
                },
            },
            "required": ["name", "script_path"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        from leagent.config.settings import get_settings

        if not get_settings().skill_scripts_enabled:
            return {
                "ok": False,
                "message": (
                    "Skill script execution is disabled. Enable "
                    f"`skill_scripts_enabled` or set {ENV_FLAG}=1 in the environment."
                ),
            }

        skill_name = params["name"]
        script_path = params["script_path"]
        raw_args = params.get("args") or []
        if not isinstance(raw_args, (list, tuple)):
            raw_args = [str(raw_args)]
        args = [str(a) for a in raw_args]
        timeout_s = int(params.get("timeout_s") or DEFAULT_TIMEOUT_S)
        timeout_s = max(1, min(timeout_s, MAX_TIMEOUT_S))

        try:
            from leagent.skills.loader import is_path_inside
            from leagent.tools.skills import resolve_skills_manager

            manager = await resolve_skills_manager()
            if manager is None:
                return {"ok": False, "message": "Skills manager is not available."}

            skill = manager.get_skill(skill_name)
            if not skill:
                return {"ok": False, "message": f"Skill '{skill_name}' not found"}

            script = skill.get_script(script_path)
            if not script:
                available = [s.relative_path for s in skill.manifest.scripts[:20]]
                return {
                    "ok": False,
                    "message": (
                        f"Script '{script_path}' is not declared by skill "
                        f"'{skill.name}'. Only scripts discovered at load time are runnable."
                    ),
                    "available": available,
                }

            if not skill.path:
                return {"ok": False, "message": "Skill has no filesystem path"}

            if not is_path_inside(skill.path, script.absolute_path):
                logger.warning(
                    "skill_script_escape_attempt",
                    skill=skill_name,
                    path=str(script.absolute_path),
                )
                return {"ok": False, "message": "Script path escapes skill directory"}

            cmd = _build_command(script.absolute_path, script.interpreter)
            if not cmd:
                return {
                    "ok": False,
                    "message": f"No interpreter available for extension '{script.extension}'",
                }

            if script.interpreter == "python":
                from leagent.skills.python_deps import ensure_skill_python_deps

                dep_result = await ensure_skill_python_deps(skill)
                if not dep_result.get("ok"):
                    return {
                        "ok": False,
                        "message": dep_result.get("error", "Skill Python dependency install failed."),
                        "dependency_install": dep_result,
                    }

            logger.info(
                "skill_script_exec",
                skill=skill.name,
                script=script.relative_path,
                interpreter=script.interpreter,
            )
            return await _run_subprocess(cmd + args, cwd=skill.path, timeout_s=timeout_s)

        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "skill_script_failed",
                skill=skill_name,
                path=script_path,
                error=str(exc),
            )
            return {"ok": False, "error": str(exc)}


def _build_command(script_path: Path, interpreter: str) -> list[str] | None:
    """Return the argv prefix to launch the script, or None if we can't."""
    if interpreter == "python":
        import sys

        return [sys.executable, str(script_path)]
    if interpreter == "node":
        node = shutil.which("node")
        if not node:
            return None
        return [node, str(script_path)]
    if interpreter == "bash":
        bash = shutil.which("bash") or shutil.which("sh")
        if not bash:
            return None
        return [bash, str(script_path)]
    if interpreter == "pwsh":
        pwsh = shutil.which("pwsh") or shutil.which("powershell")
        if not pwsh:
            return None
        return [pwsh, "-NoProfile", "-File", str(script_path)]
    if interpreter == "dotnet-script":
        dotnet = shutil.which("dotnet")
        if not dotnet:
            return None
        return [dotnet, "script", str(script_path)]
    return None


async def _run_subprocess(cmd: list[str], cwd: Path, timeout_s: int) -> dict[str, Any]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"Executable not found: {exc}"}
    except OSError as exc:
        return {"ok": False, "error": f"Failed to spawn process: {exc}"}

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        try:
            stdout_b, stderr_b = await proc.communicate()
        except Exception:  # noqa: BLE001
            stdout_b, stderr_b = b"", b""
        return {
            "ok": False,
            "timeout": True,
            "timeout_s": timeout_s,
            "stdout": stdout_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS],
            "stderr": stderr_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS],
        }

    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": stdout_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS],
        "stderr": stderr_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS],
    }
