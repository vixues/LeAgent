"""Firecrawl search API (cloud or self-hosted base URL)."""

from __future__ import annotations

from typing import Any

from leagent.tools.web.polite_http import polite_request
from leagent.tools.web.web_search.protocol import SearchHit


class FirecrawlWebSearchProvider:
    name = "firecrawl"

    def available(self) -> bool:
        from leagent.config.settings import get_settings

        cfg = get_settings().web_search
        # Self-hosted URL alone is enough; cloud needs an API key.
        if (cfg.firecrawl_api_url or "").strip():
            return True
        return bool((cfg.firecrawl_api_key or "").strip())

    def missing_credential_hint(self) -> str:
        return (
            "Set WEB_SEARCH_FIRECRAWL_API_KEY (and optionally WEB_SEARCH_FIRECRAWL_API_URL "
            "for a self-hosted instance)."
        )

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        key = (cfg.firecrawl_api_key or "").strip()
        base = (cfg.firecrawl_api_url or "").strip().rstrip("/") or "https://api.firecrawl.dev"
        if not key and not (cfg.firecrawl_api_url or "").strip():
            return []
        url = f"{base}/v1/search"
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        payload = {"query": query, "limit": max_results}
        r = await polite_request(client, "POST", url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        # Firecrawl returns { success, data: [ {url, title, description, markdown?} ] }
        rows = data.get("data") if isinstance(data, dict) else None
        if rows is None and isinstance(data, dict):
            rows = data.get("results") or []
        if not isinstance(rows, list):
            rows = []
        out: list[SearchHit] = []
        for row in rows[:max_results]:
            if not isinstance(row, dict):
                continue
            snippet = str(
                row.get("description")
                or row.get("snippet")
                or (row.get("markdown") or "")[:500]
                or ""
            )
            out.append(
                SearchHit(
                    title=str(row.get("title") or ""),
                    url=str(row.get("url") or ""),
                    snippet=snippet[:800],
                    source="firecrawl",
                    position=len(out) + 1,
                )
            )
        return out
