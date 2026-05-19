"""Skills tools — progressive disclosure of Agent Skills to the model.

Shared configuration and helpers for the skills tool modules live here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from leagent.tools.skills.install import InstallSkillTool
from leagent.tools.skills.loader import SkillTool
from leagent.tools.skills.package_skill import PackageSkillTool
from leagent.tools.skills.resource import SkillResourceTool, _read_resource_payload
from leagent.tools.skills.script import SkillScriptTool

__all__ = [
    "InstallSkillTool",
    "PackageSkillTool",
    "SkillTool",
    "SkillResourceTool",
    "SkillScriptTool",
    "SkillsConfig",
    "_read_resource_payload",
    "resolve_skills_manager",
]


@dataclass(frozen=True)
class SkillsConfig:
    """Centralised limits for all skill tools."""

    max_content_chars: int = 200_000
    max_output_chars: int = 200_000
    default_script_timeout_s: int = 60
    max_script_timeout_s: int = 600
    # Same key as ``Settings.skill_scripts_enabled`` (see env prefix LEAGENT_).
    env_flag: str = "LEAGENT_SKILL_SCRIPTS_ENABLED"


SKILLS_CONFIG = SkillsConfig()


async def resolve_skills_manager() -> Any | None:
    """Lazy-load the skills manager, ensuring skills are populated."""
    from leagent.skills.manager import get_skills_manager

    manager = get_skills_manager()
    if manager is None:
        return None
    if not manager.all_skills:
        await manager.load_all()
    return manager
