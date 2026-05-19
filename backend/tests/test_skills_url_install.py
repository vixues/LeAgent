"""Tests for install-from-URL and POST /skills/install/url."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tests.test_skills import _write_skill


def _make_skill_zip(pack_dir: Path, name: str) -> Path:
    """Create a zip with a single top-level folder *name*/ (not under *pack_dir* as a skill root)."""
    _write_skill(pack_dir, name)
    arch = shutil.make_archive(str(pack_dir / "bundle"), "zip", root_dir=pack_dir, base_dir=name)
    return Path(arch)


@pytest.mark.asyncio
class TestInstallSkillFromUrl:
    async def test_manager_installs_from_https_mocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills import url_install as url_install_mod

        pack = tmp_path / "pack"
        pack.mkdir()
        zpath = _make_skill_zip(pack, "url-skill")

        async def fake_download(
            url: str, archive_path: Path, **kwargs: Any
        ) -> None:  # noqa: ARG001
            shutil.copy(zpath, archive_path)

        monkeypatch.setattr(url_install_mod, "_download_archive", fake_download)

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        assert await mgr.load_all() == 0

        skill = await mgr.install_from_url("https://example.com/skill.zip")
        assert skill is not None
        assert skill.name == "url-skill"
        assert (tmp_path / "skills" / "url-skill" / "SKILL.md").is_file()
        assert mgr.get_skill("url-skill") is not None

    async def test_install_rejects_non_https(self, tmp_path: Path) -> None:
        from leagent.skills.manager import SkillsManager
        from leagent.skills.url_install import SkillURLError

        mgr = SkillsManager(
            skills_dir=tmp_path,
            load_builtin=False,
            enable_hot_reload=False,
            include_interop_roots=False,
        )
        with pytest.raises(SkillURLError, match="https"):
            await mgr.install_from_url("http://example.com/bad.zip")


def test_post_install_url_api(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_user: dict[str, Any],
    test_settings: Any,
) -> None:
    from leagent.api.v1 import skills as skills_api
    from leagent.services.auth import AuthService
    from leagent.skills.manager import SkillsManager
    from leagent.skills import url_install as url_install_mod

    pack = tmp_path / "pack"
    pack.mkdir()
    zpath = _make_skill_zip(pack, "api-url-skill")

    async def fake_download(url: str, archive_path: Path, **kwargs: Any) -> None:  # noqa: ARG001
        shutil.copy(zpath, archive_path)

    monkeypatch.setattr(url_install_mod, "_download_archive", fake_download)

    mgr = SkillsManager(
        skills_dir=tmp_path,
        load_builtin=False,
        enable_hot_reload=False,
        include_interop_roots=False,
    )
    import asyncio

    asyncio.run(mgr.load_all())
    monkeypatch.setattr(skills_api, "get_skills_manager", lambda: mgr)

    auth = AuthService(test_settings)
    token = auth.create_access_token(UUID(test_user["user_id"]))
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(
        "/api/v1/skills/install/url",
        json={"url": "https://example.com/x.zip"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "api-url-skill"

    bad = client.post(
        "/api/v1/skills/install/url",
        json={"url": "http://insecure.example.com/x.zip"},
        headers=headers,
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_install_skill_from_archive_path(tmp_path: Path) -> None:
    from leagent.skills.url_install import install_skill_from_archive_path

    pack = tmp_path / "pack"
    pack.mkdir()
    zpath = _make_skill_zip(pack, "local-arch-skill")
    dest = tmp_path / "dest"
    dest.mkdir()

    sk = await install_skill_from_archive_path(zpath, dest)
    assert sk.name == "local-arch-skill"
    assert (dest / "local-arch-skill" / "SKILL.md").is_file()
