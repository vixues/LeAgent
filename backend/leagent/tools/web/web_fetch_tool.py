"""Lightweight HTTP page fetch + readable extract (no Playwright)."""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from leagent.config.settings import get_settings
from leagent.tools.base import BaseTool, ToolCapability, ToolCategory, ToolContext
from leagent.tools.web.polite_http import polite_get, public_fetch_user_agent
from leagent.tools.web.robots_policy import assert_fetch_allowed
from leagent.tools.web.web_fetch.extract import html_to_readable_text
from leagent.tools.web.web_fetch.ssrf import assert_public_http_url
from leagent.tools.web.web_fetch.summarize import maybe_summarize_content
from leagent.tools.web.web_search.cache import get_fetch_cache

logger = structlog.get_logger(__name__)


class WebFetchTool(BaseTool):
    """Fetch a known URL over HTTP and extract readable main content.

    Does **not** execute JavaScript. For SPA / login pages use ``web_scraper``.
    """

    name = "web_fetch"
    description = (
        "Fetch a known https URL with plain HTTP and extract readable text/markdown-ish content. "
        "Does not run JavaScript. Prefer after web_search when you need page body text; "
        "use web_scraper only for JS-rendered or login-protected pages."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 45
    is_read_only = True
    is_concurrency_safe = True
    capabilities = (ToolCapability.NETWORK,)
    aliases = ["http_fetch"]
    search_hint = "fetch page url http extract readable content markdown"
    max_result_size_chars = 220_000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["url"],
            "additionalProperties": False,
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Public http(s) URL to fetch (not private/localhost).",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Hard cap on returned content characters (default from settings).",
                    "minimum": 500,
                    "maximum": 200_000,
                },
                "summarize": {
                    "type": "boolean",
                    "default": True,
                    "description": "When true, long pages are size-gated (summarize/truncate).",
                },
            },
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        u = (params or {}).get("url", "")
        host = ""
        try:
            host = urlparse(str(u)).hostname or ""
        except Exception:
            pass
        return f"Fetching{f' {host}' if host else ''}"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            url = assert_public_http_url(str(params.get("url") or ""))
        except ValueError as e:
            return {
                "url": str(params.get("url") or ""),
                "ok": False,
                "error": str(e),
                "next_step": (
                    "URL blocked by SSRF/public-host checks, or invalid. "
                    "Use a public https URL, or web_scraper if appropriate."
                ),
            }
        cfg = get_settings().web_fetch
        summarize = params.get("summarize")
        if summarize is None:
            summarize = True
        max_chars = int(params.get("max_chars") or cfg.max_content_chars)
        max_chars = max(500, min(max_chars, 200_000))

        cache_ttl = float(cfg.cache_ttl_minutes or 0.0)
        cache_key = hashlib.sha256(
            f"{url}|{max_chars}|{int(bool(summarize))}".encode("utf-8")
        ).hexdigest()
        if cache_ttl > 0:
            cached = get_fetch_cache(ttl_minutes=cache_ttl).get(cache_key)
            if cached is not None:
                out = dict(cached)
                out["cached"] = True
                return out

        ua = public_fetch_user_agent()
        timeout = float(cfg.timeout_sec or 30.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
            },
            trust_env=True,
        ) as client:
            # Re-check final URL after redirects for SSRF
            await assert_fetch_allowed(client, url)
            try:
                resp = await polite_get(client, url)
            except httpx.HTTPError as e:
                logger.warning("web_fetch_http_error", url=url[:120], error=str(e))
                return {
                    "url": url,
                    "ok": False,
                    "error": str(e),
                    "next_step": "Retry later, or use web_scraper if the site blocks plain HTTP clients.",
                }

            final_url = str(resp.url)
            try:
                assert_public_http_url(final_url)
            except ValueError as e:
                return {
                    "url": url,
                    "final_url": final_url,
                    "ok": False,
                    "error": f"Redirect blocked: {e}",
                    "next_step": "Choose a different public URL.",
                }

            ctype = (resp.headers.get("content-type") or "").lower()
            raw = resp.text or ""
            title = ""
            content = raw
            if "html" in ctype or raw.lstrip()[:32].lower().startswith(("<!doctype", "<html")):
                title, content = html_to_readable_text(raw)
            elif "json" in ctype:
                content = raw
                title = ""
            else:
                content = raw

            compression: dict[str, Any] = {"mode": "raw", "compressed": False, "notes": []}
            if summarize:
                content, compression = await maybe_summarize_content(
                    content,
                    threshold=int(cfg.summarize_threshold_chars),
                    output_chars=min(max_chars, int(cfg.summarize_output_chars)),
                    refuse_over=int(cfg.refuse_over_chars),
                )
            if len(content) > max_chars:
                content = content[:max_chars]
                compression = dict(compression)
                compression["compressed"] = True
                notes = list(compression.get("notes") or [])
                notes.append(f"Clipped to max_chars={max_chars}.")
                compression["notes"] = notes
                if compression.get("mode") == "raw":
                    compression["mode"] = "truncated"

            # Empty / near-empty HTML shell → hint scraper
            next_step = ""
            if len(content.strip()) < 80 and "html" in ctype:
                next_step = (
                    "Extracted little text (possible JS shell). Retry with web_scraper for rendered DOM."
                )

            result = {
                "url": url,
                "final_url": final_url,
                "ok": True,
                "status_code": resp.status_code,
                "content_type": ctype,
                "title": title,
                "content": content,
                "chars": len(content),
                "compression": compression,
                "cached": False,
                "next_step": next_step,
            }
            if cache_ttl > 0 and result["ok"]:
                get_fetch_cache(ttl_minutes=cache_ttl).set(cache_key, {k: v for k, v in result.items() if k != "cached"})
            return result
