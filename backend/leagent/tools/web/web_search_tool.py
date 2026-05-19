"""General web search: API-first for academic sources; lite HTML or SearXNG/Bing otherwise."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.config.settings import get_settings
from leagent.tools.base import BaseTool, ToolCapability, ToolCategory, ToolContext
from leagent.tools.web.web_search.core import run_web_search

logger = structlog.get_logger(__name__)


class WebSearchTool(BaseTool):
    """Search the web and return titles, URLs, and short snippets.

    For ``arxiv``, ``wikipedia``, ``crossref``, and ``pubmed`` this tool uses official
    HTTP APIs (no headless browser), which is more reliable behind strict networks.
    For ``general`` it uses ``WEB_SEARCH_PROVIDER`` (DuckDuckGo lite HTML, self-hosted
    SearxNG, or Bing Web Search API). Proxies from the environment are honored.
    """

    name = "web_search"
    description = (
        "Search the web for pages and papers; returns ranked results with URLs and snippets. "
        "Works without Bing/Google keys: use focus='arxiv'|'wikipedia'|'crossref'|'pubmed' (public APIs) or "
        "focus='general' (tries DuckDuckGo lite; Bing/SearXNG are optional upgrades). "
        "If results are empty, read degraded_reasons and next_step, then continue from context, user URLs, or web_scraper."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 50
    is_read_only = True
    is_concurrency_safe = True
    capabilities = (ToolCapability.NETWORK,)
    search_hint = "web search google bing find papers arxiv pubmed wikipedia crossref literature links"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["query"],
            "additionalProperties": False,
            "properties": {
                "query": {"type": "string", "description": "Search query or arXiv id (e.g. 2401.12345)."},
                "max_results": {
                    "type": "integer",
                    "description": "Max results (1–25).",
                    "minimum": 1,
                    "maximum": 25,
                },
                "focus": {
                    "type": "string",
                    "enum": ["auto", "arxiv", "wikipedia", "crossref", "pubmed", "general"],
                    "default": "auto",
                    "description": (
                        "auto: infer arxiv id vs general; arxiv/wikipedia/crossref/pubmed: official APIs; "
                        "general: configured provider (DDG lite / SearxNG / Bing)."
                    ),
                },
            },
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        q = (params or {}).get("query", "")
        return f"Searching{f' {q!r}' if q else ''}"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        raw_q = str(params.get("query") or "").strip()
        if not raw_q:
            raise ValueError("query is required")

        focus = params.get("focus") or "auto"
        if focus not in ("auto", "arxiv", "wikipedia", "crossref", "pubmed", "general"):
            focus = "auto"

        cfg = get_settings().web_search
        max_results = params.get("max_results")
        if max_results is None:
            max_results = cfg.max_results_default
        max_results = int(max_results)

        try:
            return await run_web_search(query=raw_q, focus=focus, max_results=max_results, cfg=cfg)
        except Exception as e:
            logger.warning("web_search_failed", error=str(e))
            return {
                "query": raw_q,
                "focus_requested": focus,
                "focus_resolved": "error",
                "strategy": "exception",
                "count": 0,
                "results": [],
                "degraded": True,
                "degraded_reasons": [str(e)],
                "next_step": (
                    "Search raised an unexpected error. Continue from session context and attachments; "
                    "ask the user for a direct https URL and use web_scraper if page content is required."
                ),
            }
