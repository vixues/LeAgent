"""Pluggable skill registry.

The open spec leaves the distribution mechanism to implementations;
this module ships a protocol (:class:`SkillRegistry`) plus two
implementations:

- :class:`DisabledRegistry` — the default when no URL is configured.
  Every method raises :class:`RegistryNotConfiguredError`.
- :class:`HTTPSkillRegistry` — talks to any HTTP endpoint that follows
  the simple contract documented below. The endpoint is configurable
  via the ``LEAGENT_SKILLS_REGISTRY_URL`` environment variable or the
  ``skills.registry.url`` key in ``$LEAGENT_HOME/config.yaml``.

HTTP contract
-------------

- ``GET {base}/skills/search?q=&category=&page=&limit=`` — returns JSON
  ``{"skills": [SkillHubEntry, ...]}``.
- ``GET {base}/skills/{name}`` — returns a single ``SkillHubEntry``.
- Each entry's ``url`` field points to a tar.gz or zip archive. An
  optional ``sha256`` field carries a hex digest the installer verifies
  before extraction.

Install flow (atomic):

1. Download to a temporary file.
2. Validate SHA-256 when provided; abort on mismatch.
3. Extract into a temporary staging directory.
4. Run :class:`SkillLoader` validation on the extracted skill.
5. On success, move staging → destination (replacing any prior copy).
6. On failure, remove the staging directory and leave the existing
   install untouched.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Literal, Protocol

import structlog

from leagent.skills.base import Skill, SkillHubEntry, SkillSource
from leagent.skills.loader import SkillLoader

logger = structlog.get_logger(__name__)


class RegistryNotConfiguredError(RuntimeError):
    """Raised when the manager is asked to use a registry but none is set."""


class SkillRegistry(Protocol):
    """Contract every registry implementation must satisfy."""

    async def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[SkillHubEntry]:
        ...

    async def get(self, name: str) -> SkillHubEntry | None:
        ...

    async def install(self, name: str, dest_base: Path) -> Skill | None:
        ...

    async def uninstall(self, name: str, skills_dir: Path) -> bool:
        ...

    async def aclose(self) -> None:
        ...


# ---------------------------------------------------------------------------
# Disabled
# ---------------------------------------------------------------------------


class DisabledRegistry:
    """Placeholder used when no registry URL is configured."""

    async def search(self, **_kwargs: Any) -> list[SkillHubEntry]:
        return []

    async def get(self, name: str) -> SkillHubEntry | None:
        return None

    async def install(self, name: str, dest_base: Path) -> Skill | None:
        raise RegistryNotConfiguredError(
            "No skills registry is configured. Set LEAGENT_SKILLS_REGISTRY_URL "
            "or add 'skills.registry.url' to $LEAGENT_HOME/config.yaml."
        )

    async def uninstall(self, name: str, skills_dir: Path) -> bool:
        # Uninstall doesn't need a registry — fall back to local removal.
        target = skills_dir / name
        if not target.exists():
            return False
        try:
            shutil.rmtree(target)
        except OSError as exc:
            logger.warning("skill_local_uninstall_failed", name=name, error=str(exc))
            return False
        return True

    async def aclose(self) -> None:
        return None


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


class HTTPSkillRegistry:
    """Registry backed by a JSON HTTP endpoint."""

    def __init__(self, base_url: str, *, timeout_s: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import httpx

            from leagent.utils.httpx_proxy import httpx_trust_env

            self._client = httpx.AsyncClient(
                timeout=self._timeout_s,
                follow_redirects=True,
                trust_env=httpx_trust_env(),
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[SkillHubEntry]:
        import httpx

        client = await self._get_client()
        params: dict[str, Any] = {"q": query, "page": page, "limit": limit}
        if category:
            params["category"] = category
        try:
            resp = await client.get(f"{self._base_url}/skills/search", params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("registry_search_failed", url=self._base_url, error=str(exc))
            return []
        data = resp.json()
        entries = data.get("skills", []) if isinstance(data, dict) else data
        return [SkillHubEntry.from_dict(entry) for entry in entries if isinstance(entry, dict)]

    async def get(self, name: str) -> SkillHubEntry | None:
        import httpx

        client = await self._get_client()
        try:
            resp = await client.get(f"{self._base_url}/skills/{name}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("registry_get_failed", name=name, error=str(exc))
            return None
        data = resp.json()
        if not isinstance(data, dict):
            return None
        return SkillHubEntry.from_dict(data)

    async def install(self, name: str, dest_base: Path) -> Skill | None:
        entry = await self.get(name)
        if not entry:
            raise FileNotFoundError(f"Skill '{name}' not found in registry")
        if not entry.url:
            raise ValueError(f"Registry entry for '{name}' has no download URL")

        dest_base.mkdir(parents=True, exist_ok=True)
        final_dir = dest_base / name

        staging = Path(tempfile.mkdtemp(prefix=f"leagent-skill-{name}-"))
        try:
            archive_path = await self._download_archive(entry.url, staging, entry.sha256)
            skill_dir = _extract_archive(archive_path, staging / "extracted")

            # Validate the extracted skill before committing it.
            loader = SkillLoader(skill_dir.parent, source=SkillSource.HUB)
            await loader.load_all()
            loaded = loader.get_skill(name)
            if loaded is None:
                raise ValueError(
                    f"Extracted archive does not contain a valid skill named '{name}'"
                )

            # Atomic swap.
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
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        # Reload from its final location so the returned Skill has the
        # correct ``path`` and ``source=HUB`` attribution.
        final_loader = SkillLoader(final_dir.parent, source=SkillSource.HUB)
        await final_loader.load_all()
        return final_loader.get_skill(name)

    async def uninstall(self, name: str, skills_dir: Path) -> bool:
        target = skills_dir / name
        if not target.exists():
            return False
        try:
            shutil.rmtree(target)
        except OSError as exc:
            logger.warning("skill_uninstall_rmtree_failed", name=name, error=str(exc))
            return False
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _download_archive(self, url: str, staging: Path, sha256: str | None) -> Path:
        import httpx

        client = await self._get_client()
        suffix = ".tar.gz" if url.endswith((".tar.gz", ".tgz")) else ".zip"
        archive_path = staging / f"archive{suffix}"

        digest = hashlib.sha256()
        with archive_path.open("wb") as fh:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        fh.write(chunk)
                        digest.update(chunk)

        actual = digest.hexdigest()
        if sha256 and sha256.lower() != actual.lower():
            raise ValueError(
                f"Archive checksum mismatch: expected {sha256}, got {actual}"
            )
        return archive_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def archive_magic_kind(path: Path) -> Literal["zip", "gzip_tar"]:
    """Detect zip vs gzip-compressed tar from file contents (not the filename).

    URL installs often omit ``.zip`` / ``.tar.gz`` in the path (query strings,
    CDNs). Using magic bytes avoids ``zipfile`` failing with "not a zip file"
    when the payload is actually ``.tar.gz``.
    """
    try:
        raw = path.read_bytes()[:512]
    except OSError as exc:
        raise ValueError(f"Cannot read archive: {exc}") from exc
    buf = raw.lstrip()
    if not buf:
        raise ValueError("Downloaded file is empty")
    # HTML / JSON error pages from CDNs or GitHub web URLs.
    if buf[:1] == b"<" or buf[:5].lower().startswith(b"<!doc"):
        raise ValueError(
            "Download looks like HTML, not an archive. Use a direct https link "
            "to a raw .zip or .tar.gz file (not a repository or release HTML page)."
        )
    if buf[:4] == b"{\"" or buf[:2] == b'{"':
        raise ValueError(
            "Download looks like JSON, not an archive. Use a direct link to a .zip or .tar.gz file."
        )
    if len(buf) >= 4 and buf[:2] == b"PK":
        return "zip"
    if len(buf) >= 2 and buf[0] == 0x1F and buf[1] == 0x8B:
        return "gzip_tar"
    raise ValueError(
        "File is not a zip or gzip (.tar.gz) archive. "
        "Ensure the URL returns a raw archive body over HTTPS."
    )


def _extract_archive(archive_path: Path, dest: Path) -> Path:
    """Extract the archive and return the path of the skill directory.

    The archive is expected to contain a single top-level directory.
    """
    dest.mkdir(parents=True, exist_ok=True)
    kind = archive_magic_kind(archive_path)
    if kind == "zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            _safe_extract_zip(zf, dest)
    else:
        with tarfile.open(archive_path, "r:gz") as tf:
            _safe_extract_tar(tf, dest)

    entries = [p for p in dest.iterdir() if p.is_dir()]
    if not entries:
        raise ValueError("Archive did not contain a skill directory")
    return entries[0]


def _safe_extract_tar(tf: tarfile.TarFile, dest: Path) -> None:
    dest_r = dest.resolve()
    for member in tf.getmembers():
        target = (dest / member.name).resolve()
        if os.path.commonpath([str(dest_r), str(target)]) != str(dest_r):
            raise ValueError(f"Refusing to extract outside target dir: {member.name}")
    tf.extractall(dest)  # noqa: S202 — validated above


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    dest_r = dest.resolve()
    for name in zf.namelist():
        target = (dest / name).resolve()
        if os.path.commonpath([str(dest_r), str(target)]) != str(dest_r):
            raise ValueError(f"Refusing to extract outside target dir: {name}")
    zf.extractall(dest)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def get_default_registry_url() -> str | None:
    """Resolve the active registry URL.

    Order of precedence: environment variable wins so operators can
    override per-process; otherwise the value from the user's config
    file is used.
    """
    env_url = os.environ.get("LEAGENT_SKILLS_REGISTRY_URL")
    if env_url:
        return env_url.rstrip("/") or None

    try:
        import yaml

        from leagent.config.constants import CONFIG_PATH

        if CONFIG_PATH.exists():
            data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
            skills_cfg = data.get("skills") or {}
            if isinstance(skills_cfg, dict):
                registry_cfg = skills_cfg.get("registry") or {}
                if isinstance(registry_cfg, dict):
                    url = registry_cfg.get("url")
                    if isinstance(url, str) and url.strip():
                        return url.strip().rstrip("/")
    except Exception:  # noqa: BLE001
        return None
    return None
