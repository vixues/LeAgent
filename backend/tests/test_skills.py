"""Tests for the skills subsystem (Agent Skills v1.0 open spec).

The suite covers:

- Models (:class:`TestSkillModels`)
- SKILL.md parsing + validation (:class:`TestSkillLoader`)
- Hot reload (:class:`TestSkillLoaderHotReload`)
- Manager orchestration (:class:`TestSkillsManager`)
- Progressive-disclosure tools (:class:`TestProgressiveDisclosure`)
- Cross-agent discovery (:class:`TestDiscovery`)
- Pluggable registry (:class:`TestRegistry`)
- CLI helpers (:class:`TestCliMigrate`)
- SKILL.md parser utility (:class:`TestMarkdownParser`)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from leagent.skills.base import (
    Skill,
    SkillManifest,
    SkillSource,
    SkillStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill(dir_: Path, name: str = "test-skill", **extra: Any) -> Path:
    """Write a minimal valid SKILL.md for *name* into *dir_/name*."""
    skill_dir = dir_ / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    description = extra.pop("description", f"Describe {name} and when to use it.")
    lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
    ]
    for key, value in extra.items():
        if isinstance(value, (list, dict)):
            import yaml

            lines.append(yaml.dump({key: value}, default_flow_style=False).strip())
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {name}")
    lines.append("Instructions for the agent.")
    (skill_dir / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return skill_dir


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestSkillModels:
    def test_manifest_defaults(self) -> None:
        manifest = SkillManifest(name="sample", description="A sample skill.")
        assert manifest.version == "1.0.0"
        assert manifest.category == "general"
        assert manifest.tags == []
        assert manifest.allowed_tools == []
        assert not manifest.has_resources
        assert not manifest.has_scripts

    def test_manifest_reads_metadata(self) -> None:
        manifest = SkillManifest(
            name="sample",
            description="A sample skill.",
            metadata={"version": "2.5.0", "author": "Alice", "tags": ["a", "b"], "category": "data"},
        )
        assert manifest.version == "2.5.0"
        assert manifest.author == "Alice"
        assert manifest.category == "data"
        assert manifest.tags == ["a", "b"]

    def test_skill_enabled_and_active_flags(self) -> None:
        manifest = SkillManifest(name="sample", description="A sample skill.")
        skill = Skill(manifest=manifest, source=SkillSource.LOCAL)
        assert skill.status == SkillStatus.INACTIVE
        assert not skill.is_active
        assert skill.enabled  # non-error == enabled for advertising

        skill.status = SkillStatus.ACTIVE
        assert skill.is_active

        skill.status = SkillStatus.ERROR
        assert not skill.enabled

    def test_manifest_to_dict_roundtrip(self) -> None:
        manifest = SkillManifest(
            name="sample",
            description="desc",
            license="MIT",
            compatibility="LeAgent >=1.0",
            allowed_tools=["Bash(git:*)", "Read"],
            metadata={"version": "2.0.0", "tags": ["x"]},
        )
        data = manifest.to_dict()
        assert data["name"] == "sample"
        assert data["license"] == "MIT"
        assert data["compatibility"] == "LeAgent >=1.0"
        assert data["allowed_tools"] == ["Bash(git:*)", "Read"]
        assert data["version"] == "2.0.0"
        assert data["tags"] == ["x"]

    def test_manifest_tags_comma_string(self) -> None:
        manifest = SkillManifest(
            name="sample",
            description="d",
            metadata={"tags": "a, b,  c"},
        )
        assert manifest.tags == ["a", "b", "c"]

    def test_skill_resource_and_script_lookup(self) -> None:
        from leagent.skills.base import (
            SkillResource,
            SkillResourceKind,
            SkillScript,
        )

        res = SkillResource(
            relative_path="references/api.md",
            absolute_path=Path("/tmp/x/references/api.md"),
            kind=SkillResourceKind.REFERENCE,
        )
        script = SkillScript(
            relative_path="scripts/run.py",
            absolute_path=Path("/tmp/x/scripts/run.py"),
            interpreter="python",
        )
        manifest = SkillManifest(
            name="sample", description="d", resources=[res], scripts=[script]
        )
        skill = Skill(manifest=manifest)
        assert skill.get_resource("references/api.md") is res
        assert skill.get_resource("missing.md") is None
        assert skill.get_script("scripts/run.py") is script
        assert skill.get_script("scripts/missing.py") is None

    def test_hub_entry_from_dict_and_to_dict(self) -> None:
        from leagent.skills.base import SkillHubEntry

        entry = SkillHubEntry.from_dict(
            {
                "name": "pkg",
                "description": "d",
                "version": "1.2.3",
                "download_url": "https://example.com/pkg.tar.gz",
                "checksum": "abc123",
                "downloads": "42",
                "rating": "4.5",
            }
        )
        assert entry.name == "pkg"
        assert entry.url == "https://example.com/pkg.tar.gz"
        assert entry.sha256 == "abc123"
        assert entry.downloads == 42
        assert entry.rating == 4.5
        assert entry.to_dict()["url"] == entry.url


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSkillLoader:
    async def test_loads_valid_skill(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader

        _write_skill(tmp_path, "my-skill")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        skills = await loader.load_all()
        assert "my-skill" in skills
        assert skills["my-skill"].manifest.description.startswith("Describe")

    async def test_rejects_dir_mismatch(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader, SkillValidationError

        _write_skill(tmp_path, "inner-name")
        (tmp_path / "inner-name").rename(tmp_path / "outer-name")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)

        with pytest.raises(SkillValidationError):
            await loader.load_skill(tmp_path / "outer-name")

    async def test_rejects_reserved_name(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader, SkillValidationError

        _write_skill(tmp_path, "claude")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        with pytest.raises(SkillValidationError):
            await loader.load_skill(tmp_path / "claude")

    async def test_rejects_bad_name_format(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader, SkillValidationError

        _write_skill(tmp_path, "Bad_Name")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        with pytest.raises(SkillValidationError):
            await loader.load_skill(tmp_path / "Bad_Name")

    async def test_rejects_description_too_long(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader, SkillValidationError

        _write_skill(tmp_path, "big-desc", description="x" * 1100)
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        with pytest.raises(SkillValidationError):
            await loader.load_skill(tmp_path / "big-desc")

    async def test_rejects_xml_in_description(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader, SkillValidationError

        _write_skill(tmp_path, "xml-desc", description="Do <evil>stuff</evil>.")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        with pytest.raises(SkillValidationError):
            await loader.load_skill(tmp_path / "xml-desc")

    async def test_discovers_resources_and_scripts(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader

        skill_dir = _write_skill(tmp_path, "rich-skill")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "api.md").write_text("# API", encoding="utf-8")
        (skill_dir / "assets").mkdir()
        (skill_dir / "assets" / "template.json").write_text("{}", encoding="utf-8")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "run.py").write_text("print('hi')", encoding="utf-8")

        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        await loader.load_all()
        skill = loader.get_skill("rich-skill")
        assert skill is not None
        kinds = {r.kind.value for r in skill.manifest.resources}
        assert "reference" in kinds
        assert "asset" in kinds
        assert any(s.relative_path == "scripts/run.py" for s in skill.manifest.scripts)
        assert skill.manifest.has_resources
        assert skill.manifest.has_scripts

    async def test_discovers_root_level_reference_files(self, tmp_path: Path) -> None:
        """Community skills often ship docs next to SKILL.md (not under references/)."""
        from leagent.skills.loader import SkillLoader

        skill_dir = _write_skill(tmp_path, "pptx")
        (skill_dir / "pptxgenjs.md").write_text("# PptxGenJS notes", encoding="utf-8")

        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        await loader.load_all()
        skill = loader.get_skill("pptx")
        assert skill is not None
        paths = {r.relative_path for r in skill.manifest.resources}
        assert "pptxgenjs.md" in paths
        assert skill.get_resource("pptxgenjs.md") is not None

    async def test_filters_disallowed_extensions(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader

        skill_dir = _write_skill(tmp_path, "strict-ext")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "blob.bin").write_bytes(b"\x00")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "noop.bin").write_bytes(b"\x00")

        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        await loader.load_all()
        skill = loader.get_skill("strict-ext")
        assert skill is not None
        assert skill.manifest.resources == []
        assert skill.manifest.scripts == []

    async def test_lazy_body_read(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader

        _write_skill(tmp_path, "lazy-skill")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        await loader.load_all()
        skill = loader.get_skill("lazy-skill")
        assert skill is not None
        assert skill._cached_body is None  # not yet read
        body = skill.read_body()
        assert "Instructions for the agent" in body
        # Second call returns cached copy.
        assert skill.read_body() is body

    async def test_body_cache_invalidates_on_mtime(self, tmp_path: Path) -> None:
        """Editing SKILL.md must invalidate the cached body."""
        import os
        import time

        from leagent.skills.loader import SkillLoader

        skill_dir = _write_skill(tmp_path, "mutable")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        await loader.load_all()
        skill = loader.get_skill("mutable")
        assert skill is not None

        first = skill.read_body()
        assert "Instructions" in first

        new_content = (
            "---\nname: mutable\ndescription: new one.\n---\n\nBrand new body content.\n"
        )
        md_path = skill_dir / "SKILL.md"
        md_path.write_text(new_content, encoding="utf-8")
        # Force a distinctly newer mtime — on some filesystems the
        # default resolution is too coarse otherwise.
        future = time.time() + 2
        os.utime(md_path, (future, future))

        refreshed = skill.read_body()
        assert "Brand new body content" in refreshed
        assert "Instructions" not in refreshed

    async def test_allowed_tools_normalisation_list(self, tmp_path: Path) -> None:
        """``allowed-tools`` given as a YAML list is normalised to a Python list."""
        from leagent.skills.loader import SkillLoader

        _write_skill(
            tmp_path,
            "list-tools",
            **{"allowed-tools": ["Bash(git:*)", "Read", "Write"]},
        )
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        await loader.load_all()
        skill = loader.get_skill("list-tools")
        assert skill is not None
        assert skill.manifest.allowed_tools == ["Bash(git:*)", "Read", "Write"]

    async def test_allowed_tools_normalisation_string(self, tmp_path: Path) -> None:
        """Spec form: space-delimited string → list of tokens."""
        from leagent.skills.loader import SkillLoader

        _write_skill(
            tmp_path,
            "string-tools",
            **{"allowed-tools": "Bash(git:*) Read Write"},
        )
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        await loader.load_all()
        skill = loader.get_skill("string-tools")
        assert skill is not None
        assert skill.manifest.allowed_tools == ["Bash(git:*)", "Read", "Write"]

    async def test_compatibility_too_long_rejected(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader, SkillValidationError

        _write_skill(tmp_path, "compat", compatibility="x" * 600)
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        with pytest.raises(SkillValidationError):
            await loader.load_skill(tmp_path / "compat")

    async def test_missing_skill_md_rejected(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoadError, SkillLoader

        skill_dir = tmp_path / "empty-dir"
        skill_dir.mkdir()
        (skill_dir / "README.md").write_text("nothing here", encoding="utf-8")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        with pytest.raises(SkillLoadError):
            await loader.load_skill(skill_dir)

    async def test_load_all_ignores_dotdirs(self, tmp_path: Path) -> None:
        from leagent.skills.loader import SkillLoader

        _write_skill(tmp_path, "visible")
        _write_skill(tmp_path, "_hidden")
        (tmp_path / ".dot-dir").mkdir()
        (tmp_path / ".dot-dir" / "SKILL.md").write_text(
            "---\nname: hidden\ndescription: hidden\n---\n", encoding="utf-8"
        )
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        skills = await loader.load_all()
        assert "visible" in skills
        assert "_hidden" not in skills
        assert ".dot-dir" not in skills


# ---------------------------------------------------------------------------
# Hot reload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSkillLoaderHotReload:
    async def test_detects_new_and_modified_and_removed(self, tmp_path: Path) -> None:
        """_check_for_changes loads new dirs and drops removed ones."""
        import os
        import time

        from leagent.skills.loader import SkillLoader

        _write_skill(tmp_path, "first")
        loader = SkillLoader(tmp_path, source=SkillSource.LOCAL)
        await loader.load_all()
        assert loader.get_skill("first") is not None

        # Add a new skill after the initial load.
        _write_skill(tmp_path, "second")
        await loader._check_for_changes()
        assert loader.get_skill("second") is not None

        # Modify the first skill's SKILL.md and verify the body updates.
        first_md = tmp_path / "first" / "SKILL.md"
        first_md.write_text(
            "---\nname: first\ndescription: updated description.\n---\n\nNew body.\n",
            encoding="utf-8",
        )
        future = time.time() + 2
        os.utime(first_md, (future, future))
        await loader._check_for_changes()
        assert loader.get_skill("first").description == "updated description."

        # Remove the second skill directory entirely.
        import shutil

        shutil.rmtree(tmp_path / "second")
        await loader._check_for_changes()
        assert loader.get_skill("second") is None


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSkillsManager:
    async def test_loads_and_activates(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager

        _write_skill(tmp_path, "activateable")
        manager = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await manager.load_all()
        assert manager.has_skill("activateable")

        skill = await manager.activate("activateable")
        assert skill.is_active

        await manager.deactivate("activateable")
        assert not manager.get_skill("activateable").is_active

    async def test_any_skill_has_resources_helpers(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager

        skill_dir = _write_skill(tmp_path, "progressive")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "doc.md").write_text("doc", encoding="utf-8")

        manager = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await manager.load_all()
        assert manager.any_skill_has_resources()
        assert not manager.any_skill_has_scripts()

    async def test_search(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager

        _write_skill(tmp_path, "alpha", description="Describe alpha analyzer.")
        _write_skill(tmp_path, "beta", description="Describe beta converter.")
        manager = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await manager.load_all()
        results = manager.search("analyzer")
        names = [s.name for s in results]
        assert "alpha" in names
        assert "beta" not in names

    async def test_list_by_category_and_tag(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager

        _write_skill(
            tmp_path,
            "cat-a",
            metadata={"category": "data", "tags": ["stats", "reports"]},
        )
        _write_skill(
            tmp_path,
            "cat-b",
            metadata={"category": "gen", "tags": ["template"]},
        )
        manager = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await manager.load_all()
        assert [s.name for s in manager.list_by_category("data")] == ["cat-a"]
        assert [s.name for s in manager.list_by_tag("template")] == ["cat-b"]

    async def test_activate_unknown_raises(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager, SkillNotFoundError

        manager = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        with pytest.raises(SkillNotFoundError):
            await manager.activate("ghost")

    async def test_activate_merges_config(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager

        _write_skill(tmp_path, "cfg")
        manager = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await manager.load_all()
        skill = await manager.activate("cfg", {"threshold": 5})
        assert skill.config == {"threshold": 5}
        # Activating again merges extra keys in.
        skill = await manager.activate("cfg", {"mode": "fast"})
        assert skill.config == {"threshold": 5, "mode": "fast"}

    async def test_advertisement_snapshot(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager

        _write_skill(tmp_path, "visible")
        manager = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await manager.load_all()
        ads = manager.get_active_advertisement()
        assert len(ads) == 1
        assert ads[0]["name"] == "visible"
        assert ads[0]["has_resources"] is False
        assert ads[0]["has_scripts"] is False

    async def test_precedence_explicit_over_builtin(self, tmp_path: Path) -> None:
        """When a user skills_dir shadows a builtin skill name, the user wins."""
        from leagent.skills.manager import SkillsManager

        # Use the real builtin name to force a precedence clash.
        _write_skill(tmp_path, "data-analyzer", description="User override.")
        manager = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=True,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await manager.load_all()
        skill = manager.get_skill("data-analyzer")
        assert skill is not None
        assert skill.description == "User override."
        origin = manager.origin_of("data-analyzer")
        assert origin is not None
        assert origin.scope == "user"


# ---------------------------------------------------------------------------
# Progressive disclosure tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProgressiveDisclosure:
    async def test_load_skill_returns_body(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        _write_skill(tmp_path, "probe")
        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        result = await SkillTool().execute({"skill_name": "probe"}, ToolContext(user_id=None, session_id=None))
        assert result["found"] is True
        assert "Instructions for the agent" in result["content"]

    async def test_read_skill_resource_second_call_hits_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from leagent.skills import manager as manager_mod
        from leagent.skills.manager import SkillsManager
        from leagent.skills.resource_cache import clear_skill_resource_read_cache
        from leagent.tools.base import ToolContext
        from leagent.tools.skills import resource as resource_mod
        from leagent.tools.skills.resource import SkillResourceTool

        clear_skill_resource_read_cache()

        skill_dir = _write_skill(tmp_path, "res-cache")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "note.md").write_text("NOTE_BODY", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        reads: list[int] = []
        real_read = resource_mod._read_resource_payload

        def counting_read(*args: Any, **kwargs: Any) -> Any:
            reads.append(1)
            return real_read(*args, **kwargs)

        monkeypatch.setattr(resource_mod, "_read_resource_payload", counting_read)

        tool = SkillResourceTool()
        ctx = ToolContext(user_id=None, session_id=None)
        p = {"skill_name": "res-cache", "resource_path": "references/note.md"}
        r1 = await tool.execute(p, ctx)
        r2 = await tool.execute(p, ctx)
        assert r1["found"] and r2["found"]
        assert r1["content"] == "NOTE_BODY" == r2["content"]
        assert len(reads) == 1

    async def test_load_skill_bundle_second_call_hits_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from leagent.skills import bundle_payload as bp
        from leagent.skills.bundle_payload_cache import clear_bundle_payload_cache
        from leagent.skills import manager as manager_mod
        from leagent.skills.manager import SkillsManager
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        clear_bundle_payload_cache()

        skill_dir = _write_skill(tmp_path, "bundle-cache")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "note.md").write_text("REF_INLINE_BODY", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        builds: list[int] = []
        real_build = bp.build_bundle_payload

        def counting_build(*args: Any, **kwargs: Any) -> Any:
            builds.append(1)
            return real_build(*args, **kwargs)

        monkeypatch.setattr(bp, "build_bundle_payload", counting_build)

        tool = SkillTool()
        ctx = ToolContext(user_id=None, session_id=None)
        params = {"skill_name": "bundle-cache", "include_bundled_content": True}
        await tool.execute(params, ctx)
        await tool.execute(params, ctx)
        assert len(builds) == 1

    async def test_skills_manager_content_revision_tracks_loader(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager

        _write_skill(tmp_path, "rev-skill")
        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        rev = mgr.get_skill_content_revision("rev-skill")
        assert isinstance(rev, str)
        assert len(rev) >= 8

    async def test_load_skill_bundles_inline_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        skill_dir = _write_skill(tmp_path, "packed")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "note.md").write_text("REF_INLINE_BODY", encoding="utf-8")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "tool.py").write_text("print('bundled')", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        result = await SkillTool().execute(
            {"skill_name": "packed", "include_bundled_content": True},
            ToolContext(user_id=None, session_id=None),
        )
        assert result["found"] is True
        assert result["include_bundled_content"] is True
        res_paths = [r["path"] for r in result["bundled_resources"]]
        assert "references/note.md" in res_paths
        assert any(r["path"] == "references/note.md" and r["content"] == "REF_INLINE_BODY" for r in result["bundled_resources"])
        assert any(
            s["path"] == "scripts/tool.py" and "print('bundled')" in s["content"] for s in result["bundled_scripts"]
        )

    async def test_load_skill_bundle_on_load_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        skill_dir = _write_skill(
            tmp_path,
            "meta-bundle",
            metadata={"leagent": {"bundle_on_load": True}},
        )
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "guide.md").write_text("FROM_METADATA_BUNDLE", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        result = await SkillTool().execute({"skill_name": "meta-bundle"}, ToolContext(user_id=None, session_id=None))
        assert result["found"] is True
        assert result["include_bundled_content"] is True
        assert any("FROM_METADATA_BUNDLE" in r.get("content", "") for r in result["bundled_resources"])

    async def test_load_skill_explicit_opt_out_overrides_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        skill_dir = _write_skill(
            tmp_path,
            "opt-out",
            metadata={"leagent": {"bundle_on_load": True}},
        )
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "secret.md").write_text("SHOULD_NOT_APPEAR", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        result = await SkillTool().execute(
            {"skill_name": "opt-out", "include_bundled_content": False},
            ToolContext(user_id=None, session_id=None),
        )
        assert result["found"] is True
        assert result["include_bundled_content"] is False
        assert "bundled_resources" not in result

    async def test_load_skill_bundle_respects_budget(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        skill_dir = _write_skill(tmp_path, "huge-body")
        huge = "x" * 190_000
        (skill_dir / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: huge-body",
                    "description: Describe huge-body and when to use it.",
                    "---",
                    "",
                    "# huge-body",
                    huge,
                ]
            ),
            encoding="utf-8",
        )
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "late.md").write_text("LATE_FILE", encoding="utf-8")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "small.py").write_text("# SHORT_SCRIPT_OK\n", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        tool = SkillTool()
        result = await tool.execute(
            {"skill_name": "huge-body", "include_bundled_content": True},
            ToolContext(user_id=None, session_id=None),
        )
        assert result["found"] is True
        assert "truncation_notes" in result
        # Huge SKILL.md is truncated to reserve budget; small reference + script sources still inline.
        late_in_bundle = any(
            isinstance(r, dict) and r.get("content") and "LATE_FILE" in r["content"]
            for r in result.get("bundled_resources", [])
        )
        assert late_in_bundle
        script_in_bundle = any(
            isinstance(s, dict) and s.get("content") and "SHORT_SCRIPT_OK" in s["content"]
            for s in result.get("bundled_scripts", [])
        )
        assert script_in_bundle
        assert any("reserve space for" in n.lower() or "truncat" in n.lower() for n in result["truncation_notes"])

    async def test_load_skill_bundles_root_txt_refs_and_script(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        skill_dir = _write_skill(tmp_path, "full-pack")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "api.md").write_text("REF_API_BODY", encoding="utf-8")
        (skill_dir / "note.txt").write_text("ROOT_NOTE_TEXT", encoding="utf-8")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "a.py").write_text("print('a')", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        result = await SkillTool().execute(
            {"skill_name": "full-pack", "include_bundled_content": True},
            ToolContext(user_id=None, session_id=None),
        )
        assert result["found"] is True
        assert any("REF_API_BODY" in (r.get("content") or "") for r in result["bundled_resources"])
        assert any(
            r.get("path") == "note.txt" and "ROOT_NOTE_TEXT" in (r.get("content") or "")
            for r in result["bundled_resources"]
        )
        assert any(
            s.get("path") == "scripts/a.py" and "print('a')" in (s.get("content") or "")
            for s in result["bundled_scripts"]
        )

    async def test_load_skill_bundle_binary_placeholder_not_inline_base64(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-UTF-8 bytes under a discovered extension become placeholders — no base64 in load_skill."""
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        skill_dir = _write_skill(tmp_path, "bin-pack")
        (skill_dir / "references").mkdir()
        # `.txt` is discovered by the loader; invalid UTF-8 still counts as binary for bundling.
        (skill_dir / "references" / "opaque.txt").write_bytes(b"\xff\xfe\xfd")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        result = await SkillTool().execute(
            {"skill_name": "bin-pack", "include_bundled_content": True},
            ToolContext(user_id=None, session_id=None),
        )
        assert result["found"] is True
        rows = [r for r in result["bundled_resources"] if r.get("path") == "references/opaque.txt"]
        assert len(rows) == 1
        assert rows[0].get("content") is None
        assert rows[0].get("omitted") == "binary"
        assert "content_base64" not in rows[0]

    async def test_load_skill_bundle_truncates_large_resource(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.loader import SkillTool

        skill_dir = _write_skill(tmp_path, "big-ref")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "big.md").write_text("z" * 60_000, encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        result = await SkillTool().execute(
            {"skill_name": "big-ref", "include_bundled_content": True},
            ToolContext(user_id=None, session_id=None),
        )
        assert result["found"] is True
        assert "truncation_notes" in result
        entry = next(r for r in result["bundled_resources"] if r["path"] == "references/big.md")
        assert entry.get("truncated") is True
        assert len(entry["content"]) <= 50_000

    async def test_read_resource_returns_skill_name(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.resource import SkillResourceTool

        skill_dir = _write_skill(tmp_path, "guarded")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "note.md").write_text("hello", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        tool = SkillResourceTool()
        ctx = ToolContext(user_id=None, session_id=None)
        ok = await tool.execute({"skill_name": "guarded", "resource_path": "references/note.md"}, ctx)
        assert ok["found"] is True
        assert ok["skill_name"] == "guarded"

    async def test_read_resource_rejects_escape(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.resource import SkillResourceTool

        skill_dir = _write_skill(tmp_path, "guarded")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "note.md").write_text("hello", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        tool = SkillResourceTool()
        ctx = ToolContext(user_id=None, session_id=None)
        # Legitimate resource read.
        ok = await tool.execute({"skill_name": "guarded", "resource_path": "references/note.md"}, ctx)
        assert ok["found"] is True
        assert ok["content"] == "hello"

        # Path escape attempts are denied.
        bad = await tool.execute({"skill_name": "guarded", "resource_path": "../outside.md"}, ctx)
        assert bad["found"] is False

    async def test_run_script_requires_env_flag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.config.settings import get_settings
        from leagent.skills.manager import SkillsManager
        from leagent.skills import manager as manager_mod
        from leagent.tools.base import ToolContext
        from leagent.tools.skills.script import ENV_FLAG, SkillScriptTool

        skill_dir = _write_skill(tmp_path, "scripter")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "hi.py").write_text("print('hi')", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        monkeypatch.setattr(manager_mod, "get_skills_manager", lambda: mgr)

        tool = SkillScriptTool()
        ctx = ToolContext(user_id=None, session_id=None)

        monkeypatch.setenv(ENV_FLAG, "0")
        get_settings.cache_clear()
        denied = await tool.execute(
            {"skill_name": "scripter", "script_path": "scripts/hi.py"},
            ctx,
        )
        assert denied["ok"] is False
        assert "disabled" in denied["message"].lower()

        monkeypatch.setenv(ENV_FLAG, "1")
        get_settings.cache_clear()
        allowed = await tool.execute(
            {"skill_name": "scripter", "script_path": "scripts/hi.py"},
            ctx,
        )
        assert allowed.get("ok") is True
        assert "hi" in allowed.get("stdout", "")


# ---------------------------------------------------------------------------
# Skill Python deps (uv)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSkillPythonDeps:
    async def test_ensure_skips_without_declarations(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills.python_deps import ensure_skill_python_deps

        _write_skill(tmp_path, "nodeps")
        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        skill = mgr.get_skill("nodeps")
        assert skill is not None
        r = await ensure_skill_python_deps(skill)
        assert r["ok"] is True
        assert r.get("skipped") is True
        assert r.get("reason") == "no_python_dependency_declarations"

    async def test_ensure_invokes_uv_with_requirements(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio
        import shutil

        from leagent.config.settings import get_settings
        from leagent.skills.manager import SkillsManager
        from leagent.skills.python_deps import clear_skill_python_deps_cache, ensure_skill_python_deps

        clear_skill_python_deps_cache()
        get_settings.cache_clear()
        monkeypatch.setenv("LEAGENT_SKILL_PYTHON_DEPS_AUTO_INSTALL", "1")
        get_settings.cache_clear()

        skill_dir = _write_skill(tmp_path, "with-req")
        (skill_dir / "requirements.txt").write_text(
            "# test\npypdf>=3.0\n",
            encoding="utf-8",
        )
        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()
        skill = mgr.get_skill("with-req")
        assert skill is not None

        monkeypatch.setattr(shutil, "which", lambda name: "/fake/uv" if name == "uv" else None)

        exec_calls: list[tuple[Any, ...]] = []

        async def fake_exec(*args: Any, **kwargs: Any) -> Any:
            exec_calls.append(args)

            class _Proc:
                returncode = 0

                async def communicate(self) -> tuple[bytes, bytes]:
                    return b"installed", b""

            return _Proc()

        monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

        r = await ensure_skill_python_deps(skill)
        assert r["ok"] is True
        assert r.get("installed") is True
        assert len(exec_calls) == 1
        argv = exec_calls[0]
        assert argv[0] == "/fake/uv"
        assert "-r" in argv


# ---------------------------------------------------------------------------
# @skill referenced bundle (full resource injection)
# ---------------------------------------------------------------------------


class TestReferencedSkillBundle:
    def test_iter_skill_ids_from_message(self) -> None:
        from leagent.skills.referenced_bundle import iter_skill_ids_from_message

        text = "x @skill:显示名#pdf-skill y @skill:Other#data-analyzer z"
        assert iter_skill_ids_from_message(text) == ["pdf-skill", "data-analyzer"]

    @pytest.mark.asyncio
    async def test_build_append_extra_inlines_bundle(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills.referenced_bundle import build_referenced_skills_append_extra

        skill_dir = _write_skill(tmp_path, "pack-skill")
        (skill_dir / "references").mkdir()
        (skill_dir / "references" / "r.md").write_text("REF_BODY", encoding="utf-8")
        (skill_dir / "scripts").mkdir()
        (skill_dir / "scripts" / "a.py").write_text("print(1)", encoding="utf-8")

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        await mgr.load_all()

        msg = "Please use @skill:Label#pack-skill for this task."
        extra = build_referenced_skills_append_extra(msg, mgr)
        assert "Referenced Agent Skills" in extra
        assert "REF_BODY" in extra
        assert "print(1)" in extra
        assert "pack-skill" in extra


# ---------------------------------------------------------------------------
# Discovery / interop
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_collects_project_and_user_roots(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.discovery import collect_discovery_roots

        home = tmp_path / "home"
        project = tmp_path / "project"

        (project / ".leagent" / "skills").mkdir(parents=True)
        (project / ".openclaw" / "skills").mkdir(parents=True)
        (project / ".claude" / "skills").mkdir(parents=True)
        (home / ".openclaw").mkdir(parents=True)
        (home / ".claude" / "skills").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        roots = collect_discovery_roots(
            leagent_home=home / ".leagent",
            project_dir=project,
            builtin_dir=None,
        )
        scopes = [(r.scope, r.origin) for r in roots]
        assert ("project", "leagent") in scopes
        assert ("project", "openclaw") in scopes
        assert ("user", "openclaw") in scopes
        assert ("project", "claude") in scopes
        assert ("user", "claude") in scopes

    def test_precedence_sort(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.skills.discovery import collect_discovery_roots

        project = tmp_path / "p"
        (project / ".leagent" / "skills").mkdir(parents=True)
        (project / ".cursor" / "skills").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

        roots = collect_discovery_roots(leagent_home=None, project_dir=project, builtin_dir=None)
        priorities = [r.priority for r in roots]
        assert priorities == sorted(priorities)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRegistry:
    async def test_disabled_registry_rejects_install(self, tmp_path: Path) -> None:
        from leagent.skills.registry import DisabledRegistry, RegistryNotConfiguredError

        reg = DisabledRegistry()
        with pytest.raises(RegistryNotConfiguredError):
            await reg.install("anything", tmp_path)

    async def test_disabled_registry_local_uninstall(self, tmp_path: Path) -> None:
        from leagent.skills.registry import DisabledRegistry

        (tmp_path / "victim").mkdir()
        (tmp_path / "victim" / "SKILL.md").write_text("---\nname: victim\ndescription: x\n---\n", encoding="utf-8")
        reg = DisabledRegistry()
        assert await reg.uninstall("victim", tmp_path) is True
        assert not (tmp_path / "victim").exists()

    async def test_http_registry_install_rollback_on_bad_checksum(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tarfile

        from leagent.skills.base import SkillHubEntry
        from leagent.skills.registry import HTTPSkillRegistry

        # Build a real tar.gz archive for the skill.
        source_dir = tmp_path / "src" / "tarball-skill"
        _write_skill(tmp_path / "src", "tarball-skill")
        archive = tmp_path / "skill.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(source_dir, arcname="tarball-skill")

        reg = HTTPSkillRegistry("https://example.invalid")

        async def fake_get(name: str) -> SkillHubEntry:
            return SkillHubEntry(
                name=name,
                description="t",
                url="https://example.invalid/skill.tar.gz",
                sha256="deadbeef" * 8,  # wrong on purpose
            )

        async def fake_download(url: str, staging: Path, sha256: str | None) -> Path:
            import hashlib

            data = archive.read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            if sha256 and sha256.lower() != actual.lower():
                raise ValueError(
                    f"Archive checksum mismatch: expected {sha256}, got {actual}"
                )
            target = staging / "archive.tar.gz"
            target.write_bytes(data)
            return target

        monkeypatch.setattr(reg, "get", fake_get)
        monkeypatch.setattr(reg, "_download_archive", fake_download)

        dest = tmp_path / "dest"
        with pytest.raises(ValueError, match="checksum"):
            await reg.install("tarball-skill", dest)
        assert not (dest / "tarball-skill").exists()

    async def test_http_registry_install_success_roundtrip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid archive installs, validates, appears on disk, uninstalls cleanly."""
        import hashlib
        import tarfile

        from leagent.skills.base import SkillHubEntry
        from leagent.skills.registry import HTTPSkillRegistry

        # Build a real tar.gz archive from a valid skill directory.
        src_root = tmp_path / "src"
        _write_skill(src_root, "goodpkg")
        archive = tmp_path / "goodpkg.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(src_root / "goodpkg", arcname="goodpkg")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()

        reg = HTTPSkillRegistry("https://example.invalid")

        async def fake_get(name: str) -> SkillHubEntry:
            return SkillHubEntry(
                name=name,
                description="ok",
                url="https://example.invalid/goodpkg.tar.gz",
                sha256=digest,
            )

        async def fake_download(url: str, staging: Path, sha256: str | None) -> Path:
            import shutil

            target = staging / "archive.tar.gz"
            shutil.copy(archive, target)
            return target

        monkeypatch.setattr(reg, "get", fake_get)
        monkeypatch.setattr(reg, "_download_archive", fake_download)

        dest = tmp_path / "dest"
        dest.mkdir()
        skill = await reg.install("goodpkg", dest)

        assert skill is not None
        assert skill.name == "goodpkg"
        assert (dest / "goodpkg" / "SKILL.md").exists()
        assert skill.source == SkillSource.HUB

        # Uninstall via the registry removes the directory.
        assert await reg.uninstall("goodpkg", dest) is True
        assert not (dest / "goodpkg").exists()

    async def test_http_registry_search_via_fake_client(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from leagent.skills.base import SkillHubEntry
        from leagent.skills.registry import HTTPSkillRegistry

        class _FakeResp:
            def __init__(self, payload: Any) -> None:
                self._payload = payload
                self.status_code = 200

            def raise_for_status(self) -> None:
                return None

            def json(self) -> Any:
                return self._payload

        class _FakeClient:
            def __init__(self) -> None:
                self.captured: dict[str, Any] = {}

            async def get(self, url: str, params: dict[str, Any] | None = None) -> _FakeResp:
                self.captured["url"] = url
                self.captured["params"] = params
                return _FakeResp(
                    {
                        "skills": [
                            {"name": "alpha", "description": "A", "version": "1.0.0"},
                            {"name": "beta", "description": "B", "version": "1.1.0"},
                        ]
                    }
                )

            async def aclose(self) -> None:
                return None

        reg = HTTPSkillRegistry("https://example.invalid")
        fake = _FakeClient()
        monkeypatch.setattr(reg, "_get_client", lambda: _coro_return(fake))

        results = await reg.search(query="anything", page=2, limit=5)
        assert [e.name for e in results] == ["alpha", "beta"]
        assert isinstance(results[0], SkillHubEntry)
        assert fake.captured["params"] == {"q": "anything", "page": 2, "limit": 5}

    async def test_get_default_registry_url_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from leagent.skills.registry import get_default_registry_url

        monkeypatch.setenv(
            "LEAGENT_SKILLS_REGISTRY_URL", "https://example.test/api/"
        )
        assert get_default_registry_url() == "https://example.test/api"

        monkeypatch.delenv("LEAGENT_SKILLS_REGISTRY_URL", raising=False)


async def _coro_return(value: Any) -> Any:
    """Helper used by ``monkeypatch.setattr`` when replacing an awaitable."""
    return value


# ---------------------------------------------------------------------------
# SKILL.md parser utility
# ---------------------------------------------------------------------------


class TestMarkdownParser:
    def test_parses_valid_frontmatter(self) -> None:
        from leagent.skills.markdown_loader import parse_skill_markdown

        content = (
            "---\n"
            "name: sample\n"
            "description: example\n"
            "allowed-tools: Read Write\n"
            "---\n\n"
            "# Sample\nBody text.\n"
        )
        front, body = parse_skill_markdown(content)
        assert front["name"] == "sample"
        # kebab → snake normalisation
        assert "allowed_tools" in front
        assert "allowed-tools" not in front
        assert "Body text" in body

    def test_missing_frontmatter(self) -> None:
        from leagent.skills.markdown_loader import parse_skill_markdown

        front, body = parse_skill_markdown("no frontmatter here\n")
        assert front == {}
        assert body == "no frontmatter here"

    def test_malformed_frontmatter_returns_empty(self) -> None:
        from leagent.skills.markdown_loader import parse_skill_markdown

        content = "---\n: not valid yaml :\n---\nbody\n"
        front, body = parse_skill_markdown(content)
        # Malformed YAML → empty dict, body preserved.
        assert isinstance(front, dict)
        assert "body" in body


# ---------------------------------------------------------------------------
# CLI: migrate
# ---------------------------------------------------------------------------


class TestCliMigrate:
    def test_migrate_generates_skill_md(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`leagent skills migrate --apply` converts YAML manifests."""
        from click.testing import CliRunner

        from leagent.cli import skills_cmd

        monkeypatch.setattr(skills_cmd, "SKILLS_DIR", tmp_path)

        legacy_dir = tmp_path / "legacy-skill"
        legacy_dir.mkdir()
        (legacy_dir / "skill.yaml").write_text(
            "name: legacy-skill\n"
            "version: '0.9'\n"
            "description: A legacy skill to migrate.\n"
            "author: someone\n"
            "tags: [test, legacy]\n"
            "allowed_tools:\n"
            "  - Read\n"
            "  - Write\n"
            "instructions: |\n"
            "  # Legacy\n"
            "  Original instructions body.\n",
            encoding="utf-8",
        )

        runner = CliRunner()
        # Dry run first (no --apply): file must not yet be created.
        result = runner.invoke(skills_cmd.skills_group, ["migrate", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert not (legacy_dir / "SKILL.md").exists()

        # Apply the migration.
        result = runner.invoke(
            skills_cmd.skills_group, ["migrate", str(tmp_path), "--apply"]
        )
        assert result.exit_code == 0, result.output
        assert (legacy_dir / "SKILL.md").exists()
        assert (legacy_dir / "skill.yaml.legacy").exists()
        content = (legacy_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "name: legacy-skill" in content
        assert "A legacy skill to migrate." in content
        assert "Read Write" in content  # allowed-tools folded to space-delimited

    def test_validate_command_on_valid_skill(
        self, tmp_path: Path
    ) -> None:
        from click.testing import CliRunner

        from leagent.cli import skills_cmd

        _write_skill(tmp_path, "ok-skill")
        runner = CliRunner()
        result = runner.invoke(
            skills_cmd.skills_group, ["validate", str(tmp_path / "ok-skill")]
        )
        assert result.exit_code == 0, result.output
        assert "valid" in result.output.lower()

    def test_validate_command_rejects_invalid(self, tmp_path: Path) -> None:
        from click.testing import CliRunner

        from leagent.cli import skills_cmd

        _write_skill(tmp_path, "Bad_Name")
        runner = CliRunner()
        result = runner.invoke(
            skills_cmd.skills_group, ["validate", str(tmp_path / "Bad_Name")]
        )
        # Validation failure → non-zero exit with error details.
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# API schemas
# ---------------------------------------------------------------------------


class TestApiSchemas:
    def test_detail_mapping_drops_internal_config(self, tmp_path: Path) -> None:
        """`SkillDetail` must not expose keys starting with an underscore."""
        from unittest.mock import MagicMock

        from leagent.api.v1.skills import _detail_from_skill
        from leagent.skills.manager import SkillsManager

        manifest = SkillManifest(
            name="api-probe",
            description="d",
            license="MIT",
            compatibility="LeAgent >=1",
            metadata={"version": "2.0.0", "tags": ["x"], "category": "data"},
            allowed_tools=["Read"],
        )
        skill = Skill(
            manifest=manifest,
            source=SkillSource.LOCAL,
            path=tmp_path,
            config={"user": "Alice", "_internal": "secret"},
        )
        mgr = MagicMock(spec=SkillsManager)
        mgr.is_skill_editable = MagicMock(return_value=False)
        detail = _detail_from_skill(skill, mgr)
        assert detail.name == "api-probe"
        assert detail.license == "MIT"
        assert detail.compatibility == "LeAgent >=1"
        assert detail.allowed_tools == ["Read"]
        assert detail.tags == ["x"]
        assert detail.config == {"user": "Alice"}
        assert "_internal" not in detail.config
