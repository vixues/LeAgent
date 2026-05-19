"""Tests for workspace directory skill install."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_skills import _write_skill


@pytest.mark.asyncio
async def test_install_skill_from_workspace_directory(tmp_path: Path) -> None:
    from leagent.skills.local_install import install_skill_from_workspace_directory

    src_root = tmp_path / "src"
    src_root.mkdir()
    _write_skill(src_root, "ws-skill")

    dest_base = tmp_path / "skills_store"
    dest_base.mkdir()

    sk = await install_skill_from_workspace_directory(
        src_root / "ws-skill",
        dest_base,
        target_name="ws-skill",
    )
    assert sk.name == "ws-skill"
    assert (dest_base / "ws-skill" / "SKILL.md").is_file()
