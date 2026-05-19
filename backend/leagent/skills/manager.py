"""SkillsManager — orchestrates discovery, activation and registry access.

The manager is the single entry point used by the rest of the app
(agent runtime, REST API, CLI). It:

- Discovers skills across all scopes via
  :func:`leagent.skills.discovery.collect_discovery_roots` and a
  single SKILL.md loader per root (v1.0 spec; YAML manifests removed).
- Tracks activation state and exposes progressive-disclosure helpers
  (``any_skill_has_resources``, ``any_skill_has_scripts``) that the
  tool layer uses to decide when to advertise Level 3 / Level 4 tools.
- Delegates registry operations (``search_hub`` / ``install_from_hub``)
  to a pluggable :class:`SkillRegistry` instance.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import structlog

from leagent.skills.base import (
    Skill,
    SkillHubEntry,
    SkillSource,
    SkillStatus,
)
from leagent.skills.github_monorepo_catalog import GitHubCatalogOverride
from leagent.skills.discovery import DiscoveryRoot, collect_discovery_roots
from leagent.skills.loader import SkillLoader

logger = structlog.get_logger(__name__)

_HUB_MERGE_CAP = 2000


class SkillNotFoundError(Exception):
    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        super().__init__(f"Skill not found: {skill_name}")


class SkillActivationError(Exception):
    def __init__(self, skill_name: str, reason: str) -> None:
        self.skill_name = skill_name
        self.reason = reason
        super().__init__(f"Failed to activate skill '{skill_name}': {reason}")


class SkillFileNotEditableError(Exception):
    def __init__(self, skill_name: str) -> None:
        self.skill_name = skill_name
        super().__init__(f"Skill '{skill_name}' is not editable")


class SkillFileUpdateError(Exception):
    def __init__(self, skill_name: str, reason: str) -> None:
        self.skill_name = skill_name
        self.reason = reason
        super().__init__(f"Failed to update skill file '{skill_name}': {reason}")


class SkillsManager:
    """Single point of truth for the installed skill set."""

    def __init__(
        self,
        skills_dir: str | Path | None = None,
        *,
        registry: Any | None = None,
        load_builtin: bool = True,
        enable_hot_reload: bool = True,
        include_interop_roots: bool = True,
        project_root: Path | None = None,
    ) -> None:
        self._skills_dir = Path(skills_dir) if skills_dir else None
        self._registry = registry  # Lazy: created on first use.
        self._load_builtin = load_builtin
        self._enable_hot_reload = enable_hot_reload
        self._include_interop_roots = include_interop_roots
        self._project_root = project_root

        self._skills: dict[str, Skill] = {}
        self._loaders: list[SkillLoader] = []
        self._skill_origin: dict[str, DiscoveryRoot] = {}
        self._skill_content_revision: dict[str, str] = {}

        self._on_activate_callbacks: list[Callable[[Skill], None]] = []
        self._on_deactivate_callbacks: list[Callable[[str], None]] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def all_skills(self) -> list[Skill]:
        return list(self._skills.values())

    @property
    def active_skills(self) -> list[Skill]:
        return [s for s in self._skills.values() if s.is_active]

    @property
    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    @property
    def registry(self) -> Any:
        """Return the registry, instantiating a default on first use."""
        if self._registry is None:
            from leagent.skills.registry import HTTPSkillRegistry, get_default_registry_url

            url = get_default_registry_url()
            if url:
                self._registry = HTTPSkillRegistry(url)
            else:
                from leagent.skills.registry import DisabledRegistry

                self._registry = DisabledRegistry()
        return self._registry

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------
    def on_activate(self, callback: Callable[[Skill], None]) -> None:
        self._on_activate_callbacks.append(callback)

    def on_deactivate(self, callback: Callable[[str], None]) -> None:
        self._on_deactivate_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    async def load_all(self) -> int:
        """Scan every configured root and load discovered SKILL.md skills."""
        roots = self._collect_roots()
        # Sort by precedence so lower numeric priority wins when two
        # roots declare the same skill name.
        roots.sort(key=lambda r: r.priority)

        for root in roots:
            loader = SkillLoader(root.path, source=root.source)
            try:
                await loader.load_all()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "skills_root_load_failed",
                    path=str(root.path),
                    scope=root.scope,
                    origin=root.origin,
                    error=str(exc),
                )
                continue

            for name, skill in loader.loaded_skills.items():
                rev = loader.get_content_revision(name)
                self._register_skill(name, skill, root, content_revision=rev)

            self._loaders.append(loader)
            if self._enable_hot_reload and root.scope != "builtin":
                loader.on_load(self._handle_skill_reload)
                loader.on_unload(self._handle_skill_unload)
                loader.start_watching()

        logger.info(
            "skills_loaded_total",
            total=len(self._skills),
            roots=len(roots),
        )
        return len(self._skills)

    def _collect_roots(self) -> list[DiscoveryRoot]:
        from leagent.skills.bundled import BUILTIN_DIR

        project_root = self._project_root
        if project_root is None and self._include_interop_roots:
            try:
                from leagent.cli.config_cmd import find_project_dir

                project_dir = find_project_dir()
                if project_dir is not None:
                    project_root = project_dir.parent
            except Exception:  # noqa: BLE001
                project_root = None

        roots: list[DiscoveryRoot] = []

        # The explicit ``skills_dir`` is treated as a direct container
        # of skill subdirectories (this is the conventional layout for
        # ``~/.leagent/skills`` as well as test fixtures).
        if self._skills_dir and self._skills_dir.exists() and self._skills_dir.is_dir():
            roots.append(
                DiscoveryRoot(
                    path=self._skills_dir.resolve(),
                    scope="user",
                    origin="leagent",
                    source=SkillSource.LOCAL,
                )
            )

        # Interop + builtin discovery on top.
        discovered = collect_discovery_roots(
            leagent_home=None,  # explicit skills_dir already covers it
            project_dir=project_root if self._include_interop_roots else None,
            builtin_dir=BUILTIN_DIR if self._load_builtin else None,
            include_user_interop=self._include_interop_roots,
        )

        # De-duplicate by resolved path (explicit wins).
        known = {r.path for r in roots}
        for root in discovered:
            if root.path in known:
                continue
            roots.append(root)
            known.add(root.path)
        return roots

    def _register_skill(
        self,
        name: str,
        skill: Skill,
        root: DiscoveryRoot,
        *,
        content_revision: str = "",
    ) -> None:
        """Register a skill, honouring root precedence for conflicts."""
        existing_root = self._skill_origin.get(name)
        if existing_root is None or root.priority < existing_root.priority:
            self._skills[name] = skill
            self._skill_origin[name] = root
            self._skill_content_revision[name] = content_revision

    def _handle_skill_reload(self, skill: Skill) -> None:
        was_active = self._skills.get(skill.name).is_active if skill.name in self._skills else False
        self._skills[skill.name] = skill
        rev = ""
        for loader in self._loaders:
            if skill.name in loader.loaded_skills:
                rev = loader.get_content_revision(skill.name)
                break
        self._skill_content_revision[skill.name] = rev
        if was_active:
            skill.status = SkillStatus.ACTIVE

    def _handle_skill_unload(self, name: str) -> None:
        self._skills.pop(name, None)
        self._skill_origin.pop(name, None)
        self._skill_content_revision.pop(name, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def get_skill_content_revision(self, name: str) -> str:
        """Filesystem fingerprint for bundled skill payloads (bundle cache invalidation)."""
        return self._skill_content_revision.get(name, "")

    def has_skill(self, name: str) -> bool:
        return name in self._skills

    def origin_of(self, name: str) -> DiscoveryRoot | None:
        return self._skill_origin.get(name)

    def is_skill_editable(self, name: str) -> bool:
        """True when SKILL.md exists and is writable and the skill is not builtin."""
        origin = self.origin_of(name)
        if origin is not None and origin.scope == "builtin":
            return False
        skill = self.get_skill(name)
        if not skill or not skill.path:
            return False
        md = skill.skill_md_path
        if not md or not md.exists():
            return False
        return os.access(md, os.W_OK)

    def _find_loader_for_skill(self, name: str) -> SkillLoader | None:
        for loader in self._loaders:
            if name in loader.loaded_skills:
                return loader
        return None

    async def update_skill_file(self, name: str, content: str) -> Skill:
        """Write SKILL.md for *name* after validation and reload the skill."""
        from leagent.skills.loader import (
            SkillLoadError,
            SkillLoader,
            SkillValidationError,
        )

        if not self.is_skill_editable(name):
            raise SkillFileNotEditableError(name)

        skill = self.get_skill(name)
        if not skill or not skill.path:
            raise SkillNotFoundError(name)

        md_path = skill.skill_md_path
        if not md_path:
            raise SkillFileUpdateError(name, "No SKILL.md path")

        loader = self._find_loader_for_skill(name)
        effective = loader or SkillLoader(skill.path.parent, source=skill.source)

        try:
            effective.validate_skill_content(skill.path, content)
        except SkillValidationError as exc:
            raise SkillFileUpdateError(name, "; ".join(exc.errors)) from exc
        except SkillLoadError as exc:
            raise SkillFileUpdateError(name, exc.reason) from exc

        old_text = md_path.read_text(encoding="utf-8")
        reloaded: Skill | None = None
        try:
            md_path.write_text(content, encoding="utf-8")
            if loader is not None:
                reloaded = await loader.reload_skill(name)
            else:
                reloaded = await effective.load_skill(skill.path)
                if reloaded:
                    self._handle_skill_reload(reloaded)
        except Exception:
            md_path.write_text(old_text, encoding="utf-8")
            raise

        if reloaded is None:
            md_path.write_text(old_text, encoding="utf-8")
            raise SkillFileUpdateError(name, "Reload failed after write")

        out = self.get_skill(name)
        return out if out is not None else reloaded

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------
    async def activate(self, name: str, config: dict[str, Any] | None = None) -> Skill:
        skill = self._skills.get(name)
        if not skill:
            raise SkillNotFoundError(name)

        if skill.is_active:
            if config:
                skill.config.update(config)
            return skill

        try:
            skill.status = SkillStatus.LOADING
            if config:
                skill.config.update(config)
            skill.status = SkillStatus.ACTIVE
            skill.error = None
            for cb in self._on_activate_callbacks:
                try:
                    cb(skill)
                except Exception:  # noqa: BLE001
                    pass
            logger.info("skill_activated", name=name)
            return skill
        except Exception as exc:  # noqa: BLE001
            skill.status = SkillStatus.ERROR
            skill.error = str(exc)
            raise SkillActivationError(name, str(exc))

    async def deactivate(self, name: str) -> bool:
        skill = self._skills.get(name)
        if not skill:
            return False
        if not skill.is_active:
            return True
        skill.status = SkillStatus.INACTIVE
        for cb in self._on_deactivate_callbacks:
            try:
                cb(name)
            except Exception:  # noqa: BLE001
                pass
        logger.info("skill_deactivated", name=name)
        return True

    async def activate_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name in list(self._skills.keys()):
            try:
                await self.activate(name)
                results[name] = True
            except Exception:  # noqa: BLE001
                results[name] = False
        return results

    async def deactivate_all(self) -> None:
        for name in list(self._skills.keys()):
            await self.deactivate(name)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------
    def list_by_category(self, category: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.manifest.category == category]

    def list_by_tag(self, tag: str) -> list[Skill]:
        return [s for s in self._skills.values() if tag in s.manifest.tags]

    def search(self, query: str) -> list[Skill]:
        q = query.lower()
        out: list[Skill] = []
        for s in self._skills.values():
            if q in s.name.lower() or q in s.description.lower():
                out.append(s)
                continue
            if any(q in tag.lower() for tag in s.manifest.tags):
                out.append(s)
        return out

    # ------------------------------------------------------------------
    # Progressive-disclosure gating helpers
    # ------------------------------------------------------------------
    def any_skill_has_resources(self) -> bool:
        return any(s.manifest.has_resources for s in self._skills.values())

    def any_skill_has_scripts(self) -> bool:
        return any(s.manifest.has_scripts for s in self._skills.values())

    def get_active_advertisement(self) -> list[dict[str, Any]]:
        """Return the Level-1 advertisement payload for each enabled skill."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "version": s.version,
                "has_resources": s.manifest.has_resources,
                "has_scripts": s.manifest.has_scripts,
            }
            for s in self._skills.values()
            if s.enabled
        ]

    # ------------------------------------------------------------------
    # Hub / registry
    # ------------------------------------------------------------------
    async def search_hub(
        self,
        query: str = "",
        category: str | None = None,
        page: int = 1,
        limit: int = 20,
        *,
        github_override: GitHubCatalogOverride | None = None,
    ) -> list[SkillHubEntry]:
        reg_list: list[SkillHubEntry] = []
        try:
            reg_list = await self.registry.search(
                query=query,
                category=category,
                page=1,
                limit=_HUB_MERGE_CAP,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("skill_hub_registry_search_failed", error=str(exc))

        gh_list: list[SkillHubEntry] = []
        try:
            from leagent.skills.github_monorepo_catalog import GitHubMonorepoCatalog, get_github_monorepo_catalog

            if github_override is not None:
                gh_cat = GitHubMonorepoCatalog(
                    owner=github_override.owner,
                    repo=github_override.repo,
                    ref=github_override.ref,
                    skills_path=github_override.skills_path,
                    enabled=True,
                )
                try:
                    gh_list = await gh_cat.search_all_matching(query=query, category=category)
                finally:
                    await gh_cat.aclose()
            else:
                singleton_cat = get_github_monorepo_catalog()
                if singleton_cat is not None:
                    gh_list = await singleton_cat.search_all_matching(query=query, category=category)
        except Exception as exc:  # noqa: BLE001
            logger.warning("skill_hub_github_search_failed", error=str(exc))

        merged: dict[str, SkillHubEntry] = {}
        for e in reg_list:
            merged[e.name] = e
        for e in gh_list:
            merged.setdefault(e.name, e)

        rows = sorted(merged.values(), key=lambda x: x.name)
        q = (query or "").strip().lower()
        if q:
            rows = [
                e
                for e in rows
                if q in e.name.lower() or q in (e.description or "").lower()
            ]
        start = max(0, (page - 1) * limit)
        return rows[start : start + limit]

    async def get_hub_skill(self, name: str) -> SkillHubEntry | None:
        try:
            entry = await self.registry.get(name)
            if entry is not None:
                return entry
        except Exception as exc:  # noqa: BLE001
            logger.warning("skill_hub_registry_get_failed", name=name, error=str(exc))

        try:
            from leagent.skills.github_monorepo_catalog import get_github_monorepo_catalog

            gh_cat = get_github_monorepo_catalog()
            if gh_cat is not None:
                gh_entry = await gh_cat.get(name)
                if gh_entry is not None:
                    return gh_entry
        except Exception as exc:  # noqa: BLE001
            logger.warning("skill_hub_github_get_failed", name=name, error=str(exc))
        return None

    async def install_from_hub(
        self,
        name: str,
        *,
        github_override: GitHubCatalogOverride | None = None,
    ) -> Skill | None:
        if not self._skills_dir:
            logger.error("skill_hub_install_no_dir")
            return None

        dest_base = self._skills_dir / "skills" if self._skills_dir.name != "skills" else self._skills_dir

        hub_entry: SkillHubEntry | None = None
        try:
            hub_entry = await self.registry.get(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("skill_hub_registry_get_failed", name=name, error=str(exc))
            hub_entry = None

        if hub_entry is not None:
            try:
                skill = await self.registry.install(name, dest_base)
                if skill:
                    self._skills[skill.name] = skill
                return skill
            except Exception as exc:  # noqa: BLE001
                logger.error("skill_hub_registry_install_failed", name=name, error=str(exc))
                return None

        try:
            from leagent.skills.github_monorepo_catalog import GitHubMonorepoCatalog, get_github_monorepo_catalog

            if github_override is not None:
                gh_cat = GitHubMonorepoCatalog(
                    owner=github_override.owner,
                    repo=github_override.repo,
                    ref=github_override.ref,
                    skills_path=github_override.skills_path,
                    enabled=True,
                )
                try:
                    skill = await gh_cat.install(name, dest_base)
                finally:
                    await gh_cat.aclose()
            else:
                singleton_cat = get_github_monorepo_catalog()
                if singleton_cat is None:
                    return None
                skill = await singleton_cat.install(name, dest_base)
            if skill:
                self._skills[skill.name] = skill
            return skill
        except Exception as exc:  # noqa: BLE001
            logger.error("skill_hub_github_install_failed", name=name, error=str(exc))
            return None

    async def install_from_url(self, url: str, sha256: str | None = None) -> Skill | None:
        """Download a skill archive from *url* and install under the user skills directory."""
        if not self._skills_dir:
            logger.error("skill_url_install_no_dir")
            return None

        dest_base = self._skills_dir / "skills" if self._skills_dir.name != "skills" else self._skills_dir
        try:
            from leagent.skills.url_install import SkillURLError, install_skill_from_url

            skill = await install_skill_from_url(url, dest_base, expected_sha256=sha256)
        except SkillURLError as exc:
            logger.error("skill_url_install_invalid", error=str(exc))
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("skill_url_install_failed", error=str(exc))
            return None

        if skill:
            self._skills[skill.name] = skill
        return skill

    async def install_from_local_directory(
        self, source: Path, target_name: str
    ) -> Skill | None:
        """Copy a skill directory from the workspace into the user skills directory."""
        if not self._skills_dir:
            logger.error("skill_local_install_no_dir")
            return None

        dest_base = self._skills_dir / "skills" if self._skills_dir.name != "skills" else self._skills_dir
        try:
            from leagent.skills.local_install import (
                LocalSkillInstallError,
                install_skill_from_workspace_directory,
            )

            skill = await install_skill_from_workspace_directory(
                source, dest_base, target_name=target_name
            )
        except LocalSkillInstallError as exc:
            logger.error("skill_local_install_invalid", error=str(exc))
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("skill_local_install_failed", error=str(exc))
            return None

        if skill:
            self._skills[skill.name] = skill
        return skill

    async def install_from_local_archive(self, archive_path: Path) -> Skill | None:
        """Install a ``.zip`` or ``.tar.gz`` from a local file path (same rules as URL install)."""
        if not self._skills_dir:
            logger.error("skill_archive_install_no_dir")
            return None

        dest_base = self._skills_dir / "skills" if self._skills_dir.name != "skills" else self._skills_dir
        try:
            from leagent.skills.url_install import SkillURLError, install_skill_from_archive_path

            skill = await install_skill_from_archive_path(archive_path, dest_base)
        except SkillURLError as exc:
            logger.error("skill_archive_install_invalid", error=str(exc))
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("skill_archive_install_failed", error=str(exc))
            return None

        if skill:
            self._skills[skill.name] = skill
        return skill

    async def uninstall(self, name: str) -> bool:
        """Remove a user-installed skill from disk and the registry."""
        if not self._skills_dir:
            return False
        try:
            ok = await self.registry.uninstall(name, self._skills_dir)
        except Exception as exc:  # noqa: BLE001
            logger.error("skill_uninstall_failed", name=name, error=str(exc))
            return False
        if ok:
            self._skills.pop(name, None)
            self._skill_origin.pop(name, None)
        return ok

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def shutdown(self) -> None:
        await self.deactivate_all()
        for loader in self._loaders:
            loader.stop_watching()
        self._loaders.clear()
        if self._registry is not None:
            close = getattr(self._registry, "aclose", None)
            if close is not None:
                try:
                    await close()
                except Exception:  # noqa: BLE001
                    pass
        try:
            from leagent.skills.github_monorepo_catalog import shutdown_github_monorepo_catalog

            await shutdown_github_monorepo_catalog()
        except Exception:  # noqa: BLE001
            pass
        logger.info("skills_manager_shutdown")


_default_manager: SkillsManager | None = None


def get_skills_manager() -> SkillsManager:
    """Return the process-wide SkillsManager singleton."""
    global _default_manager
    if _default_manager is None:
        try:
            from leagent.config.constants import LEAGENT_HOME
            from leagent.config.settings import get_settings

            raw = (get_settings().skills_directory or "").strip()
            skills_dir = Path(raw).expanduser().resolve() if raw else LEAGENT_HOME / "skills"
            skills_dir.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001
            skills_dir = None
        _default_manager = SkillsManager(skills_dir=skills_dir)
    return _default_manager


def reset_skills_manager() -> None:
    """Drop the singleton (testing hook)."""
    global _default_manager
    _default_manager = None
