"""package_skill — build a v1.0–compliant .zip of a skill directory."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from leagent.tools.base import BaseTool, ToolCategory, ToolContext


class PackageSkillTool(BaseTool):
    """Zip a validated skill folder for import into Cursor / LeAgent / ``install_skill``."""

    name = "package_skill"
    description = (
        "Build a standards-compliant .zip archive of an Agent Skill directory that contains "
        "SKILL.md. Validates against v1.0 rules before writing. Output is written under the "
        "sandbox (default: session temp). Use after authoring a skill folder in the workspace."
    )
    category = ToolCategory.SKILLS
    is_read_only = False
    is_destructive = True
    is_concurrency_safe = True
    aliases = ["export_skill_bundle", "skill_zip"]
    search_hint = "package skill zip export bundle SKILL.md archive"
    interrupt_behavior = "block"
    max_result_size_chars = 12_000
    path_params = ("skill_directory",)
    output_path_params = ("output_path",)

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        p = params or {}
        d = p.get("skill_directory", "")
        return f"Packaging skill: {d}" if d else "Packaging skill"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "skill_directory": {
                    "type": "string",
                    "description": (
                        "Path to the skill root directory (contains SKILL.md). "
                        "Must be under the project or uploads sandbox."
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Optional output .zip path under the sandbox. "
                        "If omitted, uses <temp>/<folder-name>.zip."
                    ),
                },
            },
            "required": ["skill_directory"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        from leagent.skills.packaging import SkillPackageError, build_skill_zip_async

        root = Path(params["skill_directory"])
        if not root.is_dir():
            return {"ok": False, "message": f"Not a directory: {root}"}

        out_raw = (params.get("output_path") or "").strip()
        if out_raw:
            out = Path(out_raw)
            if out.suffix.lower() != ".zip":
                out = out.with_suffix(".zip")
        else:
            base = context.temp_dir or os.environ.get("TMPDIR", os.environ.get("TEMP", "/tmp"))
            out = Path(base) / f"{root.name}.zip"

        try:
            raw = await build_skill_zip_async(root)
        except SkillPackageError as exc:
            return {"ok": False, "message": str(exc)}

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        return {
            "ok": True,
            "output_path": str(out.resolve()),
            "size_bytes": len(raw),
            "sha256": digest,
            "message": (
                f"Wrote skill archive ({len(raw)} bytes). "
                "User can import via install_skill (url after upload) or extract to .cursor/skills/."
            ),
        }
