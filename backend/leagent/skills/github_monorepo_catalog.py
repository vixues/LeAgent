"""Discover and install skills from a GitHub monorepo (folder per skill + SKILL.md).

Listing + SKILL.md metadata prefer one ``codeload.github.com`` tarball per catalog key,
extracted under ``CACHE_DIR/github-skills-hub/``, refreshed at most once per TTL — avoiding
GitHub REST ``/contents`` rate limits. Falls back to REST + ``raw.githubusercontent.com``
only if tarball download/extract fails.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import shutil
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import structlog

from leagent.config.constants import CACHE_DIR
from leagent.skills.base import Skill, SkillHubEntry
from leagent.skills.local_install import install_skill_from_workspace_directory
from leagent.skills.markdown_loader import parse_skill_markdown

logger = structlog.get_logger(__name__)

USER_AGENT = "LeAgent/1.2.0 (+https://github.com/vixues/LeAgent) skills-hub"

# Match frontend skills hub persistence (~24h): avoid hammering GitHub REST / raw on every page load.
GITHUB_HUB_CACHE_TTL_S = 86400.0
_MAX_MERGED_FETCH = 2000
_RAW_CONCURRENCY = 4

# Shared across singleton + ephemeral catalog instances (same owner/repo/ref/path).
_SHARED_DIR_CACHE: dict[str, tuple[list[str], float]] = {}
_SHARED_DIR_LAST_GOOD: dict[str, list[str]] = {}
# SKILL.md metadata: shared so per-request GitHubMonorepoCatalog instances still hit cache.
_SHARED_META_CACHE: dict[str, tuple[SkillHubEntry, float]] = {}
_RATE_LIMIT_HINT_LOGGED = False
# One tarball download per catalog key; reused across workers until TTL (see disk cache under CACHE_DIR).
_HYDRATE_LOCKS: dict[str, asyncio.Lock] = {}

HUB_DISK_SUBDIR = "github-skills-hub"


def _dir_cache_key(owner: str, repo: str, ref: str, skills_path: str) -> str:
    return f"{owner.lower().strip()}/{repo.lower().strip()}@{ref.strip()}:{skills_path.strip()}"


def _meta_cache_key(owner: str, repo: str, ref: str, skills_path: str, skill_name: str) -> str:
    return f"{_dir_cache_key(owner, repo, ref, skills_path)}::{skill_name.strip().lower()}"


def _hub_disk_cache_path(catalog_key: str) -> Path:
    slug = hashlib.sha256(catalog_key.encode("utf-8")).hexdigest()[:24]
    return CACHE_DIR / HUB_DISK_SUBDIR / slug


def _get_hydrate_lock(catalog_key: str) -> asyncio.Lock:
    lock = _HYDRATE_LOCKS.get(catalog_key)
    if lock is None:
        lock = asyncio.Lock()
        _HYDRATE_LOCKS[catalog_key] = lock
    return lock


def _resolve_skills_root_from_extract(extract_root: Path, skills_path: str) -> Path | None:
    top_levels = [p for p in extract_root.iterdir() if p.is_dir()]
    if len(top_levels) != 1:
        logger.warning("github_tar_extract_bad_top_level", count=len(top_levels))
        return None
    base = top_levels[0]
    rel = skills_path.strip().strip("/")
    if not rel:
        return None
    sr: Path = base
    for part in rel.split("/"):
        if not part:
            continue
        sr = sr / part
    sr = sr.resolve()
    er = extract_root.resolve()
    try:
        sr.relative_to(er)
    except ValueError:
        return None
    return sr if sr.is_dir() else None


def _safe_extract_tar_gz(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        root_r = dest.resolve()
        for m in tf.getmembers():
            target = (dest / m.name).resolve()
            if os.path.commonpath([str(root_r), str(target)]) != str(root_r):
                raise ValueError(f"Unsafe tar member: {m.name}")
        tf.extractall(dest)


@dataclass(frozen=True)
class GitHubCatalogOverride:
    """Per-request GitHub monorepo source (UI-selected repo / ref / skills subtree)."""

    owner: str
    repo: str
    ref: str = "main"
    skills_path: str = "skills"


def _github_token() -> str | None:
    for key in ("LEAGENT_GITHUB_TOKEN", "GITHUB_TOKEN"):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    return None


class GitHubMonorepoCatalog:
    """Skill hub backed by ``owner/repo`` at ``skills_path/<name>/SKILL.md``."""

    def __init__(
        self,
        *,
        owner: str,
        repo: str,
        ref: str,
        skills_path: str,
        enabled: bool = True,
    ) -> None:
        self._owner = owner.strip()
        self._repo = repo.strip()
        self._ref = ref.strip() or "main"
        self._skills_path = skills_path.strip().strip("/")
        self._enabled = enabled
        self._token = _github_token()
        self._client: Any = None

        self._dir_names_cache: tuple[list[str], float] = ([], 0.0)
        self._meta_cache: dict[str, tuple[SkillHubEntry, float]] = {}

    def is_enabled(self) -> bool:
        return self._enabled and bool(self._owner and self._repo)

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import httpx

            from leagent.utils.httpx_proxy import httpx_trust_env

            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"

            self._client = httpx.AsyncClient(
                base_url="https://api.github.com",
                timeout=60.0,
                follow_redirects=True,
                headers=headers,
                trust_env=httpx_trust_env(),
            )
        return self._client

    def _is_github_rate_limited_response(self, resp: Any) -> bool:
        """403 is used for quota/abuse limits as well as 429."""
        if resp.status_code == 429:
            return True
        if resp.status_code != 403:
            return False
        remaining = (resp.headers.get("X-RateLimit-Remaining") or "").strip()
        if remaining == "0":
            return True
        try:
            body = (resp.text or "")[:500].lower()
        except Exception:  # noqa: BLE001
            body = ""
        return "rate limit" in body or "api rate limit exceeded" in body

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        import httpx

        client = await self._get_client()
        delay = 0.5
        last_exc: Exception | None = None
        for attempt in range(6):
            try:
                resp = await client.request(method, url, **kwargs)
                if self._is_github_rate_limited_response(resp):
                    ra = resp.headers.get("Retry-After")
                    try:
                        wait_s = float(ra) if ra not in (None, "") else delay
                    except (TypeError, ValueError):
                        wait_s = delay
                    wait_s += random.uniform(0, 0.35)
                    logger.warning(
                        "github_rate_limited",
                        status=resp.status_code,
                        wait_s=round(wait_s, 2),
                        attempt=attempt,
                        has_token=bool(self._token),
                    )
                    await asyncio.sleep(min(wait_s, 120.0))
                    delay = min(delay * 2, 45.0)
                    continue
                if resp.status_code >= 500:
                    await asyncio.sleep(delay + random.uniform(0, 0.2))
                    delay = min(delay * 2, 30.0)
                    continue
                return resp
            except httpx.HTTPError as exc:
                last_exc = exc
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30.0)
        if last_exc:
            raise last_exc
        raise RuntimeError("GitHub request failed")

    def _load_extract_into_caches(self, extract_root: Path, catalog_key: str, now: float) -> bool:
        sr = _resolve_skills_root_from_extract(extract_root, self._skills_path)
        if sr is None:
            return False
        names: list[str] = []
        for child in sorted(sr.iterdir()):
            if not child.is_dir() or not (child / "SKILL.md").is_file():
                continue
            names.append(child.name)
        names.sort()
        for name in names:
            raw = (sr / name / "SKILL.md").read_text(encoding="utf-8", errors="replace")
            entry = self._entry_from_skill_md(name, raw)
            mk = _meta_cache_key(self._owner, self._repo, self._ref, self._skills_path, name)
            self._meta_cache[name] = (entry, now)
            _SHARED_META_CACHE[mk] = (entry, now)
        self._dir_names_cache = (names, now)
        _SHARED_DIR_CACHE[catalog_key] = (names, now)
        _SHARED_DIR_LAST_GOOD[catalog_key] = list(names)
        return True

    async def _download_repo_tarball_to(self, dest_file: Path) -> None:
        import httpx

        from leagent.utils.httpx_proxy import httpx_trust_env

        tar_url = f"https://codeload.github.com/{self._owner}/{self._repo}/tar.gz/{quote(self._ref)}"
        headers = {"User-Agent": USER_AGENT}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, trust_env=httpx_trust_env()) as dl:
            resp = await dl.get(tar_url, headers=headers)
            resp.raise_for_status()
            dest_file.write_bytes(resp.content)

    async def _refresh_catalog_from_tarball(self, catalog_key: str) -> bool:
        """Fetch repo archive once (codeload), extract + scan SKILL.md; disk + memory cache for TTL."""
        async with _get_hydrate_lock(catalog_key):
            now_mono = time.monotonic()
            warm = _SHARED_DIR_CACHE.get(catalog_key)
            if warm is not None and now_mono - warm[1] < GITHUB_HUB_CACHE_TTL_S:
                return True

            cache_root = _hub_disk_cache_path(catalog_key)
            manifest_path = cache_root / "manifest.json"
            extract_path = cache_root / "extract"

            if manifest_path.is_file() and extract_path.is_dir():
                try:
                    meta = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if meta.get("catalog_key") != catalog_key:
                        raise ValueError("catalog_key mismatch")
                    saved_at = float(meta.get("saved_at", 0))
                    if time.time() - saved_at < GITHUB_HUB_CACHE_TTL_S:
                        ok = await asyncio.to_thread(
                            self._load_extract_into_caches,
                            extract_path,
                            catalog_key,
                            time.monotonic(),
                        )
                        if ok:
                            logger.info("github_catalog_hub_disk_cache_hit", key=catalog_key)
                            return True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("github_hub_disk_cache_read_failed", key=catalog_key, error=str(exc))
                    shutil.rmtree(cache_root, ignore_errors=True)

            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                shutil.rmtree(cache_root, ignore_errors=True)
                cache_root.mkdir(parents=True, exist_ok=True)
                extract_path.mkdir(parents=True, exist_ok=True)

                fd, tmp_path = tempfile.mkstemp(prefix="leagent-hub-tar-", suffix=".tar.gz")
                os.close(fd)
                tar_p = Path(tmp_path)
                try:
                    await self._download_repo_tarball_to(tar_p)
                    await asyncio.to_thread(_safe_extract_tar_gz, tar_p, extract_path)
                finally:
                    tar_p.unlink(missing_ok=True)

                ok = await asyncio.to_thread(
                    self._load_extract_into_caches,
                    extract_path,
                    catalog_key,
                    time.monotonic(),
                )
                if not ok:
                    logger.warning("github_catalog_tarball_scan_failed", key=catalog_key)
                    shutil.rmtree(cache_root, ignore_errors=True)
                    return False

                manifest_path.write_text(
                    json.dumps({"saved_at": time.time(), "catalog_key": catalog_key}),
                    encoding="utf-8",
                )
                logger.info("github_catalog_tarball_cached", key=catalog_key)
                return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("github_catalog_tarball_hydrate_failed", key=catalog_key, error=str(exc))
                shutil.rmtree(cache_root, ignore_errors=True)
                return False

    async def _list_directory_names(self) -> list[str]:
        global _RATE_LIMIT_HINT_LOGGED
        key = _dir_cache_key(self._owner, self._repo, self._ref, self._skills_path)
        now = time.monotonic()

        shared = _SHARED_DIR_CACHE.get(key)
        if shared is not None and now - shared[1] < GITHUB_HUB_CACHE_TTL_S:
            return list(shared[0])

        cached, ts = self._dir_names_cache
        if cached and now - ts < GITHUB_HUB_CACHE_TTL_S:
            return list(cached)

        if await self._refresh_catalog_from_tarball(key):
            hit = _SHARED_DIR_CACHE.get(key)
            if hit is not None:
                return list(hit[0])

        path_q = quote(self._skills_path, safe="/")
        url = f"/repos/{self._owner}/{self._repo}/contents/{path_q}"
        try:
            resp = await self._request("GET", url, params={"ref": self._ref})
        except Exception as exc:  # noqa: BLE001
            logger.warning("github_directory_request_failed", key=key, error=str(exc))
            if key in _SHARED_DIR_LAST_GOOD:
                logger.warning("github_directory_using_stale_after_error", key=key)
                return list(_SHARED_DIR_LAST_GOOD[key])
            return list(cached) if cached else []

        if resp.status_code == 404:
            logger.warning("github_skills_path_missing", path=self._skills_path)
            empty: list[str] = []
            self._dir_names_cache = (empty, now)
            _SHARED_DIR_CACHE[key] = (empty, now)
            return []

        if resp.status_code >= 400:
            if self._is_github_rate_limited_response(resp) or resp.status_code == 403:
                if not self._token and not _RATE_LIMIT_HINT_LOGGED:
                    _RATE_LIMIT_HINT_LOGGED = True
                    logger.warning(
                        "github_api_quota_exceeded_hint",
                        hint="Set GITHUB_TOKEN or LEAGENT_GITHUB_TOKEN for 5k req/hr; "
                        "unauthenticated GitHub REST allows ~60 req/hr.",
                    )
                if key in _SHARED_DIR_LAST_GOOD:
                    logger.warning(
                        "github_directory_rate_limited_using_stale",
                        key=key,
                        status=resp.status_code,
                    )
                    return list(_SHARED_DIR_LAST_GOOD[key])
            try:
                resp.raise_for_status()
            except Exception:
                if key in _SHARED_DIR_LAST_GOOD:
                    return list(_SHARED_DIR_LAST_GOOD[key])
                return list(cached) if cached else []

        data = resp.json()
        if not isinstance(data, list):
            self._dir_names_cache = ([], now)
            _SHARED_DIR_CACHE[key] = ([], now)
            return []

        names = [
            item["name"]
            for item in data
            if isinstance(item, dict) and item.get("type") == "dir" and isinstance(item.get("name"), str)
        ]
        names.sort()
        self._dir_names_cache = (names, now)
        _SHARED_DIR_CACHE[key] = (names, now)
        _SHARED_DIR_LAST_GOOD[key] = list(names)
        return list(names)

    async def _fetch_skill_md_raw(self, skill_name: str) -> str:
        # Static raw host — one GET per skill metadata refresh.
        path = f"{self._skills_path}/{skill_name}/SKILL.md".strip("/")
        path_q = quote(path)
        url = f"https://raw.githubusercontent.com/{self._owner}/{self._repo}/{self._ref}/{path_q}"
        import httpx

        token = self._token
        headers = {"User-Agent": USER_AGENT}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as raw_client:
            resp = await raw_client.get(url, headers=headers)
            if resp.status_code == 404:
                return ""
            resp.raise_for_status()
            return resp.text

    def _entry_from_skill_md(self, skill_name: str, raw: str) -> SkillHubEntry:
        front, _body = parse_skill_markdown(raw)
        desc = ""
        if isinstance(front.get("description"), str):
            desc = front["description"].strip()
        ver = "1.0.0"
        if isinstance(front.get("version"), str) and front["version"].strip():
            ver = front["version"].strip()
        author = ""
        if isinstance(front.get("author"), str):
            author = front["author"].strip()
        tags: list[str] = ["github-catalog"]
        if isinstance(front.get("tags"), list):
            tags.extend(str(t) for t in front["tags"] if isinstance(t, str))
        return SkillHubEntry(
            name=skill_name,
            description=desc or f"Skill `{skill_name}` from GitHub ({self._owner}/{self._repo})",
            version=ver,
            author=author,
            category="github-catalog",
            tags=tags,
            url="",
            sha256=None,
        )

    async def _get_entry(self, skill_name: str) -> SkillHubEntry | None:
        now = time.monotonic()
        mk = _meta_cache_key(self._owner, self._repo, self._ref, self._skills_path, skill_name)

        shared_meta = _SHARED_META_CACHE.get(mk)
        if shared_meta is not None and now - shared_meta[1] < GITHUB_HUB_CACHE_TTL_S:
            return shared_meta[0]

        hit = self._meta_cache.get(skill_name)
        if hit and now - hit[1] < GITHUB_HUB_CACHE_TTL_S:
            return hit[0]

        raw = await self._fetch_skill_md_raw(skill_name)
        if not raw.strip():
            return None
        entry = self._entry_from_skill_md(skill_name, raw)
        self._meta_cache[skill_name] = (entry, now)
        _SHARED_META_CACHE[mk] = (entry, now)
        return entry

    async def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> list[SkillHubEntry]:
        all_rows = await self.search_all_matching(query=query, category=category)
        start = max(0, (page - 1) * limit)
        return all_rows[start : start + limit]

    async def search_all_matching(
        self,
        *,
        query: str = "",
        category: str | None = None,
    ) -> list[SkillHubEntry]:
        """Return up to :data:`_MAX_MERGED_FETCH` entries for hub merge (paginate after merge)."""
        if not self.is_enabled():
            return []

        if category and category.lower() not in ("github-catalog", "github", "general"):
            return []

        names = await self._list_directory_names()
        q = (query or "").strip().lower()
        if q:
            names = [n for n in names if q in n.lower()]

        capped = names[:_MAX_MERGED_FETCH]

        # Empty query: use SKILL.md from tarball cache when present; else placeholders (no raw GET per skill).
        if not q:
            mono = time.monotonic()
            rows: list[SkillHubEntry] = []
            for n in capped:
                mk = _meta_cache_key(self._owner, self._repo, self._ref, self._skills_path, n)
                sm = _SHARED_META_CACHE.get(mk)
                if sm is not None and mono - sm[1] < GITHUB_HUB_CACHE_TTL_S:
                    rows.append(sm[0])
                else:
                    rows.append(
                        SkillHubEntry(
                            name=n,
                            description=f"{self._owner}/{self._repo} @ {self._ref}",
                            version="1.0.0",
                            category="github-catalog",
                            tags=["github-catalog"],
                        )
                    )
            return rows

        sem = asyncio.Semaphore(_RAW_CONCURRENCY)
        out: list[SkillHubEntry] = []

        async def consider(n: str) -> None:
            nonlocal out
            async with sem:
                entry = await self._get_entry(n)
                if entry is None:
                    return
                if q not in entry.name.lower() and q not in entry.description.lower():
                    return
                out.append(entry)

        await asyncio.gather(*[consider(n) for n in capped])
        out.sort(key=lambda e: e.name)
        return out

    async def get(self, name: str) -> SkillHubEntry | None:
        if not self.is_enabled():
            return None
        names = await self._list_directory_names()
        if name not in names:
            return None
        return await self._get_entry(name)

    async def install(self, name: str, dest_base: Path) -> Skill | None:
        if not self.is_enabled():
            return None
        entry = await self.get(name)
        if entry is None:
            return None

        import httpx

        from leagent.utils.httpx_proxy import httpx_trust_env

        tar_url = f"https://codeload.github.com/{self._owner}/{self._repo}/tar.gz/{quote(self._ref)}"
        headers = {"User-Agent": USER_AGENT}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        fd, archive_path = tempfile.mkstemp(prefix="leagent-gh-skill-", suffix=".tar.gz")
        os.close(fd)
        path = Path(archive_path)
        try:
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True, trust_env=httpx_trust_env()) as dl:
                resp = await dl.get(tar_url, headers=headers)
                resp.raise_for_status()
                path.write_bytes(resp.content)

            extract_root = Path(tempfile.mkdtemp(prefix="leagent-gh-extract-"))
            try:
                with tarfile.open(path, "r:gz") as tf:
                    root_r = extract_root.resolve()
                    for m in tf.getmembers():
                        dest_path = (extract_root / m.name).resolve()
                        if os.path.commonpath([str(root_r), str(dest_path)]) != str(root_r):
                            raise ValueError(f"Unsafe tar member: {m.name}")
                    tf.extractall(extract_root)

                top_levels = [p for p in extract_root.iterdir() if p.is_dir()]
                if len(top_levels) != 1:
                    logger.error("github_tarball_unexpected_layout", count=len(top_levels))
                    return None
                skill_src = top_levels[0] / self._skills_path / name
                skill_src = skill_src.resolve()
                if not skill_src.is_dir() or not (skill_src / "SKILL.md").is_file():
                    logger.error("github_skill_folder_missing", path=str(skill_src))
                    return None

                skill = await install_skill_from_workspace_directory(
                    skill_src, dest_base, target_name=name
                )
                return skill
            finally:
                import shutil

                shutil.rmtree(extract_root, ignore_errors=True)
        finally:
            path.unlink(missing_ok=True)


_catalog_singleton: GitHubMonorepoCatalog | None = None


def get_github_monorepo_catalog() -> GitHubMonorepoCatalog | None:
    """Lazy singleton from application settings."""
    global _catalog_singleton
    if _catalog_singleton is None:
        from leagent.config.settings import get_settings

        s = get_settings()
        enabled = getattr(s, "skills_github_catalog_enabled", True)
        owner = (getattr(s, "skills_github_owner", "") or "").strip() or "anthropics"
        repo = (getattr(s, "skills_github_repo", "") or "").strip() or "skills"
        ref = (getattr(s, "skills_github_ref", "") or "").strip() or "main"
        skills_path = (getattr(s, "skills_github_skills_path", "") or "").strip() or "skills"

        _catalog_singleton = GitHubMonorepoCatalog(
            owner=owner,
            repo=repo,
            ref=ref,
            skills_path=skills_path,
            enabled=enabled,
        )
    if not _catalog_singleton.is_enabled():
        return None
    return _catalog_singleton


def reset_github_monorepo_catalog() -> None:
    """Testing hook."""
    global _catalog_singleton, _RATE_LIMIT_HINT_LOGGED
    _catalog_singleton = None
    _SHARED_DIR_CACHE.clear()
    _SHARED_DIR_LAST_GOOD.clear()
    _SHARED_META_CACHE.clear()
    _HYDRATE_LOCKS.clear()
    _RATE_LIMIT_HINT_LOGGED = False
    hub_disk = CACHE_DIR / HUB_DISK_SUBDIR
    if hub_disk.is_dir():
        shutil.rmtree(hub_disk, ignore_errors=True)


async def shutdown_github_monorepo_catalog() -> None:
    """Close HTTP clients if the catalog singleton was created."""
    global _catalog_singleton
    if _catalog_singleton is not None:
        await _catalog_singleton.aclose()
