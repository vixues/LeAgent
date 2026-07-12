"""Brave Search API."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from leagent.tools.web.polite_http import polite_get
from leagent.tools.web.web_search.protocol import SearchHit


class BraveWebSearchProvider:
    name = "brave"

    def available(self) -> bool:
        from leagent.config.settings import get_settings

        return bool((get_settings().web_search.brave_api_key or "").strip())

    def missing_credential_hint(self) -> str:
        return "Set WEB_SEARCH_BRAVE_API_KEY in Settings (api.search.brave.com)."

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        key = (cfg.brave_api_key or "").strip()
        if not key:
            return []
        url = "https://api.search.brave.com/res/v1/web/search?" + urlencode(
            {"q": query, "count": max_results}
        )
        r = await polite_get(
            client,
            url,
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": key,
            },
        )
        r.raise_for_status()
        data = r.json()
        web = (data.get("web") or {}).get("results") or []
        out: list[SearchHit] = []
        for row in web[:max_results]:
            out.append(
                SearchHit(
                    title=str(row.get("title") or ""),
                    url=str(row.get("url") or ""),
                    snippet=str(row.get("description") or ""),
                    source="brave",
                    position=len(out) + 1,
                )
            )
        return out
