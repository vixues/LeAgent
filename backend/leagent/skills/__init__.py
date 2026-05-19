"""Skills package — Agent Skills v1.0 open-spec implementation.

Exports the core dataclasses (`Skill`, `SkillManifest`,
`SkillResource`, `SkillScript`, `SkillHubEntry`), the loader
(`SkillLoader`, `BuiltinSkillLoader`), the manager
(`SkillsManager`, `get_skills_manager`), and the registry protocol
used for hub integrations.
"""

from leagent.skills.base import (
    Skill,
    SkillHubEntry,
    SkillManifest,
    SkillResource,
    SkillResourceKind,
    SkillScript,
    SkillSource,
    SkillStatus,
)
from leagent.skills.discovery import DiscoveryRoot, collect_discovery_roots
from leagent.skills.loader import (
    BuiltinSkillLoader,
    LoaderOptions,
    SkillLoader,
    SkillLoadError,
    SkillValidationError,
)
from leagent.skills.manager import (
    SkillActivationError,
    SkillNotFoundError,
    SkillsManager,
    get_skills_manager,
    reset_skills_manager,
)

__all__ = [
    "BuiltinSkillLoader",
    "DiscoveryRoot",
    "LoaderOptions",
    "Skill",
    "SkillActivationError",
    "SkillHubEntry",
    "SkillLoadError",
    "SkillLoader",
    "SkillManifest",
    "SkillNotFoundError",
    "SkillResource",
    "SkillResourceKind",
    "SkillScript",
    "SkillSource",
    "SkillStatus",
    "SkillValidationError",
    "SkillsManager",
    "collect_discovery_roots",
    "get_skills_manager",
    "reset_skills_manager",
]
