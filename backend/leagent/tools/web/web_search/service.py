"""Web search service — provider registry with credential-aware selection."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import httpx
import structlog

from leagent.config.settings import WebSearchSettings
from leagent.tools.web.web_search.cache import get_search_cache
from leagent.tools.web.web_search.providers import build_default_providers
from leagent.tools.web.web_search.protocol import (
    AUTO_PROVIDER_PREFERENCE,
    DEFAULT_SEARCH_FLOOR,
    SearchHit,
    WebSearchProvider,
)

logger = structlog.get_logger(__name__)

_SERVICE: WebSearchService | None = None


class WebSearchService:
    """Strategy registry for general web search.

    Default provider is ``tavily`` (needs a key). ``auto`` never silently uses
    unconfigured API backends and prefers Tavily first when configured. The
    zero-config floor is Playwright Bing (``bing_playwright``).
    """

    def __init__(self) -> None:
        self._providers: dict[str, WebSearchProvider] = {}

    def register(self, provider: WebSearchProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> WebSearchProvider | None:
        return self._providers.get(name)

    def list_names(self) -> list[str]:
        return list(self._providers.keys())

    def available_names(self) -> list[str]:
        return [n for n, p in self._providers.items() if p.available()]

    def resolve_provider_name(self, preferred: str | None, cfg: WebSearchSettings) -> tuple[str, list[str]]:
        """Resolve ``auto`` / unavailable preferred → an available provider name.

        Returns ``(name, degraded_reasons)``.
        """
        reasons: list[str] = []
        raw = (preferred or cfg.provider or "auto").strip() or "auto"

        if raw == "auto":
            for name in AUTO_PROVIDER_PREFERENCE:
                prov = self._providers.get(name)
                if prov is not None and prov.available():
                    if name != DEFAULT_SEARCH_FLOOR:
                        reasons.append(f"auto selected configured provider={name}.")
                    else:
                        reasons.append(
                            "No WEB_SEARCH_TAVILY_API_KEY (preferred default); using "
                            "bing_playwright (Playwright + Bing). Recommend configuring "
                            "Tavily in Settings (app.tavily.com)."
                        )
                    return name, reasons
            reasons.append(
                "No WEB_SEARCH_TAVILY_API_KEY (preferred default); using bing_playwright "
                "(Playwright + Bing). Recommend configuring Tavily in Settings (app.tavily.com)."
            )
            return DEFAULT_SEARCH_FLOOR, reasons

        prov = self._providers.get(raw)
        if prov is None:
            reasons.append(f"Unknown WEB_SEARCH_PROVIDER={raw!r}; using {DEFAULT_SEARCH_FLOOR}.")
            return DEFAULT_SEARCH_FLOOR, reasons

        if not prov.available():
            hint = prov.missing_credential_hint() or f"{raw} is not configured"
            reasons.append(f"{hint}; not using unconfigured provider — falling back to {DEFAULT_SEARCH_FLOOR}.")
            floor = self._providers.get(DEFAULT_SEARCH_FLOOR)
            if floor is not None and floor.available():
                return DEFAULT_SEARCH_FLOOR, reasons
            reasons.append(
                f"{DEFAULT_SEARCH_FLOOR} unavailable. Install Playwright Chromium or set a search API key."
            )
            return DEFAULT_SEARCH_FLOOR, reasons

        return raw, reasons

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: httpx.AsyncClient,
        cfg: WebSearchSettings,
        preferred: str | None = None,
    ) -> tuple[list[dict[str, Any]], str, list[str], bool]:
        """Run general search.

        Returns ``(results, strategy, degraded_reasons, had_fallback)``.
        """
        reasons: list[str] = []
        had_fallback = False

        from leagent.config.settings import get_settings

        cache_ttl = float(get_settings().web_fetch.cache_ttl_minutes or 0.0)
        if cache_ttl <= 0:
            cache_ttl = float(getattr(cfg, "cache_ttl_minutes", 0.0) or 0.0)

        requested = (preferred or cfg.provider or "auto").strip() or "auto"
        resolved, resolve_reasons = self.resolve_provider_name(preferred, cfg)
        reasons.extend(resolve_reasons)
        if resolved != requested and requested != "auto":
            had_fallback = True
        if requested == "auto" and resolved != DEFAULT_SEARCH_FLOOR and resolve_reasons:
            # auto → configured API is intentional, not a failure fallback
            pass
        elif requested == "auto" and resolved == DEFAULT_SEARCH_FLOOR:
            had_fallback = False  # expected zero-config path

        cache_key = hashlib.sha256(
            json.dumps(
                {"q": query, "n": max_results, "p": resolved},
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        if cache_ttl > 0:
            cached = get_search_cache(ttl_minutes=cache_ttl).get(cache_key)
            if cached is not None:
                return (
                    list(cached.get("results") or []),
                    str(cached.get("strategy") or resolved) + "_cached",
                    list(cached.get("degraded_reasons") or []) + reasons,
                    bool(cached.get("had_fallback")) or had_fallback,
                )

        primary = self._providers.get(resolved)
        if primary is None or not primary.available():
            return (
                [],
                f"{resolved}_unavailable",
                reasons
                + [
                    "No usable web search provider. Install Playwright "
                    "(`uv run playwright install chromium`) or configure an API key "
                    "(Brave/Tavily/Exa/Firecrawl/Serper/Bing) or SearXNG URL."
                ],
                True,
            )

        try:
            hits = await primary.search(query, max_results=max_results, client=client, cfg=cfg)
            strategy = "bing_api" if primary.name == "bing" else primary.name
            results = [h.to_dict() if isinstance(h, SearchHit) else h for h in hits]
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError, RuntimeError) as e:
            logger.warning("web_search_general_failed", provider=primary.name, error=str(e))
            reasons.append(f"{primary.name}:{e!s}")
            results = []
            strategy = f"{primary.name}_failed"
            # Fail over only to the Playwright Bing floor — never to unconfigured APIs / DDG.
            if primary.name != DEFAULT_SEARCH_FLOOR:
                had_fallback = True
                floor = self._providers.get(DEFAULT_SEARCH_FLOOR)
                if floor is not None and floor.available():
                    try:
                        hits = await floor.search(
                            query, max_results=max_results, client=client, cfg=cfg
                        )
                        results = [h.to_dict() for h in hits]
                        strategy = DEFAULT_SEARCH_FLOOR
                        reasons.append(
                            f"Fell back to {DEFAULT_SEARCH_FLOOR} after primary failure."
                        )
                    except (httpx.HTTPError, ValueError, RuntimeError) as e2:
                        results = []
                        strategy = f"{DEFAULT_SEARCH_FLOOR}_failed"
                        reasons.append(f"{DEFAULT_SEARCH_FLOOR}:{e2!s}")

        if cache_ttl > 0 and results:
            get_search_cache(ttl_minutes=cache_ttl).set(
                cache_key,
                {
                    "results": results,
                    "strategy": strategy,
                    "degraded_reasons": reasons,
                    "had_fallback": had_fallback,
                },
            )

        return results, strategy, reasons, had_fallback


def build_default_web_search_service() -> WebSearchService:
    svc = WebSearchService()
    for p in build_default_providers():
        svc.register(p)
    return svc


def get_web_search_service() -> WebSearchService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = build_default_web_search_service()
    return _SERVICE


def reset_web_search_service() -> None:
    """Test / settings-reload helper."""
    global _SERVICE
    _SERVICE = None
