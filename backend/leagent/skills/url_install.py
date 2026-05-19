"""Install a skill by downloading a zip or tar.gz from an HTTPS URL.

Reuses :func:`leagent.skills.registry._extract_archive` and the same
staging / validation pattern as :class:`HTTPSkillRegistry`.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from leagent.skills.base import Skill, SkillSource
from leagent.skills.loader import SkillLoader
from leagent.skills.registry import _extract_archive

DEFAULT_MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 5


class SkillURLError(ValueError):
    """Invalid URL, protocol, or download policy violation."""


def _require_https_url(url: str) -> None:
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise SkillURLError("Only https:// URLs are allowed for skill install from URL")
    if not parsed.netloc:
        raise SkillURLError("Invalid URL")


async def _download_archive(
    url: str,
    archive_path: Path,
    *,
    expected_sha256: str | None,
    max_bytes: int,
    timeout_s: float,
) -> None:
    import httpx

    from leagent.utils.httpx_proxy import httpx_trust_env

    digest = hashlib.sha256()
    total = 0
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s),
        follow_redirects=True,
        max_redirects=MAX_REDIRECTS,
        trust_env=httpx_trust_env(),
    ) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            with archive_path.open("wb") as fh:
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise SkillURLError(
                            f"Archive exceeds maximum size ({max_bytes} bytes)"
                        )
                    fh.write(chunk)
                    digest.update(chunk)
    if expected_sha256 and digest.hexdigest().lower() != expected_sha256.strip().lower():
        raise SkillURLError(
            f"Archive checksum mismatch: expected {expected_sha256}, got {digest.hexdigest()}"
        )


async def install_skill_from_url(
    url: str,
    dest_base: Path,
    *,
    expected_sha256: str | None = None,
    timeout_s: float = 120.0,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> Skill:
    """Download, extract, validate, and move a skill into *dest_base*.

    *dest_base* is the same directory the hub installer uses
    (e.g. ``~/.leagent/skills`` or ``.../skills``).
    """
    _require_https_url(url)

    dest_base.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix="leagent-skill-url-"))
    try:
        # Neutral filename — format is detected via magic bytes after download
        # (URLs often omit .zip/.tar.gz or use query strings).
        archive_path = staging / "archive.bin"

        await _download_archive(
            url,
            archive_path,
            expected_sha256=expected_sha256,
            max_bytes=max_archive_bytes,
            timeout_s=timeout_s,
        )

        extracted_root = staging / "extracted"
        try:
            skill_dir = _extract_archive(archive_path, extracted_root)
        except ValueError as exc:
            raise SkillURLError(str(exc)) from exc

        loader = SkillLoader(skill_dir.parent, source=SkillSource.HUB)
        await loader.load_all()
        if not loader.loaded_skills:
            raise SkillURLError("Archive did not contain a valid skill")
        name = next(iter(loader.loaded_skills.keys()))
        loaded = loader.get_skill(name)
        if loaded is None:
            raise SkillURLError(f"Failed to load skill from archive (name: {name!r})")

        final_dir = dest_base / name

        if final_dir.exists():
            backup = final_dir.with_suffix(".old")
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            final_dir.rename(backup)
            try:
                shutil.move(str(skill_dir), str(final_dir))
            except Exception:
                backup.rename(final_dir)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        else:
            shutil.move(str(skill_dir), str(final_dir))

        final_loader = SkillLoader(final_dir.parent, source=SkillSource.HUB)
        await final_loader.load_all()
        out = final_loader.get_skill(name)
        if out is None:
            raise SkillURLError("Failed to reload skill after install")
        return out
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _archive_size_ok(archive_path: Path, max_bytes: int) -> None:
    try:
        sz = archive_path.stat().st_size
    except OSError as exc:
        raise SkillURLError(f"Cannot read archive: {exc}") from exc
    if sz > max_bytes:
        raise SkillURLError(f"Archive exceeds maximum size ({max_bytes} bytes)")


async def install_skill_from_archive_path(
    archive_path: Path,
    dest_base: Path,
    *,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
) -> Skill:
    """Install from an existing ``.zip`` or ``.tar.gz`` on disk (same validation as URL install)."""
    archive_path = archive_path.expanduser().resolve()
    if not archive_path.is_file():
        raise SkillURLError(f"Archive not found: {archive_path}")

    _archive_size_ok(archive_path, max_archive_bytes)

    dest_base.mkdir(parents=True, exist_ok=True)

    staging = Path(tempfile.mkdtemp(prefix="leagent-skill-archive-"))
    try:
        extracted_root = staging / "extracted"
        try:
            skill_dir = _extract_archive(archive_path, extracted_root)
        except ValueError as exc:
            raise SkillURLError(str(exc)) from exc

        loader = SkillLoader(skill_dir.parent, source=SkillSource.HUB)
        await loader.load_all()
        if not loader.loaded_skills:
            raise SkillURLError("Archive did not contain a valid skill")
        name = next(iter(loader.loaded_skills.keys()))
        loaded = loader.get_skill(name)
        if loaded is None:
            raise SkillURLError(f"Failed to load skill from archive (name: {name!r})")

        final_dir = dest_base / name

        if final_dir.exists():
            backup = final_dir.with_suffix(".old")
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            final_dir.rename(backup)
            try:
                shutil.move(str(skill_dir), str(final_dir))
            except Exception:
                backup.rename(final_dir)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        else:
            shutil.move(str(skill_dir), str(final_dir))

        final_loader = SkillLoader(final_dir.parent, source=SkillSource.HUB)
        await final_loader.load_all()
        out = final_loader.get_skill(name)
        if out is None:
            raise SkillURLError("Failed to reload skill after install")
        return out
    finally:
        shutil.rmtree(staging, ignore_errors=True)
