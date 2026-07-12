"""DuckDuckGo search (no API key; always available)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode

from leagent.tools.web.polite_http import polite_get
from leagent.tools.web.web_search.providers.ddg_html import search_duckduckgo_html
from leagent.tools.web.web_search.protocol import SearchHit


class DuckDuckGoLiteProvider:
    """Prefer html.duckduckgo.com; fall back to lite.duckduckgo.com."""

    name = "duckduckgo_lite"

    def available(self) -> bool:
        return True

    def missing_credential_hint(self) -> str:
        return ""

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        try:
            hits = await search_duckduckgo_html(
                client, query, max_results=max_results, source="duckduckgo_html"
            )
            if hits:
                return hits
        except Exception:
            pass

        url = f"https://lite.duckduckgo.com/lite/?{urlencode({'q': query})}"
        r = await polite_get(client, url)
        r.raise_for_status()
        text = r.text
        out: list[SearchHit] = []
        for m in re.finditer(
            r'<a[^>]*class="[^"]*result-link[^"]*"[^>]*href="([^"]+)"[^>]*>([^<]*)</a>',
            text,
            re.IGNORECASE,
        ):
            href, title = m.group(1), (m.group(2) or "").strip()
            if href.startswith("//"):
                href = "https:" + href
            if not href.startswith("http"):
                continue
            out.append(
                SearchHit(
                    title=title or href,
                    url=href,
                    snippet="",
                    source="duckduckgo_lite",
                    position=len(out) + 1,
                )
            )
            if len(out) >= max_results:
                break
        return out
