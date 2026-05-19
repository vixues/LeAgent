"""Build a spec-compliant .zip of a skill directory (single top-level folder)."""

from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path
from typing import Any

from leagent.skills.base import SkillSource
from leagent.skills.loader import SkillLoadError, SkillLoader, SkillValidationError

__all__ = [
    "SkillPackageError",
    "build_skill_zip",
    "build_skill_zip_async",
    "validate_skill_directory_async",
]


class SkillPackageError(ValueError):
    """Skill directory failed validation or could not be zipped."""


async def validate_skill_directory_async(skill_root: Path) -> None:
    """Validate *skill_root* with :class:`SkillLoader`."""
    skill_root = skill_root.resolve()
    if not skill_root.is_dir():
        raise SkillPackageError(f"Not a directory: {skill_root}")

    loader = SkillLoader(skill_root.parent, source=SkillSource.LOCAL)
    try:
        await loader.load_skill(skill_root)
    except (SkillLoadError, SkillValidationError) as exc:
        raise SkillPackageError(str(exc)) from exc


def _iter_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file():
            out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


async def build_skill_zip_async(skill_root: Path) -> bytes:
    """Build a ``.zip`` with top-level folder ``<skill_folder_name>/`` (Agent Skills v1.0 install layout)."""
    await validate_skill_directory_async(skill_root)
    skill_root = skill_root.resolve()
    top_name = skill_root.name

    buf = io.BytesIO()
    with zipfile.ZipFile(
        buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as zf:
        for file_path in _iter_files(skill_root):
            rel = file_path.relative_to(skill_root)
            arcname = f"{top_name}/{rel.as_posix()}"
            zf.write(file_path, arcname)

    data = buf.getvalue()
    max_bytes = 20 * 1024 * 1024
    if len(data) > max_bytes:
        raise SkillPackageError(f"Archive exceeds maximum size ({max_bytes} bytes)")
    if not data:
        raise SkillPackageError("Archive is empty")
    return data


def build_skill_zip(skill_root: Path) -> bytes:
    """Sync wrapper for scripts/CLI (uses :func:`asyncio.run`)."""
    return asyncio.run(build_skill_zip_async(skill_root))


def build_skill_zip_result(skill_root: Path) -> dict[str, Any]:
    """Return ``{ ok, zip_base64, size_bytes, error }`` for synchronous callers."""
    import base64

    try:
        raw = build_skill_zip(skill_root)
    except SkillPackageError as exc:
        return {"ok": False, "error": str(exc), "zip_base64": None, "size_bytes": 0}
    return {
        "ok": True,
        "error": None,
        "zip_base64": base64.b64encode(raw).decode("ascii"),
        "size_bytes": len(raw),
    }
