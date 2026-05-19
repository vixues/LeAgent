"""Install a skill by copying a validated workspace directory into the skills tree."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from leagent.skills.base import Skill, SkillSource
from leagent.skills.loader import SkillLoader, SkillLoadError, SkillValidationError

__all__ = ["LocalSkillInstallError", "install_skill_from_workspace_directory"]


class LocalSkillInstallError(ValueError):
    """Invalid source path, copy failure, or skill validation error."""


async def install_skill_from_workspace_directory(
    source_dir: Path,
    dest_base: Path,
    *,
    target_name: str,
) -> Skill:
    """Copy *source_dir* to ``dest_base/<target_name>`` and validate with :class:`SkillLoader`.

    *target_name* must match the kebab-case directory name and the ``name`` field in ``SKILL.md``
    (see :class:`~leagent.skills.loader.SkillLoader` rules).
    """
    source_dir = source_dir.resolve()
    if not source_dir.is_dir():
        raise LocalSkillInstallError(f"Source is not a directory: {source_dir}")
    if not (source_dir / "SKILL.md").is_file():
        raise LocalSkillInstallError(f"Source has no SKILL.md: {source_dir}")

    dest_base.mkdir(parents=True, exist_ok=True)
    final_dir = dest_base / target_name

    staging = Path(tempfile.mkdtemp(prefix="leagent-skill-ws-"))
    try:
        tmp_target = staging / target_name
        shutil.copytree(source_dir, tmp_target)
        loader = SkillLoader(tmp_target.parent, source=SkillSource.LOCAL)
        try:
            await loader.load_skill(tmp_target)
        except (SkillLoadError, SkillValidationError) as exc:
            raise LocalSkillInstallError(str(exc)) from exc

        loaded = loader.get_skill(target_name)
        if loaded is None:
            raise LocalSkillInstallError("Validation loaded no skill (unexpected)")

        if final_dir.exists():
            backup = final_dir.with_suffix(".old")
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            final_dir.rename(backup)
            try:
                shutil.move(str(tmp_target), str(final_dir))
            except Exception:
                backup.rename(final_dir)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        else:
            shutil.move(str(tmp_target), str(final_dir))

        final_loader = SkillLoader(final_dir.parent, source=SkillSource.LOCAL)
        await final_loader.load_skill(final_dir)
        out = final_loader.get_skill(target_name)
        if out is None:
            raise LocalSkillInstallError("Failed to reload skill after install")
        return out
    finally:
        shutil.rmtree(staging, ignore_errors=True)
