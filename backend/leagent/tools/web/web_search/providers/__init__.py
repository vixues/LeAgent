"""Built-in general web search providers."""

from __future__ import annotations

from leagent.tools.web.web_search.providers.bing import BingWebSearchProvider
from leagent.tools.web.web_search.providers.bing_playwright import BingPlaywrightWebSearchProvider
from leagent.tools.web.web_search.providers.brave import BraveWebSearchProvider
from leagent.tools.web.web_search.providers.duckduckgo_lite import DuckDuckGoLiteProvider
from leagent.tools.web.web_search.providers.exa import ExaWebSearchProvider
from leagent.tools.web.web_search.providers.firecrawl import FirecrawlWebSearchProvider
from leagent.tools.web.web_search.providers.searxng import SearxngWebSearchProvider
from leagent.tools.web.web_search.providers.serper import SerperWebSearchProvider
from leagent.tools.web.web_search.providers.tavily import TavilyWebSearchProvider
from leagent.tools.web.web_search.protocol import WebSearchProvider

__all__ = [
    "BingPlaywrightWebSearchProvider",
    "BingWebSearchProvider",
    "BraveWebSearchProvider",
    "DuckDuckGoLiteProvider",
    "ExaWebSearchProvider",
    "FirecrawlWebSearchProvider",
    "SearxngWebSearchProvider",
    "SerperWebSearchProvider",
    "TavilyWebSearchProvider",
    "build_default_providers",
]


def build_default_providers() -> list[WebSearchProvider]:
    return [
        BingPlaywrightWebSearchProvider(),
        DuckDuckGoLiteProvider(),
        SearxngWebSearchProvider(),
        BingWebSearchProvider(),
        BraveWebSearchProvider(),
        TavilyWebSearchProvider(),
        ExaWebSearchProvider(),
        FirecrawlWebSearchProvider(),
        SerperWebSearchProvider(),
    ]
