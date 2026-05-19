"""Optional robots.txt checks for user-supplied URLs (scraper / image download).

Uses a small in-memory cache per hostname. When ``robots.txt`` is missing or unreadable,
fetches are **allowed** (fail-open) so local-first workflows are not blocked by noisy hosts.
"""

from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog

from leagent.tools.web.polite_http import polite_get, public_fetch_user_agent

logger = structlog.get_logger(__name__)

_cache: dict[str, tuple[float, RobotFileParser]] = {}


def _allow_all_rules() -> list[str]:
    return ["User-agent: *", "Allow: /"]


async def assert_fetch_allowed(client: httpx.AsyncClient, url: str) -> None:
    """Raise ``ValueError`` if ``robots.txt`` disallows this URL for our User-Agent."""
    from leagent.config.settings import get_settings

    wf = get_settings().web_fetch
    if not wf.check_robots_txt or not wf.enabled:
        return

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return

    host = parsed.hostname.lower()
    now = time.time()
    ttl = max(60.0, float(wf.robots_cache_ttl_sec))
    ua = public_fetch_user_agent()

    hit = _cache.get(host)
    if hit is not None:
        exp, rp = hit
        if now < exp:
            if not rp.can_fetch(ua, url):
                raise ValueError(
                    f"robots.txt on {host!r} disallows fetching this URL for automated clients. "
                    "Ask the user to export or paste content, or set WEB_FETCH_CHECK_ROBOTS=0 for local-only use."
                )
            return

    robots_url = f"{parsed.scheme}://{host}/robots.txt"
    new_rp = RobotFileParser()
    new_rp.set_url(robots_url)
    try:
        resp = await polite_get(client, robots_url)
        new_rp.parse(resp.text.splitlines())
    except httpx.HTTPStatusError as e:
        if e.response is not None and e.response.status_code == 404:
            new_rp.parse(_allow_all_rules())
        else:
            logger.warning("robots_fetch_failed", host=host, status=e.response.status_code)
            new_rp.parse(_allow_all_rules())
    except Exception as e:
        logger.warning("robots_fetch_failed", host=host, error=str(e))
        new_rp.parse(_allow_all_rules())

    _cache[host] = (now + ttl, new_rp)
    if not new_rp.can_fetch(ua, url):
        raise ValueError(
            f"robots.txt on {host!r} disallows fetching this URL for automated clients. "
            "Ask the user to export or paste content, or set WEB_FETCH_CHECK_ROBOTS=0 for local-only use."
        )
