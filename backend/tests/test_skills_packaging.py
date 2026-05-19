"""Tests for leagent.skills.packaging."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_skills import _write_skill


@pytest.mark.asyncio
async def test_build_skill_zip_roundtrip(tmp_path: Path) -> None:
    from leagent.skills.base import SkillSource
    from leagent.skills.loader import SkillLoader
    from leagent.skills.packaging import build_skill_zip_async
    from leagent.skills.registry import _extract_archive

    _write_skill(tmp_path, "round-skill")
    (tmp_path / "round-skill" / "note.txt").write_text("x", encoding="utf-8")

    raw = await build_skill_zip_async(tmp_path / "round-skill")
    assert raw.startswith(b"PK")

    arch = tmp_path / "out.zip"
    arch.write_bytes(raw)
    ex = tmp_path / "ex"
    skill_dir = _extract_archive(arch, ex)

    loader = SkillLoader(skill_dir.parent, source=SkillSource.LOCAL)
    await loader.load_skill(skill_dir)
    assert "round-skill" in loader.loaded_skills
    assert (skill_dir / "note.txt").read_text() == "x"


def test_build_skill_zip_rejects_invalid(tmp_path: Path) -> None:
    from leagent.skills.packaging import SkillPackageError, build_skill_zip

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: oops\n---\n", encoding="utf-8")
    with pytest.raises(SkillPackageError):
        build_skill_zip(bad)
