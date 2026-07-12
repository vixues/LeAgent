"""Tavily Search API."""

from __future__ import annotations

from typing import Any

from leagent.tools.web.polite_http import polite_request
from leagent.tools.web.web_search.protocol import SearchHit


class TavilyWebSearchProvider:
    name = "tavily"

    def available(self) -> bool:
        from leagent.config.settings import get_settings

        return bool((get_settings().web_search.tavily_api_key or "").strip())

    def missing_credential_hint(self) -> str:
        return "Set WEB_SEARCH_TAVILY_API_KEY in Settings (app.tavily.com)."

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        key = (cfg.tavily_api_key or "").strip()
        if not key:
            return []
        payload = {
            "api_key": key,
            "query": query,
            "max_results": max_results,
            "include_answer": False,
            "search_depth": "basic",
        }
        r = await polite_request(
            client,
            "POST",
            "https://api.tavily.com/search",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
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
                    source="tavily",
                    position=len(out) + 1,
                )
            )
        return out
