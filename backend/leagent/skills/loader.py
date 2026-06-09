"""SKILL.md loader — discovers, validates and hot-reloads skills.

Implements the Agent Skills v1.0 open specification:

- A skill lives in its own directory.
- That directory MUST contain a ``SKILL.md`` file whose YAML
  frontmatter supplies the required ``name`` and ``description`` fields
  along with optional ``license``, ``compatibility``, ``metadata`` and
  ``allowed-tools``.
- The directory MAY bundle ``references/`` and ``assets/`` (content
  files), optional **root-level** reference files with allowed
  extensions (same discovery rules; excludes ``SKILL.md``), and
  ``scripts/`` (executables).

Validation follows the spec:

- ``name`` must match ``^[a-z0-9]+(-[a-z0-9]+)*$``, be 1-64 chars long,
  avoid reserved words ``anthropic`` / ``claude`` and exactly equal its
  parent directory name.
- ``description`` must be 1-1024 characters and contain no XML-style
  tags.
- ``compatibility`` must be ≤500 characters.

YAML manifest support has been removed in the v1.0 migration — only
``SKILL.md`` is accepted.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import structlog

from leagent.skills.base import (
    Skill,
    SkillManifest,
    SkillResource,
    SkillResourceKind,
    SkillScript,
    SkillSource,
    SkillStatus,
)
from leagent.skills.markdown_loader import parse_skill_markdown

logger = structlog.get_logger(__name__)

SKILL_MD_FILENAME = "SKILL.md"

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_RESERVED_NAMES = frozenset({"anthropic", "claude"})
_XML_TAG_RE = re.compile(r"<[^>]+>")

_DEFAULT_RESOURCE_EXTENSIONS = frozenset({".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt"})
_DEFAULT_SCRIPT_EXTENSIONS = frozenset({".py", ".js", ".sh", ".ps1", ".cs", ".csx"})

_INTERPRETER_BY_EXT = {
    ".py": "python",
    ".js": "node",
    ".sh": "bash",
    ".ps1": "pwsh",
    ".cs": "dotnet-script",
    ".csx": "dotnet-script",
}


class SkillLoadError(Exception):
    """Raised when a skill directory cannot be loaded."""

    def __init__(self, skill_path: str, reason: str) -> None:
        self.skill_path = skill_path
        self.reason = reason
        super().__init__(f"Failed to load skill from '{skill_path}': {reason}")


class SkillValidationError(Exception):
    """Raised when a skill manifest fails validation."""

    def __init__(self, skill_name: str, errors: list[str]) -> None:
        self.skill_name = skill_name
        self.errors = errors
        super().__init__(f"Skill '{skill_name}' validation failed: {'; '.join(errors)}")


@dataclass
class LoaderOptions:
    """Configurable extension allow-lists for bundled files.

    Callers can shrink or extend these sets to match their security
    posture — by default we follow Microsoft's Agent Framework defaults
    documented in the v1.0 spec.
    """

    resource_extensions: frozenset[str] = field(default_factory=lambda: _DEFAULT_RESOURCE_EXTENSIONS)
    script_extensions: frozenset[str] = field(default_factory=lambda: _DEFAULT_SCRIPT_EXTENSIONS)
    max_body_size: int = 256 * 1024  # 256 KiB
    max_resource_size: int = 2 * 1024 * 1024  # 2 MiB


class SkillLoader:
    """Load, validate and hot-reload skills from a directory.

    Each subdirectory that contains a ``SKILL.md`` becomes a
    :class:`~leagent.skills.base.Skill`. Hot-reload is opt-in: start
    it with :meth:`start_watching` and stop it with
    :meth:`stop_watching`.
    """

    def __init__(
        self,
        skills_dir: str | Path,
        source: SkillSource = SkillSource.LOCAL,
        watch_interval: float = 2.0,
        options: LoaderOptions | None = None,
    ) -> None:
        self._skills_dir = Path(skills_dir)
        self._source = source
        self._watch_interval = watch_interval
        self._options = options or LoaderOptions()

        self._skills: dict[str, Skill] = {}
        self._dir_hashes: dict[str, str] = {}
        self._watch_task: asyncio.Task[None] | None = None
        self._watching = False

        self._on_load_callbacks: list[Callable[[Skill], None]] = []
        self._on_unload_callbacks: list[Callable[[str], None]] = []
        self._on_error_callbacks: list[Callable[[str, Exception], None]] = []

    # ------------------------------------------------------------------
    # Public properties / callbacks
    # ------------------------------------------------------------------
    @property
    def skills_dir(self) -> Path:
        return self._skills_dir

    @property
    def options(self) -> LoaderOptions:
        return self._options

    @property
    def loaded_skills(self) -> dict[str, Skill]:
        return dict(self._skills)

    @property
    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def on_load(self, callback: Callable[[Skill], None]) -> None:
        self._on_load_callbacks.append(callback)

    def on_unload(self, callback: Callable[[str], None]) -> None:
        self._on_unload_callbacks.append(callback)

    def on_error(self, callback: Callable[[str, Exception], None]) -> None:
        self._on_error_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    async def load_all(self) -> dict[str, Skill]:
        if not self._skills_dir.exists() or not self._skills_dir.is_dir():
            logger.debug("skills_dir_missing", path=str(self._skills_dir))
            return {}

        loaded = 0
        errors = 0
        for subdir in sorted(self._skills_dir.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith((".", "_")):
                continue
            if not (subdir / SKILL_MD_FILENAME).exists():
                continue
            try:
                skill = await self.load_skill(subdir)
                if skill:
                    loaded += 1
            except (SkillLoadError, SkillValidationError) as exc:
                errors += 1
                logger.warning("skill_load_failed", path=str(subdir), error=str(exc))
            except Exception as exc:  # noqa: BLE001
                errors += 1
                logger.warning("skill_load_failed_unexpected", path=str(subdir), error=str(exc))

        logger.info(
            "skills_loaded",
            total=loaded,
            errors=errors,
            directory=str(self._skills_dir),
        )
        return dict(self._skills)

    async def load_skill(self, skill_path: str | Path) -> Skill | None:
        path = Path(skill_path)
        if not path.exists():
            raise SkillLoadError(str(path), "Directory does not exist")
        if not path.is_dir():
            raise SkillLoadError(str(path), "Path is not a directory")

        md_path = path / SKILL_MD_FILENAME
        if not md_path.exists():
            raise SkillLoadError(str(path), f"Missing {SKILL_MD_FILENAME}")

        try:
            content = md_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SkillLoadError(str(path), f"Failed to read SKILL.md: {exc}") from exc

        frontmatter, _body = parse_skill_markdown(content)
        manifest = self._build_manifest(frontmatter, path)

        errors = self._validate(manifest, path)
        if errors:
            raise SkillValidationError(manifest.name or path.name, errors)

        existing = self._skills.get(manifest.name)
        skill = Skill.from_manifest(manifest, source=self._source, path=path)
        skill.status = SkillStatus.INACTIVE

        if existing is not None:
            # Preserve runtime state (active status + user config).
            skill.status = existing.status
            skill.config = dict(existing.config)
            # Force a fresh body read next time.
            skill.invalidate_body_cache()

        self._dir_hashes[manifest.name] = self._compute_dir_hash(path)
        self._skills[manifest.name] = skill

        for cb in self._on_load_callbacks:
            try:
                cb(skill)
            except Exception:  # noqa: BLE001
                logger.debug("on_load_callback_failed", skill=manifest.name, exc_info=True)

        logger.info(
            "skill_loaded",
            name=manifest.name,
            resources=len(manifest.resources),
            scripts=len(manifest.scripts),
            source=self._source.value,
        )
        return skill

    async def unload_skill(self, name: str) -> bool:
        if name not in self._skills:
            return False
        del self._skills[name]
        self._dir_hashes.pop(name, None)
        for cb in self._on_unload_callbacks:
            try:
                cb(name)
            except Exception:  # noqa: BLE001
                logger.debug("on_unload_callback_failed", skill=name, exc_info=True)
        logger.info("skill_unloaded", name=name)
        return True

    async def reload_skill(self, name: str) -> Skill | None:
        skill = self._skills.get(name)
        if not skill or not skill.path:
            return None
        return await self.load_skill(skill.path)

    def validate_skill_content(self, skill_path: str | Path, content: str) -> None:
        """Check *content* as SKILL.md for *skill_path* without writing.

        Raises :class:`SkillValidationError` when validation fails.
        """
        path = Path(skill_path)
        if not path.exists() or not path.is_dir():
            raise SkillLoadError(str(path), "Path is not a valid skill directory")

        frontmatter, _body = parse_skill_markdown(content)
        manifest = self._build_manifest(frontmatter, path)
        errors = self._validate(manifest, path)
        if errors:
            raise SkillValidationError(manifest.name or path.name, errors)

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def get_content_revision(self, skill_name: str) -> str:
        """Directory fingerprint for cache invalidation (updated on each load_skill)."""
        return self._dir_hashes.get(skill_name, "")

    # ------------------------------------------------------------------
    # Manifest construction & validation
    # ------------------------------------------------------------------
    def _build_manifest(self, frontmatter: dict[str, Any], skill_path: Path) -> SkillManifest:
        name = str(frontmatter.get("name") or skill_path.name).strip()
        description = str(frontmatter.get("description") or "").strip()

        license_raw = frontmatter.get("license")
        license_str = str(license_raw).strip() if license_raw else None

        compat_raw = frontmatter.get("compatibility")
        compatibility = str(compat_raw).strip() if compat_raw else None

        metadata_raw = frontmatter.get("metadata") or {}
        if not isinstance(metadata_raw, dict):
            metadata: dict[str, Any] = {"_raw": metadata_raw}
        else:
            metadata = dict(metadata_raw)

        # Promote a few legacy top-level fields into metadata so older
        # LeAgent SKILL.md files keep working without reformatting.
        for legacy_key in ("version", "author", "authors", "category", "tags", "display_name"):
            if legacy_key in frontmatter and legacy_key not in metadata:
                metadata[legacy_key] = frontmatter[legacy_key]

        allowed_tools = _normalise_allowed_tools(frontmatter.get("allowed_tools"))

        resources = _discover_resources(skill_path, self._options)
        scripts = _discover_scripts(skill_path, self._options)

        return SkillManifest(
            name=name,
            description=description,
            license=license_str,
            compatibility=compatibility,
            metadata=metadata,
            allowed_tools=allowed_tools,
            resources=resources,
            scripts=scripts,
        )

    def _validate(self, manifest: SkillManifest, skill_path: Path) -> list[str]:
        errors: list[str] = []
        name = manifest.name

        if not name:
            errors.append("`name` is required")
        else:
            if len(name) > 64:
                errors.append("`name` must be at most 64 characters")
            if not _NAME_RE.match(name):
                errors.append(
                    "`name` must match ^[a-z0-9]+(-[a-z0-9]+)*$ "
                    "(lowercase letters, digits and single hyphens)"
                )
            if name.lower() in _RESERVED_NAMES:
                errors.append(f"`name` cannot be a reserved word: {name}")
            if skill_path.name != name:
                errors.append(
                    f"`name` ({name!r}) must match parent directory ({skill_path.name!r})"
                )

        description = manifest.description
        if not description:
            errors.append("`description` is required")
        else:
            if len(description) > 1024:
                errors.append("`description` must be at most 1024 characters")
            if _XML_TAG_RE.search(description):
                errors.append("`description` must not contain XML-style tags")

        if manifest.compatibility and len(manifest.compatibility) > 500:
            errors.append("`compatibility` must be at most 500 characters")

        return errors

    # ------------------------------------------------------------------
    # Hot reload
    # ------------------------------------------------------------------
    def _compute_dir_hash(self, skill_path: Path) -> str:
        """Hash SKILL.md + bundled file mtimes to detect any change."""
        hasher = hashlib.sha256()
        candidates: list[Path] = [skill_path / SKILL_MD_FILENAME]
        for sub in ("references", "assets", "scripts"):
            sub_dir = skill_path / sub
            if sub_dir.is_dir():
                for entry in sorted(sub_dir.rglob("*")):
                    if entry.is_file():
                        candidates.append(entry)

        candidates.extend(_root_level_resource_paths(skill_path, self._options))

        for entry in candidates:
            try:
                stat = entry.stat()
            except OSError:
                continue
            hasher.update(str(entry.relative_to(skill_path)).encode("utf-8"))
            hasher.update(str(int(stat.st_mtime_ns)).encode("utf-8"))
            hasher.update(str(stat.st_size).encode("utf-8"))
            hasher.update(b"\0")
        return hasher.hexdigest()

    def start_watching(self) -> None:
        if self._watching:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("skill_watcher_no_loop", directory=str(self._skills_dir))
            return
        self._watching = True
        self._watch_task = asyncio.create_task(self._watch_loop())
        logger.info("skill_watcher_started", directory=str(self._skills_dir))

    def stop_watching(self) -> None:
        self._watching = False
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None
        logger.info("skill_watcher_stopped")

    async def _watch_loop(self) -> None:
        while self._watching:
            try:
                await asyncio.sleep(self._watch_interval)
                await self._check_for_changes()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                logger.error("skill_watcher_error", error=str(exc))

    async def _check_for_changes(self) -> None:
        # 1. Detect removals / modifications of already-loaded skills.
        for name, skill in list(self._skills.items()):
            if not skill.path:
                continue
            if not (skill.path / SKILL_MD_FILENAME).exists():
                logger.info("skill_removed", name=name)
                await self.unload_skill(name)
                continue
            current_hash = self._compute_dir_hash(skill.path)
            if current_hash != self._dir_hashes.get(name):
                try:
                    await self.reload_skill(name)
                    logger.info("skill_reloaded", name=name)
                except (SkillLoadError, SkillValidationError) as exc:
                    skill.status = SkillStatus.ERROR
                    skill.error = str(exc)
                    for cb in self._on_error_callbacks:
                        try:
                            cb(name, exc)
                        except Exception:  # noqa: BLE001
                            pass

        # 2. Discover new skill directories.
        if not self._skills_dir.exists():
            return
        known_paths = {s.path for s in self._skills.values() if s.path}
        for subdir in sorted(self._skills_dir.iterdir()):
            if not subdir.is_dir() or subdir.name.startswith((".", "_")):
                continue
            if subdir in known_paths:
                continue
            if not (subdir / SKILL_MD_FILENAME).exists():
                continue
            try:
                await self.load_skill(subdir)
            except (SkillLoadError, SkillValidationError) as exc:
                logger.warning("skill_discovery_failed", path=str(subdir), error=str(exc))


class BuiltinSkillLoader(SkillLoader):
    """Loader rooted at the bundled ``skills/builtin/`` directory."""

    def __init__(self, watch_interval: float = 5.0) -> None:
        builtin_dir = Path(__file__).parent / "builtin"
        super().__init__(
            skills_dir=builtin_dir,
            source=SkillSource.BUILTIN,
            watch_interval=watch_interval,
        )


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _normalise_allowed_tools(value: Any) -> list[str]:
    """Return the ``allowed-tools`` list in a stable form.

    The open spec defines this field as a space-delimited string
    (``Bash(git:*) Read Write``). Historically LeAgent wrote it as a
    YAML list; we accept both and normalise to a Python list so
    consumers never need to branch.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [token for token in value.split() if token]
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            if not item:
                continue
            if isinstance(item, str):
                token = item.strip()
            else:
                token = str(item).strip()
            if token:
                out.append(token)
        return out
    return [str(value)]


