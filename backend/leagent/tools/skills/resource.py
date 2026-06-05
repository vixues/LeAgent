"""SkillResourceTool: read_skill_resource — Level 3 of progressive disclosure.

After a skill has been loaded (via ``load_skill``) the model can ask
for supplementary files under ``references/``, ``assets/``, or
allowed-extension files at the skill root (excluding ``SKILL.md``).
Only files discovered at load time are readable. Path traversal is
rejected up-front.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

MAX_CHARS = 200_000


class SkillResourceTool(BaseTool):
    """Read a bundled reference or asset file from an installed skill."""

    name = "read_skill_resource"
    description = (
        "Read a file bundled with an Agent Skill (references/, assets/, "
        "or root-level docs). Use this when a loaded skill points to a "
        "supplementary document. Returns UTF-8 decoded text for text "
        "files or a base64 payload for binary assets."
    )
    category = ToolCategory.SKILLS
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["read_skill_file", "skill_resource"]
    search_hint = "skill resource reference asset read bundled file"
    interrupt_behavior = "cancel"
    max_result_size_chars = MAX_CHARS

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        p = params or {}
        skill = p.get("name", "")
        path = p.get("resource_path", "")
        return f"Reading skill resource: {skill}/{path}" if skill else "Reading skill resource"

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
                "resource_path": {
                    "type": "string",
                    "description": (
                        "Path to the resource relative to the skill directory "
                        "(e.g. 'references/api.md' or 'assets/template.json')."
                    ),
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "Optional cap on bytes to return (default: 200000).",
                },
            },
            "required": ["name", "resource_path"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        skill_name = params["name"]
        resource_path = params["resource_path"]
        max_bytes = int(params.get("max_bytes") or MAX_CHARS)

        try:
            from leagent.skills.loader import is_path_inside
            from leagent.tools.skills import resolve_skills_manager

            manager = await resolve_skills_manager()
            if manager is None:
                return {"found": False, "message": "Skills manager is not available."}

            skill = manager.get_skill(skill_name)
            if not skill:
                return {"found": False, "message": f"Skill '{skill_name}' not found"}

            resource = skill.get_resource(resource_path)
            if not resource:
                available = [r.relative_path for r in skill.manifest.resources[:50]]
                return {
                    "found": False,
                    "message": (
                        f"Resource '{resource_path}' is not declared by skill "
                        f"'{skill.name}'. Only files discovered at load time are readable."
                    ),
                    "available": available,
                }

            if not skill.path:
                return {"found": False, "message": "Skill has no filesystem path"}

            if not is_path_inside(skill.path, resource.absolute_path):
                logger.warning(
                    "skill_resource_escape_attempt",
                    skill=skill_name,
                    path=str(resource.absolute_path),
                )
                return {"found": False, "message": "Resource path escapes skill directory"}

            cap = max(1024, min(max_bytes, MAX_CHARS))
            abs_path = resource.absolute_path
            from leagent.skills.resource_cache import (
                cache_key_for_path,
                get_cached_resource_payload,
                put_cached_resource_payload,
            )

            ck = cache_key_for_path(abs_path, cap)
            if ck is not None:
                cached = get_cached_resource_payload(ck)
                if cached is not None:
                    return cached
            out = _read_resource_payload(
                abs_path,
                max_bytes=max_bytes,
                resource=resource,
                name=skill.name,
            )
            if ck is not None:
                put_cached_resource_payload(ck, out)
            return out

        except Exception as exc:  # noqa: BLE001
            logger.warning("skill_resource_read_failed", skill=skill_name, path=resource_path, error=str(exc))
            return {"found": False, "error": str(exc)}


def _read_resource_payload(
    path: Path,
    *,
    max_bytes: int,
    resource: Any,
    name: str = "",
) -> dict[str, Any]:
    """Return a dict payload suitable for a ``tool_result`` message."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        return {"found": False, "error": f"Cannot stat resource: {exc}"}

    cap = max(1024, min(max_bytes, MAX_CHARS))
    try:
        data = path.read_bytes()[:cap]
    except OSError as exc:
        return {"found": False, "error": f"Cannot read resource: {exc}"}

    try:
        text = data.decode("utf-8")
        return {
            "found": True,
            "name": name or "",
            "resource_path": resource.relative_path,
            "kind": resource.kind.value,
            "encoding": "utf-8",
            "size": size,
            "truncated": size > cap,
            "content": text,
        }
    except UnicodeDecodeError:
        import base64

        return {
            "found": True,
            "name": name or "",
            "resource_path": resource.relative_path,
            "kind": resource.kind.value,
            "encoding": "base64",
            "size": size,
            "truncated": size > cap,
            "content_base64": base64.b64encode(data).decode("ascii"),
        }
