"""install_skill — install an Agent Skill from URL, registry, workspace, or an uploaded archive."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_MAX_INFO = 8_000


def _skill_summary(skill: Any) -> dict[str, Any]:
    return {
        "name": skill.name,
        "version": skill.version,
        "description": (skill.description or "")[:500],
        "source": skill.source.value if skill.source else "",
    }


class InstallSkillTool(BaseTool):
    """Install a v1.0 Agent Skill into the LeAgent skills directory (chat-friendly)."""

    name = "install_skill"
    description = (
        "Install an Agent Skill (SKILL.md bundle) so it becomes available to load_skill. "
        "Use when the user pastes an https:// link to a .zip or .tar.gz skill archive, "
        "names a skill from the configured registry, points to a skill directory in the "
        "project/workspace, or attached a skill archive. Only https:// URLs are allowed."
    )
    category = ToolCategory.SKILLS
    is_read_only = False
    is_destructive = True
    is_concurrency_safe = False
    aliases = ["skill_install", "add_skill"]
    search_hint = "install skill zip url registry hub workspace upload archive"
    interrupt_behavior = "block"
    max_result_size_chars = _MAX_INFO
    path_params = ("workspace_path",)

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        p = params or {}
        st = p.get("source_type", "")
        return f"Installing skill ({st})" if st else "Installing skill"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_type": {
                    "type": "string",
                    "enum": ["url", "registry", "workspace", "uploaded_archive"],
                    "description": "Where to install from.",
                },
                "url": {
                    "type": "string",
                    "description": "For source_type=url: https:// location of .zip or .tar.gz",
                },
                "sha256": {
                    "type": "string",
                    "description": "Optional hex SHA-256 of the archive bytes (url only).",
                },
                "registry_skill_name": {
                    "type": "string",
                    "description": "For source_type=registry: skill id/name from the hub.",
                },
                "workspace_path": {
                    "type": "string",
                    "description": (
                        "For source_type=workspace: path to a skill directory under the "
                        "project or uploads sandbox (must contain SKILL.md)."
                    ),
                },
                "target_skill_name": {
                    "type": "string",
                    "description": (
                        "For source_type=workspace: kebab-case folder name / SKILL.md name "
                        "(must match the directory's SKILL.md `name` field)."
                    ),
                },
                "file_id": {
                    "type": "string",
                    "description": (
                        "For source_type=uploaded_archive: UUID or path of an attached "
                        ".zip / .tar.gz / .tgz file."
                    ),
                },
            },
            "required": ["source_type"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        from leagent.tools.skills import resolve_skills_manager

        manager = await resolve_skills_manager()
        if manager is None:
            return {"ok": False, "message": "Skills manager is not available."}

        st = params.get("source_type") or ""
        try:
            if st == "url":
                return await self._install_url(manager, params)
            if st == "registry":
                return await self._install_registry(manager, params)
            if st == "workspace":
                return await self._install_workspace(manager, params)
            if st == "uploaded_archive":
                return await self._install_uploaded(manager, params, context)
        except Exception as exc:  # noqa: BLE001
            logger.warning("install_skill_failed", source_type=st, error=str(exc))
            return {"ok": False, "message": str(exc)}
        return {"ok": False, "message": f"Unknown source_type: {st!r}"}

    async def _install_url(self, manager: Any, params: dict[str, Any]) -> dict[str, Any]:
        from leagent.skills.url_install import SkillURLError

        url = (params.get("url") or "").strip()
        if not url:
            return {"ok": False, "message": "Parameter `url` is required for source_type=url."}
        sha = (params.get("sha256") or "").strip() or None
        try:
            skill = await manager.install_from_url(url, sha256=sha)
        except SkillURLError as exc:
            return {"ok": False, "message": str(exc)}
        if skill is None:
            return {"ok": False, "message": "Install failed (skills directory not configured or error)."}
        return {"ok": True, "skill": _skill_summary(skill), "message": f"Installed skill '{skill.name}'."}

    async def _install_registry(self, manager: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = (params.get("registry_skill_name") or "").strip()
        if not name:
            return {
                "ok": False,
                "message": "Parameter `registry_skill_name` is required for source_type=registry.",
            }
        skill = await manager.install_from_hub(name)
        if skill is None:
            return {
                "ok": False,
                "message": (
                    "Registry install failed. Ensure LEAGENT_SKILLS_REGISTRY_URL (or config) "
                    "is set and the skill exists."
                ),
            }
        return {"ok": True, "skill": _skill_summary(skill), "message": f"Installed skill '{skill.name}'."}

    async def _install_workspace(self, manager: Any, params: dict[str, Any]) -> dict[str, Any]:
        from leagent.skills.local_install import LocalSkillInstallError

        raw = (params.get("workspace_path") or "").strip()
        target = (params.get("target_skill_name") or "").strip()
        if not raw:
            return {
                "ok": False,
                "message": "Parameter `workspace_path` is required for source_type=workspace.",
            }
        if not target:
            return {
                "ok": False,
                "message": "Parameter `target_skill_name` is required for source_type=workspace.",
            }

        source = Path(params["workspace_path"])
        if not source.is_dir():
            return {"ok": False, "message": f"Not a directory: {source}"}

        try:
            skill = await manager.install_from_local_directory(source, target)
        except LocalSkillInstallError as exc:
            return {"ok": False, "message": str(exc)}
        if skill is None:
            return {"ok": False, "message": "Install failed (skills directory not configured or error)."}
        return {"ok": True, "skill": _skill_summary(skill), "message": f"Installed skill '{skill.name}'."}

    async def _install_uploaded(
        self, manager: Any, params: dict[str, Any], context: ToolContext
    ) -> dict[str, Any]:
        from leagent.file.sandbox import PathSandbox
        from leagent.skills.url_install import SkillURLError

        fid = (params.get("file_id") or "").strip()
        if not fid:
            return {
                "ok": False,
                "message": "Parameter `file_id` is required for source_type=uploaded_archive.",
            }

        req = context.extra.get("request_id", context.session_id or "")
        try:
            archive_path = PathSandbox.resolve_safe(
                fid,
                context=context,
                allow_create=False,
                tool_name=self.name,
                request_id=str(req),
            )
        except PermissionError as exc:
            return {"ok": False, "message": str(exc)}

        if not archive_path.is_file():
            return {"ok": False, "message": f"Not a file: {archive_path}"}

        name_l = archive_path.name.lower()
        if not (name_l.endswith(".zip") or name_l.endswith(".tar.gz") or name_l.endswith(".tgz")):
            return {
                "ok": False,
                "message": "Attachment must be a .zip, .tar.gz, or .tgz skill archive.",
            }

        try:
            skill = await manager.install_from_local_archive(archive_path)
        except SkillURLError as exc:
            return {"ok": False, "message": str(exc)}
        if skill is None:
            return {"ok": False, "message": "Install failed (skills directory not configured or error)."}
        return {"ok": True, "skill": _skill_summary(skill), "message": f"Installed skill '{skill.name}'."}
