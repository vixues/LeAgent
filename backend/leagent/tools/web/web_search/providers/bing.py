"""Bing Web Search API v7."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from leagent.tools.web.polite_http import polite_get
from leagent.tools.web.web_search.protocol import SearchHit


class BingWebSearchProvider:
    name = "bing"

    def available(self) -> bool:
        from leagent.config.settings import get_settings

        return bool((get_settings().web_search.bing_api_key or "").strip())

    def missing_credential_hint(self) -> str:
        return "Set WEB_SEARCH_BING_API_KEY in Settings (Azure Bing Web Search)."

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        key = (cfg.bing_api_key or "").strip()
        if not key:
            return []
        endpoint = (cfg.bing_endpoint or "https://api.bing.microsoft.com/v7.0/search").rstrip("/")
        url = f"{endpoint}?{urlencode({'q': query, 'count': max_results})}"
        r = await polite_get(client, url, headers={"Ocp-Apim-Subscription-Key": key})
        r.raise_for_status()
        data = r.json()
        web_pages = ((data.get("webPages") or {}).get("value")) or []
        out: list[SearchHit] = []
        for row in web_pages[:max_results]:
            out.append(
                SearchHit(
                    title=str(row.get("name") or ""),
                    url=str(row.get("url") or ""),
                    snippet=str(row.get("snippet") or ""),
                    source="bing",
                    position=len(out) + 1,
                )
            )
        return out
