"""Tests for install_skill and package_skill tools."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.test_skills import _write_skill
from leagent.tools.base import ToolContext
from leagent.tools.skills.install import InstallSkillTool
from leagent.tools.skills.package_skill import PackageSkillTool


@pytest.mark.asyncio
async def test_install_skill_url_mocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from leagent.skills.manager import SkillsManager
    from leagent.skills import url_install as url_install_mod

    pack = tmp_path / "pack"
    pack.mkdir()
    _write_skill(pack, "tool-url-skill")
    arch = shutil.make_archive(str(pack / "bundle"), "zip", root_dir=pack, base_dir="tool-url-skill")
    zpath = Path(arch)

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
    await mgr.load_all()

    async def fake_resolve() -> Any:
        return mgr

    monkeypatch.setattr(
        "leagent.tools.skills.resolve_skills_manager",
        fake_resolve,
    )

    tool = InstallSkillTool()
    ctx = ToolContext(user_id="u", session_id="s", extra={})
    result = await tool.execute(
        {"source_type": "url", "url": "https://example.com/s.zip"},
        ctx,
    )
    assert result["ok"] is True
    assert result["skill"]["name"] == "tool-url-skill"


@pytest.mark.asyncio
async def test_package_skill_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "leagent.file.sandbox._get_allowed_roots",
        lambda: (tmp_path.resolve(),),
    )

    skill_root = _write_skill(tmp_path, "pkg-skill")
    tool = PackageSkillTool()
    ctx = ToolContext(
        user_id="u",
        session_id="s",
        temp_dir=str(tmp_path),
        extra={"request_id": "r1"},
    )
    result = await tool.execute(
        {"skill_directory": str(skill_root)},
        ctx,
    )
    assert result["ok"] is True
    out = Path(result["output_path"])
    assert out.exists()
    assert out.stat().st_size > 0


@pytest.mark.asyncio
async def test_install_skill_uploaded_archive_tool_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve uploaded zip via attachment path."""
    import shutil

    from leagent.skills.manager import SkillsManager

    pack = tmp_path / "pack"
    pack.mkdir()
    _write_skill(pack, "up-skill")
    zpath = shutil.make_archive(str(pack / "bundle"), "zip", root_dir=pack, base_dir="up-skill")

    attach_name = f"{uuid.uuid4()}_myskill.zip"
    attach_path = tmp_path / attach_name
    shutil.copy(zpath, attach_path)

    mgr = SkillsManager(
        skills_dir=tmp_path / "udir",
        load_builtin=False,
        enable_hot_reload=False,
        include_interop_roots=False,
    )
    await mgr.load_all()

    async def fake_resolve() -> Any:
        return mgr

    monkeypatch.setattr(
        "leagent.tools.skills.resolve_skills_manager",
        fake_resolve,
    )
    monkeypatch.setattr(
        "leagent.file.sandbox._get_allowed_roots",
        lambda: (tmp_path.resolve(),),
    )

    tool = InstallSkillTool()
    ctx = ToolContext(
        user_id="u1",
        session_id=str(uuid.uuid4()),
        extra={
            "request_id": "t1",
            "attachments": (str(attach_path),),
        },
    )
    result = await tool.execute(
        {"source_type": "uploaded_archive", "file_id": str(attach_path)},
        ctx,
    )
    assert result.get("ok") is True
    assert result.get("skill", {}).get("name") == "up-skill"
