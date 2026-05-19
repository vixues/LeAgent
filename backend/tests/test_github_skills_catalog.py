"""Tests for GitHub monorepo skill catalog and hub merge."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leagent.skills.base import SkillHubEntry
from leagent.skills.github_monorepo_catalog import GitHubMonorepoCatalog, reset_github_monorepo_catalog
from leagent.skills.manager import SkillsManager


@pytest.fixture(autouse=True)
def _reset_catalog() -> None:
    reset_github_monorepo_catalog()
    yield
    reset_github_monorepo_catalog()


@pytest.mark.asyncio
async def test_search_hub_merges_registry_and_github() -> None:
    reg_entries = [
        SkillHubEntry(name="alpha", description="a", category="general"),
    ]
    gh_entries = [
        SkillHubEntry(name="beta", description="b", category="github-catalog"),
    ]

    mgr = SkillsManager(skills_dir=Path("/tmp/leagent-skills-merge-test"))
    mock_reg = MagicMock()
    mock_reg.search = AsyncMock(return_value=reg_entries)
    mock_reg.get = AsyncMock(return_value=None)
    mock_reg.install = AsyncMock()
    mock_reg.aclose = AsyncMock()
    mgr._registry = mock_reg  # noqa: SLF001

    mock_gh = MagicMock()
    mock_gh.search_all_matching = AsyncMock(return_value=gh_entries)

    with patch(
        "leagent.skills.github_monorepo_catalog.get_github_monorepo_catalog",
        return_value=mock_gh,
    ):
        out = await mgr.search_hub(query="", page=1, limit=20)

    names = [e.name for e in out]
    assert "alpha" in names and "beta" in names
    mock_reg.search.assert_awaited_once()
    mock_gh.search_all_matching.assert_awaited_once()


@pytest.mark.asyncio
async def test_search_hub_registry_wins_duplicate_name() -> None:
    reg_entries = [
        SkillHubEntry(name="dup", description="from-registry", category="general"),
    ]
    gh_entries = [
        SkillHubEntry(name="dup", description="from-github", category="github-catalog"),
    ]

    mgr = SkillsManager(skills_dir=Path("/tmp/leagent-skills-dedupe-test"))
    mock_reg = MagicMock()
    mock_reg.search = AsyncMock(return_value=reg_entries)
    mock_reg.get = AsyncMock(return_value=None)
    mock_reg.aclose = AsyncMock()
    mgr._registry = mock_reg  # noqa: SLF001

    mock_gh = MagicMock()
    mock_gh.search_all_matching = AsyncMock(return_value=gh_entries)

    with patch(
        "leagent.skills.github_monorepo_catalog.get_github_monorepo_catalog",
        return_value=mock_gh,
    ):
        out = await mgr.search_hub(query="", page=1, limit=20)

    dup = [e for e in out if e.name == "dup"]
    assert len(dup) == 1
    assert dup[0].description == "from-registry"


@pytest.mark.asyncio
async def test_github_catalog_install_from_tarball(tmp_path: Path) -> None:
    """Tarball layout matches GitHub codeload (single top-level dir / skills / name / SKILL.md)."""
    skill_md = b"---\nname: my-skill\ndescription: test skill\n---\nbody\n"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo(name="demo-repo-abcdef/skills/my-skill/SKILL.md")
        ti.size = len(skill_md)
        tf.addfile(ti, io.BytesIO(skill_md))
    tarball_bytes = buf.getvalue()

    cat = GitHubMonorepoCatalog(
        owner="demo",
        repo="skills",
        ref="main",
        skills_path="skills",
        enabled=True,
    )

    async def fake_list() -> list[str]:
        return ["my-skill"]

    async def fake_get(self: GitHubMonorepoCatalog, _name: str) -> SkillHubEntry:
        return SkillHubEntry(
            name="my-skill",
            description="test skill",
            category="github-catalog",
        )

    class _Resp:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    class _Inner:
        async def get(self, url: str, headers: dict[str, str] | None = None) -> _Resp:
            assert "codeload.github.com" in url
            return _Resp(tarball_bytes)

    class _FakeAC:
        async def __aenter__(self) -> _Inner:
            return _Inner()

        async def __aexit__(self, *args: object) -> None:
            return None

    with (
        patch.object(GitHubMonorepoCatalog, "_list_directory_names", fake_list),
        patch.object(GitHubMonorepoCatalog, "get", fake_get),
        patch("httpx.AsyncClient", side_effect=lambda **kwargs: _FakeAC()),
    ):
        dest_base = tmp_path / "skills_out"
        dest_base.mkdir(parents=True, exist_ok=True)
        skill = await cat.install("my-skill", dest_base)

    assert skill is not None
    assert skill.name == "my-skill"
    assert (dest_base / "my-skill" / "SKILL.md").is_file()


@pytest.mark.asyncio
async def test_install_from_hub_prefers_registry_when_present(tmp_path: Path) -> None:
    from leagent.skills.base import Skill

    mock_skill = MagicMock(spec=Skill)
    mock_skill.name = "pack"

    root = tmp_path / "hub_install"
    root.mkdir(parents=True, exist_ok=True)
    mgr = SkillsManager(skills_dir=root)

    mock_reg = MagicMock()
    mock_reg.get = AsyncMock(
        return_value=SkillHubEntry(name="pack", description="x", url="https://example.com/a.zip")
    )
    mock_reg.install = AsyncMock(return_value=mock_skill)
    mock_reg.aclose = AsyncMock()
    mgr._registry = mock_reg  # noqa: SLF001

    mock_gh = MagicMock()
    mock_gh.install = AsyncMock(return_value=None)

    with patch(
        "leagent.skills.github_monorepo_catalog.get_github_monorepo_catalog",
        return_value=mock_gh,
    ):
        out = await mgr.install_from_hub("pack")

    assert out is mock_skill
    mock_gh.install.assert_not_called()
