"""Pluggable general web search — shared types and provider protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

# Explicit provider ids (plus ``auto`` which resolves at runtime).
WEB_SEARCH_PROVIDER_IDS: tuple[str, ...] = (
    "auto",
    "bing_playwright",
    "duckduckgo_lite",
    "searxng",
    "bing",
    "brave",
    "tavily",
    "exa",
    "firecrawl",
    "serper",
)

# Preference order when WEB_SEARCH_PROVIDER=auto (only available/configured backends).
AUTO_PROVIDER_PREFERENCE: tuple[str, ...] = (
    "brave",
    "tavily",
    "exa",
    "firecrawl",
    "serper",
    "bing",
    "searxng",
    "bing_playwright",
)

# Zero-config floor — Playwright Bing, not unconfigured API scrapers.
DEFAULT_SEARCH_FLOOR = "bing_playwright"


@dataclass(frozen=True)
class SearchHit:
    """One web search result suitable for follow-up ``web_fetch`` / ``web_scraper``."""

    title: str
    url: str
    snippet: str = ""
    source: str = ""
    position: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
        }
        if self.position is not None:
            out["position"] = self.position
        return out


@runtime_checkable
class WebSearchProvider(Protocol):
    """Strategy protocol every general web-search backend implements."""

    @property
    def name(self) -> str:
        """Stable id used in ``WEB_SEARCH_PROVIDER``."""
        ...

    def available(self) -> bool:
        """Whether credentials / URL / runtime deps are present (no network I/O)."""
        ...

    def missing_credential_hint(self) -> str:
        """Human-readable hint when ``available()`` is False."""
        ...

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        """Run a search using the shared ``httpx.AsyncClient`` (or browser pool)."""
        ...
