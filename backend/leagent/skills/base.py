"""Core skill data models — Agent Skills v1.0 open-spec shape.

This module defines the runtime representation of an Agent Skill as
specified at https://agentskills.my/specification (v1.0, 2026-04-01):

- A skill is a directory containing a ``SKILL.md`` file with YAML
  frontmatter (required: ``name`` / ``description``; optional: ``license``
  / ``compatibility`` / ``metadata`` / ``allowed-tools``) followed by a
  markdown body that acts as the skill's instructions.
- A skill MAY bundle ``references/`` (documentation loaded into context
  on demand), ``assets/`` (templates / images / data files) and
  ``scripts/`` (executable code invoked via subprocess).

The model deliberately tracks *paths* for the body and bundled files
rather than their contents: the full body is read lazily by
``Skill.read_body`` and bundled resources / scripts are fetched on
demand by dedicated tools (see ``leagent.tools.util``). This keeps
startup cheap and aligns with the progressive-disclosure pattern.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SkillStatus(str, Enum):
    """Runtime status of a skill."""

    INACTIVE = "inactive"
    ACTIVE = "active"
    ERROR = "error"
    LOADING = "loading"


class SkillSource(str, Enum):
    """Origin of a loaded skill."""

    BUILTIN = "builtin"
    LOCAL = "local"
    HUB = "hub"
    CUSTOM = "custom"


class SkillResourceKind(str, Enum):
    """Classification of bundled skill resources.

    ``REFERENCE`` files sit under ``references/`` and are intended to be
    loaded into the LLM context on demand. ``ASSET`` files sit under
    ``assets/`` and are typically templates or binary blobs referenced
    during output generation; the agent may read them but they are not
    assumed to be human-readable prose.
    """

    REFERENCE = "reference"
    ASSET = "asset"


@dataclass
class SkillResource:
    """A bundled reference or asset file.

    Attributes:
        relative_path: Path relative to the skill directory (e.g.
            ``references/api.md``). Always POSIX-style.
        absolute_path: Fully-resolved path on the local filesystem.
        kind: Whether the file is a reference doc or an output asset.
        size: File size in bytes at discovery time.
        extension: Lower-case extension including the leading dot.
    """

    relative_path: str
    absolute_path: Path
    kind: SkillResourceKind
    size: int = 0
    extension: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.relative_path,
            "kind": self.kind.value,
            "size": self.size,
            "extension": self.extension,
        }


@dataclass
class SkillScript:
    """An executable script bundled with a skill.

    Attributes:
        relative_path: Path relative to the skill directory (e.g.
            ``scripts/run.py``).
        absolute_path: Fully-resolved path on the local filesystem.
        interpreter: Best-guess interpreter name derived from the
            file extension (``python``, ``node``, ``bash``, ``pwsh``,
            ``dotnet-script``) or an empty string when unknown.
        size: File size in bytes at discovery time.
        extension: Lower-case extension including the leading dot.
    """

    relative_path: str
    absolute_path: Path
    interpreter: str = ""
    size: int = 0
    extension: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.relative_path,
            "interpreter": self.interpreter,
            "size": self.size,
            "extension": self.extension,
        }


@dataclass
class SkillManifest:
    """Parsed SKILL.md frontmatter + discovered bundled files.

    Only ``name`` and ``description`` come from the open spec as
    required fields. Every other attribute is either an optional spec
    field (``license`` / ``compatibility`` / ``metadata`` /
    ``allowed_tools``) or a LeAgent-specific derivation (e.g.
    ``category`` / ``tags`` extracted from ``metadata`` for filtering).
    """

    name: str
    description: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    resources: list[SkillResource] = field(default_factory=list)
    scripts: list[SkillScript] = field(default_factory=list)

    @property
    def version(self) -> str:
        """Version string — read from ``metadata.version`` when present."""
        value = self.metadata.get("version") if self.metadata else None
        return str(value) if value else "1.0.0"

    @property
    def author(self) -> str:
        """Author — read from ``metadata.author`` / ``metadata.authors``."""
        if not self.metadata:
            return ""
        author = self.metadata.get("author")
        if author:
            return str(author)
        authors = self.metadata.get("authors")
        if isinstance(authors, list) and authors:
            return ", ".join(str(a) for a in authors)
        if authors:
            return str(authors)
        return ""

    @property
    def category(self) -> str:
        """Category — read from ``metadata.category`` (default ``general``)."""
        value = self.metadata.get("category") if self.metadata else None
        return str(value) if value else "general"

    @property
    def tags(self) -> list[str]:
        """Tags — read from ``metadata.tags`` (list of strings)."""
        if not self.metadata:
            return []
        raw = self.metadata.get("tags") or []
        if isinstance(raw, str):
            return [t.strip() for t in raw.split(",") if t.strip()]
        return [str(t) for t in raw if t]

    @property
    def display_name(self) -> str:
        """Human-readable name — ``metadata.display_name`` or derived."""
        if self.metadata and self.metadata.get("display_name"):
            return str(self.metadata["display_name"])
        return self.name.replace("-", " ").replace("_", " ").title()

    @property
    def has_resources(self) -> bool:
        return bool(self.resources)

    @property
    def has_scripts(self) -> bool:
        return bool(self.scripts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "license": self.license,
            "compatibility": self.compatibility,
            "metadata": dict(self.metadata),
            "allowed_tools": list(self.allowed_tools),
            "resources": [r.to_dict() for r in self.resources],
            "scripts": [s.to_dict() for s in self.scripts],
            # convenience fields
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "tags": self.tags,
            "display_name": self.display_name,
        }


@dataclass
class Skill:
    """A loaded skill with runtime state.

    The manifest holds the parsed frontmatter and discovered file
    paths; the full SKILL.md body is read on demand via
    ``read_body`` to preserve progressive disclosure.
    """

    manifest: SkillManifest
    source: SkillSource = SkillSource.LOCAL
    path: Path | None = None
    status: SkillStatus = SkillStatus.INACTIVE
    config: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    _cached_body: str | None = field(default=None, repr=False, compare=False)
    _cached_body_mtime: float = field(default=0.0, repr=False, compare=False)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def display_name(self) -> str:
        return self.manifest.display_name

    @property
    def description(self) -> str:
        return self.manifest.description

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def is_active(self) -> bool:
        return self.status == SkillStatus.ACTIVE

    @property
    def enabled(self) -> bool:
        """Convenience flag mirroring ``is_active`` for prompt advertising."""
        return self.status != SkillStatus.ERROR

    @property
    def skill_md_path(self) -> Path | None:
        """Absolute path to the skill's ``SKILL.md`` file."""
        return (self.path / "SKILL.md") if self.path else None

    def get_resource(self, relative_path: str) -> SkillResource | None:
        rel = relative_path.replace("\\", "/").lstrip("./")
        for r in self.manifest.resources:
            if r.relative_path == rel:
                return r
        return None

    def get_script(self, relative_path: str) -> SkillScript | None:
        rel = relative_path.replace("\\", "/").lstrip("./")
        for s in self.manifest.scripts:
            if s.relative_path == rel:
                return s
        return None

    def read_body(self, refresh: bool = False) -> str:
        """Read the SKILL.md body lazily.

        The body is cached in memory and invalidated when the file's
        mtime changes. Returns an empty string if the skill has no
        backing file on disk (e.g. programmatically-constructed skills
        in tests).
        """
        md_path = self.skill_md_path
        if not md_path or not md_path.exists():
            return self._cached_body or ""

        try:
            mtime = md_path.stat().st_mtime
        except OSError:
            mtime = time.time()

        if not refresh and self._cached_body is not None and mtime == self._cached_body_mtime:
            return self._cached_body

        try:
            content = md_path.read_text(encoding="utf-8")
        except OSError:
            return self._cached_body or ""

        # Strip frontmatter: drop everything up to and including the
        # second ``---`` delimiter so callers get pure instructions.
        body = _strip_frontmatter(content)
        self._cached_body = body
        self._cached_body_mtime = mtime
        return body

    def invalidate_body_cache(self) -> None:
        self._cached_body = None
        self._cached_body_mtime = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest.to_dict(),
            "source": self.source.value,
            "path": str(self.path) if self.path else None,
            "status": self.status.value,
            "config": self.config,
            "error": self.error,
        }

    @classmethod
    def from_manifest(
        cls,
        manifest: SkillManifest,
        source: SkillSource = SkillSource.LOCAL,
        path: Path | None = None,
    ) -> Skill:
        """Create a skill instance anchored to the given source/path."""
        return cls(manifest=manifest, source=source, path=path)


