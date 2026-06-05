"""SkillTool: load_skill — Level 2 of the Agent Skills progressive disclosure.

At startup the ``SkillsManager`` advertises the ``name`` + ``description``
of every installed skill in the system prompt (Level 1). When the model
decides a skill is relevant, it calls the ``load_skill`` tool defined
here; the tool reads the skill's SKILL.md body from disk (lazy) and
returns it as a ``tool_result`` message that the model can act on.

The body is read through ``Skill.read_body`` which caches by file
mtime, so repeated calls within the same session do not re-hit disk.
Bundled payloads and ``read_skill_resource`` responses use small
process-local LRU caches (invalidated by content revision / file mtime);
no extra configuration is required.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class SkillTool(BaseTool):
    """Load a skill's instructions (SKILL.md body) on demand."""

    name = "load_skill"
    description = (
        "Load the full instructions of an Agent Skill by name. Call this "
        "when the current task matches one of the advertised skills. "
        "By default returns the SKILL.md body plus metadata paths for bundled files "
        "(progressive disclosure). For full context in one response, pass "
        "`include_bundled_content: true`, or ask the skill author to set "
        "`metadata.leagent.bundle_on_load: true` in SKILL.md, or enable "
        "`LEAGENT_SKILL_LOAD_BUNDLE_DEFAULT` on the server. "
        "Optional `bundled_resources` / `bundled_scripts` refine what is inlined when "
        "bundling is enabled. "
        "Binary assets are not base64-inlined here — use `read_skill_resource`. "
        "Scripts are inlined as source only; execution stays on `run_skill_script`. "
        "Use `read_skill_resource` / `run_skill_script` for omitted or truncated files."
    )
    category = ToolCategory.SKILLS
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["skill", "knowledge", "load_knowledge"]
    search_hint = "skill load knowledge documentation instructions task type"
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        skill = (params or {}).get("name", "")
        return f"Loading skill{f': {skill}' if skill else ''}"

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
                "query": {
                    "type": "string",
                    "description": "Optional focus keywords — if the body is long, matching lines will be prioritised.",
                },
                "include_bundled_content": {
                    "type": "boolean",
                    "description": (
                        "When true, inline UTF-8 text of bundled references/assets and script sources "
                        "(subject to size caps). When omitted, uses SKILL.md metadata "
                        "`metadata.leagent.bundle_on_load` or server setting skill_load_bundle_default."
                    ),
                },
                "bundled_resources": {
                    "type": "boolean",
                    "description": "If false, skip inlining reference/asset files (scripts still follow bundled_scripts).",
                },
                "bundled_scripts": {
                    "type": "boolean",
                    "description": "If false, skip inlining script sources under scripts/.",
                },
            },
            "required": ["name"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        skill_name = params["name"]
        query = params.get("query") or ""

        try:
            from leagent.config.settings import get_settings
            from leagent.skills.bundle_payload import (
                DEFAULT_MAX_PER_FILE_CHARS,
                build_bundle_payload,
                skill_metadata_bundle_on_load,
            )
            from leagent.skills.bundle_payload_cache import get_cached_bundle, put_cached_bundle
            from leagent.tools.skills import resolve_skills_manager

            manager = await resolve_skills_manager()
            if manager is None:
                return {"found": False, "message": "Skills manager is not available."}

            skill = manager.get_skill(skill_name)
            if not skill:
                lowered = skill_name.lower()
                skill = next(
                    (s for s in manager.all_skills if lowered in s.name.lower()),
                    None,
                )

            if not skill:
                available = [s.name for s in manager.all_skills[:20]]
                return {
                    "found": False,
                    "message": f"Skill '{skill_name}' not found",
                    "available": available,
                }

            body = skill.read_body()
            if not body:
                body = skill.description
            query_filter_applied = False

            if query and len(body) > 2000:
                focus = [line for line in body.splitlines() if query.lower() in line.lower()]
                if focus:
                    body = "\n".join(focus[:200])
                    query_filter_applied = True

            explicit_include = params.get("include_bundled_content")
            br_raw = params.get("bundled_resources")
            bs_raw = params.get("bundled_scripts")
            meta_bundle = skill_metadata_bundle_on_load(skill)
            settings_bundle = get_settings().skill_load_bundle_default

            if explicit_include is False:
                include_inline = False
            elif explicit_include is True:
                include_inline = True
            else:
                include_inline = bool(meta_bundle or settings_bundle)

            if include_inline:
                include_res = True if br_raw is None else bool(br_raw)
                include_scr = True if bs_raw is None else bool(bs_raw)
            else:
                include_res = False
                include_scr = False

            result: dict[str, Any] = {
                "found": True,
                "name": skill.name,
                "description": skill.description,
                "version": skill.version,
                "license": skill.manifest.license,
                "compatibility": skill.manifest.compatibility,
                "allowed_tools": list(skill.manifest.allowed_tools),
                "content": "",
                "include_bundled_content": include_inline,
            }

            if include_inline and (include_res or include_scr):
                if not query_filter_applied:
                    rev = manager.get_skill_content_revision(skill.name)
                    cache_key = (
                        skill.name,
                        rev,
                        include_res,
                        include_scr,
                        int(self.max_result_size_chars),
                        DEFAULT_MAX_PER_FILE_CHARS,
                    )
                    hit = get_cached_bundle(cache_key)
                    if hit is not None:
                        body_out, bundle_extra = hit
                    else:
                        body_out, bundle_extra = build_bundle_payload(
                            skill,
                            skill_body=body,
                            max_total_chars=self.max_result_size_chars,
                            include_resources=include_res,
                            include_scripts=include_scr,
                        )
                        put_cached_bundle(cache_key, (body_out, bundle_extra))
                else:
                    body_out, bundle_extra = build_bundle_payload(
                        skill,
                        skill_body=body,
                        max_total_chars=self.max_result_size_chars,
                        include_resources=include_res,
                        include_scripts=include_scr,
                    )
                result["content"] = body_out
                result.update(bundle_extra)
            else:
                result["content"] = body[: self.max_result_size_chars]

            if skill.manifest.resources:
                result["resources"] = [
                    r.to_dict() for r in skill.manifest.resources[:200]
                ]
                result["resource_tool"] = "read_skill_resource"
            if skill.manifest.scripts:
                result["scripts"] = [s.to_dict() for s in skill.manifest.scripts[:50]]
                result["script_tool"] = "run_skill_script"

            return result

        except Exception as exc:  # noqa: BLE001
            logger.warning("skill_load_failed", skill=skill_name, error=str(exc))
            return {"found": False, "error": str(exc)}