def _root_level_resource_paths(skill_path: Path, options: LoaderOptions) -> list[Path]:
    """Files directly under the skill dir that count as bundled references.

    Third-party packs often place docs next to ``SKILL.md`` (e.g. ``pptxgenjs.md``).
    Non-recursive — does not walk ``scripts/`` or other subdirectories.
    """
    paths: list[Path] = []
    skill_md = (skill_path / SKILL_MD_FILENAME).resolve()
    try:
        for entry in sorted(skill_path.iterdir()):
            if not entry.is_file():
                continue
            try:
                if entry.resolve() == skill_md:
                    continue
            except OSError:
                pass
            if entry.name.upper() == SKILL_MD_FILENAME.upper():
                continue
            ext = entry.suffix.lower()
            if options.resource_extensions and ext not in options.resource_extensions:
                continue
            paths.append(entry)
    except OSError:
        pass
    return paths


def _discover_resources(skill_path: Path, options: LoaderOptions) -> list[SkillResource]:
    resources: list[SkillResource] = []
    for sub, kind in (
        ("references", SkillResourceKind.REFERENCE),
        ("assets", SkillResourceKind.ASSET),
    ):
        root = skill_path / sub
        if not root.is_dir():
            continue
        for entry in sorted(root.rglob("*")):
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if options.resource_extensions and ext not in options.resource_extensions:
                continue
            try:
                size = entry.stat().st_size
            except OSError:
                size = 0
            rel = entry.relative_to(skill_path).as_posix()
            resources.append(
                SkillResource(
                    relative_path=rel,
                    absolute_path=entry.resolve(),
                    kind=kind,
                    size=size,
                    extension=ext,
                )
            )

    for entry in _root_level_resource_paths(skill_path, options):
        ext = entry.suffix.lower()
        try:
            size = entry.stat().st_size
        except OSError:
            size = 0
        resources.append(
            SkillResource(
                relative_path=entry.name,
                absolute_path=entry.resolve(),
                kind=SkillResourceKind.REFERENCE,
                size=size,
                extension=ext,
            )
        )

    return resources


def _discover_scripts(skill_path: Path, options: LoaderOptions) -> list[SkillScript]:
    scripts_dir = skill_path / "scripts"
    if not scripts_dir.is_dir():
        return []
    scripts: list[SkillScript] = []
    for entry in sorted(scripts_dir.rglob("*")):
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if options.script_extensions and ext not in options.script_extensions:
            continue
        try:
            stat = entry.stat()
            size = stat.st_size
        except OSError:
            size = 0
        rel = entry.relative_to(skill_path).as_posix()
        scripts.append(
            SkillScript(
                relative_path=rel,
                absolute_path=entry.resolve(),
                interpreter=_INTERPRETER_BY_EXT.get(ext, ""),
                size=size,
                extension=ext,
            )
        )
    return scripts


def is_path_inside(parent: Path, child: Path) -> bool:
    """Return True if ``child`` resolves to a location inside ``parent``.

    Delegates to :func:`leagent.file.primitives.is_path_inside`.
    """
    from leagent.file.primitives import is_path_inside as _canonical

    try:
        return _canonical(child.resolve(), (parent.resolve(),))
    except OSError:
        return False