@dataclass
class SkillHubEntry:
    """Entry returned by a skills registry.

    The registry contract is deliberately narrow: a name, a description,
    an optional download URL, plus soft metadata fields used for
    display. See :mod:`leagent.skills.registry` for the protocol.
    """

    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    category: str = "general"
    downloads: int = 0
    rating: float = 0.0
    tags: list[str] = field(default_factory=list)
    url: str = ""
    sha256: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillHubEntry:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            category=data.get("category", "general"),
            downloads=int(data.get("downloads", 0) or 0),
            rating=float(data.get("rating", 0.0) or 0.0),
            tags=list(data.get("tags", []) or []),
            url=data.get("url") or data.get("download_url") or "",
            sha256=data.get("sha256") or data.get("checksum"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "category": self.category,
            "downloads": self.downloads,
            "rating": self.rating,
            "tags": self.tags,
            "url": self.url,
            "sha256": self.sha256,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_frontmatter(content: str) -> str:
    """Return the markdown body after the YAML frontmatter block.

    Mirrors the lightweight parser used by ``markdown_loader`` but keeps
    this module free of an import cycle.
    """
    if not content.startswith("---"):
        return content.strip()
    # Split on "\n---" that closes the frontmatter block.
    rest = content[3:]
    close_idx = rest.find("\n---")
    if close_idx == -1:
        return content.strip()
    body = rest[close_idx + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    elif body.startswith("\r\n"):
        body = body[2:]
    return body.strip()
