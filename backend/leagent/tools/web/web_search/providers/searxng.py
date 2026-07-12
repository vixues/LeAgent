"""Self-hosted SearXNG JSON search."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from leagent.tools.web.polite_http import polite_get
from leagent.tools.web.web_search.protocol import SearchHit


class SearxngWebSearchProvider:
    name = "searxng"

    def available(self) -> bool:
        from leagent.config.settings import get_settings

        return bool((get_settings().web_search.searxng_base_url or "").strip())

    def missing_credential_hint(self) -> str:
        return "Set WEB_SEARCH_SEARXNG_BASE_URL in Settings (http(s)://… SearXNG instance)."

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        base = (cfg.searxng_base_url or "").strip().rstrip("/")
        if not base:
            return []
        url = f"{base}/search?{urlencode({'q': query, 'format': 'json'})}"
        r = await polite_get(client, url)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        out: list[SearchHit] = []
        for row in results[:max_results]:
            out.append(
                SearchHit(
                    title=str(row.get("title") or ""),
                    url=str(row.get("url") or ""),
                    snippet=str(row.get("content") or ""),
                    source="searxng",
                    position=len(out) + 1,
                )
            )
        return out
