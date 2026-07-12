"""DuckDuckGo HTML search helpers (no API key)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote, urlencode

from leagent.tools.web.polite_http import polite_get
from leagent.tools.web.web_search.protocol import SearchHit


async def search_duckduckgo_html(
    client: Any,
    query: str,
    *,
    max_results: int,
    source: str = "duckduckgo_html",
) -> list[SearchHit]:
    """Parse ``html.duckduckgo.com`` results (more reliable than lite for CJK)."""
    url = f"https://html.duckduckgo.com/html/?{urlencode({'q': query})}"
    r = await polite_get(client, url)
    r.raise_for_status()
    text = r.text
    out: list[SearchHit] = []
    seen: set[str] = set()

    # Prefer classic result__a blocks with title + uddg redirect target.
    for m in re.finditer(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        href_raw, title_html = m.group(1), m.group(2)
        title = re.sub(r"<[^>]+>", "", title_html or "").strip()
        href = href_raw
        um = re.search(r"[?&]uddg=([^&]+)", href_raw)
        if um:
            href = unquote(um.group(1))
        if href.startswith("//"):
            href = "https:" + href
        if not href.startswith("http"):
            continue
        if "duckduckgo.com" in href:
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append(
            SearchHit(
                title=title or href,
                url=href,
                snippet="",
                source=source,
                position=len(out) + 1,
            )
        )
        if len(out) >= max_results:
            break

    if out:
        return out

    # Fallback: any uddg= links
    for m in re.finditer(r"[?&]uddg=([^&\"']+)", text):
        href = unquote(m.group(1))
        if not href.startswith("http") or "duckduckgo.com" in href:
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append(
            SearchHit(
                title=href,
                url=href,
                snippet="",
                source=source,
                position=len(out) + 1,
            )
        )
        if len(out) >= max_results:
            break
    return out
