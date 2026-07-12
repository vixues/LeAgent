"""Serper.dev Google SERP API."""

from __future__ import annotations

from typing import Any

from leagent.tools.web.polite_http import polite_request
from leagent.tools.web.web_search.protocol import SearchHit


class SerperWebSearchProvider:
    name = "serper"

    def available(self) -> bool:
        from leagent.config.settings import get_settings

        return bool((get_settings().web_search.serper_api_key or "").strip())

    def missing_credential_hint(self) -> str:
        return "Set WEB_SEARCH_SERPER_API_KEY in Settings (serper.dev)."

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        key = (cfg.serper_api_key or "").strip()
        if not key:
            return []
        payload = {"q": query, "num": max_results}
        r = await polite_request(
            client,
            "POST",
            "https://google.serper.dev/search",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": key,
            },
        )
        r.raise_for_status()
        data = r.json()
        organic = data.get("organic") or []
        out: list[SearchHit] = []
        for row in organic[:max_results]:
            out.append(
                SearchHit(
                    title=str(row.get("title") or ""),
                    url=str(row.get("link") or ""),
                    snippet=str(row.get("snippet") or ""),
                    source="serper",
                    position=len(out) + 1,
                )
            )
        return out
