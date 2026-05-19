"""Search the web for image URLs, then use ``web_image_download`` to attach locally."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCapability, ToolCategory, ToolContext
from leagent.tools.web.image_search.google_cse import search_google_cse

logger = structlog.get_logger(__name__)


class WebImageSearchTool(BaseTool):
    """Discover HTTPS image URLs via Google CSE when configured; otherwise returns empty + guidance."""

    name = "web_image_search"
    description = (
        "Search the web for images and return HTTPS URLs when Google CSE is configured; "
        "if not configured, returns an empty list with guidance so you can continue without images. "
        "After picking a URL, call web_image_download to save it into the session workspace "
        "and obtain preview_url for markdown ![alt](url) or GenUI Image nodes."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 45
    is_read_only = True
    is_concurrency_safe = True
    capabilities = (ToolCapability.NETWORK,)
    search_hint = "image search pictures photos meme illustration google find URL"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["query"],
            "additionalProperties": False,
            "properties": {
                "query": {"type": "string", "description": "Search query (what images to find)."},
                "max_results": {
                    "type": "integer",
                    "description": "Max URLs to return (1–10 per API request).",
                    "minimum": 1,
                    "maximum": 10,
                },
                "intent": {
                    "type": "string",
                    "enum": ["general", "meme"],
                    "description": "meme: bias toward meme/sticker-style results (query hint).",
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        from leagent.config.settings import get_settings

        raw_q = str(params.get("query") or "").strip()
        if not raw_q:
            raise ValueError("query is required")

        intent = "general"
        if params.get("intent") == "meme":
            intent = "meme"

        q = raw_q
        if intent == "meme" and "meme" not in q.lower():
            q = f"{q} meme"

        max_results = params.get("max_results")
        if max_results is None:
            max_results = get_settings().image_search.max_results_default
        max_results = int(max_results)
        max_results = max(1, min(max_results, 10))

        cfg = get_settings().image_search
        if cfg.provider != "google_cse":
            return {
                "query": q,
                "intent": intent,
                "provider": cfg.provider,
                "count": 0,
                "results": [],
                "image_search_configured": False,
                "degraded": True,
                "next_step": (
                    f"Image search provider {cfg.provider!r} is not supported in this build. "
                    "Continue without auto image search."
                ),
            }

        key = (cfg.api_key or "").strip()
        cx = (cfg.cx or "").strip()
        if not key or not cx:
            return {
                "query": q,
                "intent": intent,
                "provider": cfg.provider,
                "count": 0,
                "results": [],
                "image_search_configured": False,
                "degraded": True,
                "next_step": (
                    "Google image search is not configured (IMAGE_SEARCH_API_KEY + IMAGE_SEARCH_CX in Settings). "
                    "Continue without stock images: use prose-only answers, ask the user to attach an image or paste "
                    "an https image URL, or use web_search + web_scraper on a page that lists images if allowed."
                ),
            }

        try:
            hits = await search_google_cse(
                q,
                api_key=key,
                cx=cx,
                max_results=max_results,
                endpoint=cfg.endpoint,
            )
        except Exception as e:
            logger.warning("web_image_search_failed", error=str(e))
            return {
                "query": q,
                "intent": intent,
                "provider": cfg.provider,
                "count": 0,
                "results": [],
                "image_search_configured": True,
                "degraded": True,
                "next_step": (
                    f"Google image search request failed ({e!s}). Continue without auto images; "
                    "use attachments, user-provided URLs, or web_search + web_scraper if appropriate."
                ),
            }

        results = [
            {
                "url": h.url,
                "title": h.title,
                "thumbnail_url": h.thumbnail_url,
                "source_host": h.source_host,
            }
            for h in hits
        ]

        return {
            "query": q,
            "intent": intent,
            "provider": cfg.provider,
            "count": len(results),
            "results": results,
            "image_search_configured": True,
            "degraded": len(results) == 0,
            "next_step": "Call web_image_download(url=chosen_https_url) then cite preview_url in markdown or GenUI.",
        }
