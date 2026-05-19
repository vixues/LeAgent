"""Cross-agent skill directory discovery.

The open spec (agentskills.my v1.0) encourages interoperability between
agents: skills written for one agent should work in any other that
implements the spec. This module enumerates the well-known discovery
roots from other popular agents so a user who already installed a skill
for Claude Code or Cursor gets it for free inside LeAgent too.

Precedence (first match wins when two roots contain a skill with the
same ``name``):

1. Project-scoped LeAgent roots (``.leagent/skills/``).
2. Project-scoped interop roots (``.claude/skills/`` etc).
3. User-scoped LeAgent root (``$LEAGENT_HOME/skills/``).
4. User-scoped interop roots (``~/.claude/skills/`` etc).
5. Bundled builtin skills.

Each root is reported with a :class:`DiscoveryRoot` so the manager can
tag loaded skills with their origin for debugging without silently
overwriting one user's customisation with another vendor's default.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from leagent.skills.base import SkillSource

#: Well-known project-relative interop directories (in precedence order).
PROJECT_INTEROP_SUBDIRS: tuple[str, ...] = (
    ".leagent/skills",
    ".openclaw/skills",
    ".openclaw",
    ".claude/skills",
    ".cursor/skills",
    ".codex/skills",
    ".gemini/skills",
    ".opencode/skills",
    ".kiro/skills",
    ".windsurf/skills",
    ".github/skills",
)

#: Well-known user-home-relative interop directories.
USER_INTEROP_SUBDIRS: tuple[str, ...] = (
    ".openclaw/skills",
    ".openclaw",
    ".claude/skills",
    ".cursor/skills",
    ".codex/skills",
    ".gemini/skills",
    ".config/opencode/skills",
    ".kiro/skills",
    ".codeium/windsurf/skills",
    ".copilot/skills",
)


@dataclass(frozen=True)
class DiscoveryRoot:
    """A filesystem directory that may contain skill subdirectories."""

    path: Path
    scope: str  # "project" | "user" | "builtin"
    origin: str  # e.g. "leagent", "claude", "cursor"
    source: SkillSource

    @property
    def priority(self) -> int:
        """Lower integer wins when two roots define the same skill."""
        if self.scope == "project":
            return 0 if self.origin == "leagent" else 1
        if self.scope == "user":
            return 2 if self.origin == "leagent" else 3
        return 4  # builtin


def collect_discovery_roots(
    *,
    leagent_home: Path | None = None,
    project_dir: Path | None = None,
    builtin_dir: Path | None = None,
    include_user_interop: bool = True,
) -> list[DiscoveryRoot]:
    """Return all roots to scan, in precedence order.

    Arguments are all optional so callers can opt out of individual
    scopes (e.g. tests that only care about a temp directory).
    """
    roots: list[DiscoveryRoot] = []

    # 1. Project scope
    if project_dir:
        seen: set[Path] = set()
        for sub in PROJECT_INTEROP_SUBDIRS:
            candidate = (project_dir / sub).resolve()
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists() and candidate.is_dir():
                origin = _origin_from_subdir(sub)
                roots.append(
                    DiscoveryRoot(
                        path=candidate,
                        scope="project",
                        origin=origin,
                        source=SkillSource.LOCAL,
                    )
                )

    # 2. User scope (LeAgent's own home)
    if leagent_home:
        wa_dir = (leagent_home / "skills").resolve()
        if wa_dir.exists() and wa_dir.is_dir():
            roots.append(
                DiscoveryRoot(
                    path=wa_dir,
                    scope="user",
                    origin="leagent",
                    source=SkillSource.LOCAL,
                )
            )

    # 3. User scope (other agents)
    try:
        home = Path.home()
    except (RuntimeError, OSError):
        home = None
    if include_user_interop and home is not None:
        seen_home: set[Path] = set()
        for sub in USER_INTEROP_SUBDIRS:
            candidate = (home / sub).resolve()
            if candidate in seen_home:
                continue
            seen_home.add(candidate)
            if candidate.exists() and candidate.is_dir():
                roots.append(
                    DiscoveryRoot(
                        path=candidate,
                        scope="user",
                        origin=_origin_from_subdir(sub),
                        source=SkillSource.LOCAL,
                    )
                )

    # 4. Builtin
    if builtin_dir and builtin_dir.exists() and builtin_dir.is_dir():
        roots.append(
            DiscoveryRoot(
                path=builtin_dir,
                scope="builtin",
                origin="leagent",
                source=SkillSource.BUILTIN,
            )
        )

    return roots


def _origin_from_subdir(sub: str) -> str:
    """Heuristic tag derived from a well-known directory pattern."""
    lower = sub.lower()
    for marker in (
        "leagent",
        "openclaw",
        "claude",
        "cursor",
        "codex",
        "gemini",
        "opencode",
        "kiro",
        "windsurf",
        "copilot",
        "github",
    ):
        if marker in lower:
            return marker
    return "unknown"
