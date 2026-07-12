"""Exa neural / keyword search API."""

from __future__ import annotations

from typing import Any

from leagent.tools.web.polite_http import polite_request
from leagent.tools.web.web_search.protocol import SearchHit


class ExaWebSearchProvider:
    name = "exa"

    def available(self) -> bool:
        from leagent.config.settings import get_settings

        return bool((get_settings().web_search.exa_api_key or "").strip())

    def missing_credential_hint(self) -> str:
        return "Set WEB_SEARCH_EXA_API_KEY in Settings (dashboard.exa.ai)."

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        key = (cfg.exa_api_key or "").strip()
        if not key:
            return []
        payload = {
            "query": query,
            "numResults": max_results,
            "type": "auto",
            "contents": {"text": {"maxCharacters": 500}},
        }
        r = await polite_request(
            client,
            "POST",
            "https://api.exa.ai/search",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": key,
            },
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        out: list[SearchHit] = []
        for row in results[:max_results]:
            text = row.get("text") or row.get("summary") or ""
            out.append(
                SearchHit(
                    title=str(row.get("title") or ""),
                    url=str(row.get("url") or ""),
                    snippet=str(text)[:500],
                    source="exa",
                    position=len(out) + 1,
                )
            )
        return out
