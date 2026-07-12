"""Tests for web search providers, failover, and web_fetch helpers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from leagent.config.settings import WebSearchSettings
from leagent.tools.web.web_fetch.extract import html_to_readable_text
from leagent.tools.web.web_fetch.ssrf import assert_public_http_url
from leagent.tools.web.web_fetch.summarize import maybe_summarize_content
from leagent.tools.web.web_search.cache import reset_web_caches
from leagent.tools.web.web_search.core import _normalize_focus, run_web_search
from leagent.tools.web.web_search.protocol import SearchHit
from leagent.tools.web.web_search.providers.brave import BraveWebSearchProvider
from leagent.tools.web.web_search.providers.duckduckgo_lite import DuckDuckGoLiteProvider
from leagent.tools.web.web_search.providers.serper import SerperWebSearchProvider
from leagent.tools.web.web_search.providers.tavily import TavilyWebSearchProvider
from leagent.tools.web.web_search.service import (
    WebSearchService,
    reset_web_search_service,
)


@pytest.fixture(autouse=True)
def _reset_web_singletons() -> None:
    reset_web_caches()
    reset_web_search_service()
    yield
    reset_web_caches()
    reset_web_search_service()


def test_normalize_focus_arxiv() -> None:
    assert _normalize_focus("2401.12345", "auto") == "arxiv"
    assert _normalize_focus("hello world", "auto") == "general"
    assert _normalize_focus("anything", "wikipedia") == "wikipedia"


def test_html_to_readable_text_prefers_main() -> None:
    html = """
    <html><head><title>Hello</title></head>
    <body>
      <nav>skip me</nav>
      <main><h1>Title</h1><p>Body text here.</p></main>
      <script>evil()</script>
    </body></html>
    """
    title, text = html_to_readable_text(html)
    assert title == "Hello"
    assert "Body text here" in text
    assert "evil" not in text
    assert "skip me" not in text


def test_ssrf_blocks_localhost() -> None:
    with pytest.raises(ValueError, match="private|local"):
        assert_public_http_url("http://localhost/admin")
    with pytest.raises(ValueError, match="private|Refusing|non-public"):
        assert_public_http_url("http://127.0.0.1/")
    with pytest.raises(ValueError, match="http"):
        assert_public_http_url("ftp://example.com/x")


def test_ssrf_allows_when_any_public_a_record(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wikipedia-like: public IPv4 + private-looking IPv6 must still be allowed."""
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("199.16.158.8", 0)),
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001::1", 0, 0, 0)),
        ],
    )
    out = assert_public_http_url("https://en.wikipedia.org/wiki/X")
    assert out.startswith("https://en.wikipedia.org")


def test_ssrf_blocks_when_only_private(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001::1", 0, 0, 0)),
        ],
    )
    with pytest.raises(ValueError, match="non-public"):
        assert_public_http_url("https://evil.example/")


def test_hits_look_relevant() -> None:
    from leagent.tools.web.web_search.providers.bing_playwright import hits_look_relevant
    from leagent.tools.web.web_search.protocol import SearchHit

    good = [SearchHit(title="长征十号运载火箭", url="https://zh.wikipedia.org/wiki/x", source="t")]
    bad = [SearchHit(title="How to get help in Windows", url="https://support.microsoft.com/", source="t")]
    assert hits_look_relevant("长征十号", good) is True
    assert hits_look_relevant("长征十号", bad) is False


def test_ssrf_allows_public_example() -> None:
    # example.com is a well-known public name; DNS may fail offline — tolerate resolve errors.
    try:
        out = assert_public_http_url("https://example.com/path")
        assert out.startswith("https://example.com")
    except ValueError as e:
        if "Cannot resolve" not in str(e):
            raise


@pytest.mark.asyncio
async def test_maybe_summarize_truncates_without_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_llm(*_a: Any, **_k: Any) -> str | None:
        return None

    monkeypatch.setattr(
        "leagent.tools.web.web_fetch.summarize._try_llm_summarize",
        no_llm,
    )
    long = "x" * 10_000
    out, meta = await maybe_summarize_content(
        long, threshold=100, output_chars=200, refuse_over=1_000_000
    )
    assert len(out) == 200
    assert meta["mode"] == "truncated"
    assert meta["compressed"] is True


@pytest.mark.asyncio
async def test_brave_provider_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "web": {
            "results": [
                {"title": "A", "url": "https://a.example/", "description": "da"},
                {"title": "B", "url": "https://b.example/", "description": "db"},
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=payload)
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)

    cfg = WebSearchSettings(brave_api_key="brave-key", provider="brave")
    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: MagicMock(web_search=cfg),
    )

    prov = BraveWebSearchProvider()
    assert prov.available()
    hits = await prov.search("q", max_results=2, client=mock_client, cfg=cfg)
    assert len(hits) == 2
    assert hits[0].source == "brave"
    assert hits[0].url == "https://a.example/"


@pytest.mark.asyncio
async def test_tavily_and_serper_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    tavily_payload = {
        "results": [{"title": "T", "url": "https://t.example/", "content": "tc"}]
    }
    serper_payload = {
        "organic": [{"title": "S", "link": "https://s.example/", "snippet": "ss"}]
    }

    async def fake_request(client: Any, method: str, url: str, **kwargs: Any) -> MagicMock:
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        if "tavily" in url:
            resp.json = MagicMock(return_value=tavily_payload)
        else:
            resp.json = MagicMock(return_value=serper_payload)
        return resp

    monkeypatch.setattr(
        "leagent.tools.web.web_search.providers.tavily.polite_request",
        fake_request,
    )
    monkeypatch.setattr(
        "leagent.tools.web.web_search.providers.serper.polite_request",
        fake_request,
    )

    t_cfg = WebSearchSettings(tavily_api_key="tvly", provider="tavily")
    s_cfg = WebSearchSettings(serper_api_key="serp", provider="serper")
    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: MagicMock(web_search=t_cfg),
    )
    t_hits = await TavilyWebSearchProvider().search(
        "q", max_results=3, client=AsyncMock(), cfg=t_cfg
    )
    assert t_hits[0].source == "tavily"

    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: MagicMock(web_search=s_cfg),
    )
    s_hits = await SerperWebSearchProvider().search(
        "q", max_results=3, client=AsyncMock(), cfg=s_cfg
    )
    assert s_hits[0].url == "https://s.example/"


@pytest.mark.asyncio
async def test_service_failover_when_primary_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingKeyProvider:
        name = "brave"

        def available(self) -> bool:
            return False

        def missing_credential_hint(self) -> str:
            return "Set WEB_SEARCH_BRAVE_API_KEY"

        async def search(self, *a: Any, **k: Any) -> list[SearchHit]:
            raise AssertionError("should not be called")

    class FloorProvider:
        name = "bing_playwright"

        def available(self) -> bool:
            return True

        def missing_credential_hint(self) -> str:
            return ""

        async def search(self, query: str, *, max_results: int, client: Any, cfg: Any) -> list[SearchHit]:
            return [SearchHit(title="ok", url="https://example.com/", snippet="", source="bing_playwright")]

    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: MagicMock(web_fetch=MagicMock(cache_ttl_minutes=0)),
    )

    svc = WebSearchService()
    svc.register(MissingKeyProvider())  # type: ignore[arg-type]
    svc.register(FloorProvider())  # type: ignore[arg-type]

    cfg = WebSearchSettings(provider="brave", cache_ttl_minutes=0)
    results, strategy, reasons, had_fallback = await svc.search(
        "q", max_results=3, client=AsyncMock(), cfg=cfg, preferred="brave"
    )
    assert had_fallback is True
    assert strategy == "bing_playwright"
    assert results[0]["url"] == "https://example.com/"
    assert any("BRAVE" in r for r in reasons)


@pytest.mark.asyncio
async def test_service_failover_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class BoomProvider:
        name = "bing"

        def available(self) -> bool:
            return True

        def missing_credential_hint(self) -> str:
            return ""

        async def search(self, *a: Any, **k: Any) -> list[SearchHit]:
            raise httpx.HTTPError("boom")

    class FloorProvider:
        name = "bing_playwright"

        def available(self) -> bool:
            return True

        def missing_credential_hint(self) -> str:
            return ""

        async def search(self, *a: Any, **k: Any) -> list[SearchHit]:
            return [SearchHit(title="bing-pw", url="https://bing.example/", source="bing_playwright")]

    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: MagicMock(web_fetch=MagicMock(cache_ttl_minutes=0)),
    )

    svc = WebSearchService()
    svc.register(BoomProvider())  # type: ignore[arg-type]
    svc.register(FloorProvider())  # type: ignore[arg-type]
    cfg = WebSearchSettings(provider="bing", bing_api_key="x", cache_ttl_minutes=0)
    results, strategy, reasons, had_fallback = await svc.search(
        "q", max_results=2, client=AsyncMock(), cfg=cfg, preferred="bing"
    )
    assert had_fallback
    assert strategy == "bing_playwright"
    assert results[0]["title"] == "bing-pw"
    assert any("Fell back" in r for r in reasons)


def test_auto_resolves_to_bing_playwright_without_api_keys() -> None:
    from leagent.tools.web.web_search.providers import build_default_providers

    svc = WebSearchService()
    for p in build_default_providers():
        svc.register(p)
    cfg = WebSearchSettings(provider="auto")
    name, reasons = svc.resolve_provider_name("auto", cfg)
    assert name == "bing_playwright"
    assert reasons == [] or any(
        "bing_playwright" in r or "TAVILY" in r or "No configured" in r for r in reasons
    )


def test_default_provider_is_tavily() -> None:
    assert WebSearchSettings().provider == "tavily"


def test_tavily_default_falls_back_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.tools.web.web_search.providers import build_default_providers

    cfg = WebSearchSettings(provider="tavily")
    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: MagicMock(web_search=cfg, web_fetch=MagicMock(cache_ttl_minutes=0)),
    )
    svc = WebSearchService()
    for p in build_default_providers():
        svc.register(p)
    name, reasons = svc.resolve_provider_name("tavily", cfg)
    assert name == "bing_playwright"
    assert any("TAVILY" in r or "tavily" in r.lower() for r in reasons)


def test_auto_prefers_configured_tavily_over_brave(monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.tools.web.web_search.providers import build_default_providers

    cfg = WebSearchSettings(provider="auto", tavily_api_key="tk", brave_api_key="bk")
    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: MagicMock(web_search=cfg, web_fetch=MagicMock(cache_ttl_minutes=0)),
    )
    svc = WebSearchService()
    for p in build_default_providers():
        svc.register(p)
    name, _ = svc.resolve_provider_name("auto", cfg)
    assert name == "tavily"


def test_auto_prefers_configured_brave(monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.tools.web.web_search.providers import build_default_providers

    cfg = WebSearchSettings(provider="auto", brave_api_key="bk")
    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: MagicMock(web_search=cfg, web_fetch=MagicMock(cache_ttl_minutes=0)),
    )
    svc = WebSearchService()
    for p in build_default_providers():
        svc.register(p)
    name, _ = svc.resolve_provider_name("auto", cfg)
    assert name == "brave"


@pytest.mark.asyncio
async def test_run_web_search_recommends_tavily_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Svc:
        async def search(self, *a: Any, **k: Any) -> tuple[list[dict[str, Any]], str, list[str], bool]:
            return (
                [{"title": "x", "url": "https://example.com", "snippet": "", "source": "bing_playwright"}],
                "bing_playwright",
                ["Set WEB_SEARCH_TAVILY_API_KEY...; falling back"],
                True,
            )

    class _CM:
        async def __aenter__(self) -> AsyncMock:
            return AsyncMock()

        async def __aexit__(self, *a: Any) -> None:
            return None

    monkeypatch.setattr(
        "leagent.tools.web.web_search.core.get_web_search_service",
        lambda: _Svc(),
    )
    monkeypatch.setattr(
        "leagent.tools.web.web_search.core.search_http_client",
        lambda **kwargs: _CM(),
    )

    cfg = WebSearchSettings(provider="tavily", cache_ttl_minutes=0)
    out = await run_web_search(query="hello world", focus="general", max_results=3, cfg=cfg)
    assert out["strategy"] == "bing_playwright"
    assert out["count"] == 1
    assert "WEB_SEARCH_TAVILY_API_KEY" in out["next_step"]
    assert any("WEB_SEARCH_TAVILY_API_KEY" in r for r in out["degraded_reasons"])


@pytest.mark.asyncio
async def test_run_web_search_wikipedia_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_wiki(client: Any, query: str, max_results: int) -> list[dict[str, Any]]:
        return [
            {
                "title": "Wiki",
                "url": "https://en.wikipedia.org/wiki/X",
                "snippet": "s",
                "source": "wikipedia_opensearch",
            }
        ]

    monkeypatch.setattr(
        "leagent.tools.web.web_search.core._wikipedia_opensearch",
        fake_wiki,
    )

    class _CM:
        async def __aenter__(self) -> AsyncMock:
            return AsyncMock()

        async def __aexit__(self, *a: Any) -> None:
            return None

    monkeypatch.setattr(
        "leagent.tools.web.web_search.core.search_http_client",
        lambda **kwargs: _CM(),
    )

    cfg = WebSearchSettings(cache_ttl_minutes=0)
    out = await run_web_search(query="python", focus="wikipedia", max_results=5, cfg=cfg)
    assert out["focus_resolved"] == "wikipedia"
    assert out["count"] == 1
    assert out["results"][0]["source"] == "wikipedia_opensearch"
    assert "web_fetch" in out["next_step"]


@pytest.mark.asyncio
async def test_duckduckgo_lite_parses_html() -> None:
    html = """
    <html><body>
    <a class="result-link" href="https://example.com/a">Alpha</a>
    <a class="result-link" href="//example.com/b">Beta</a>
    </body></html>
    """
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = html
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)

    hits = await DuckDuckGoLiteProvider().search(
        "q", max_results=5, client=mock_client, cfg=WebSearchSettings()
    )
    assert len(hits) == 2
    assert hits[1].url.startswith("https:")


def test_validate_web_search_provider_new_values() -> None:
    from leagent.services.settings_configure import SettingsConfigureError, validate_env_updates

    validate_env_updates({"WEB_SEARCH_PROVIDER": "tavily"})
    validate_env_updates({"WEB_SEARCH_PROVIDER": "brave"})
    validate_env_updates({"WEB_SEARCH_PROVIDER": "auto"})
    validate_env_updates({"WEB_SEARCH_PROVIDER": "bing_playwright"})
    validate_env_updates({"WEB_SEARCH_FIRECRAWL_API_URL": "https://fc.example"})
    with pytest.raises(SettingsConfigureError):
        validate_env_updates({"WEB_SEARCH_PROVIDER": "google"})
    with pytest.raises(SettingsConfigureError):
        validate_env_updates({"WEB_SEARCH_FIRECRAWL_API_URL": "not-a-url"})


@pytest.mark.asyncio
async def test_web_fetch_tool_ssrf(monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.web.web_fetch_tool import WebFetchTool

    tool = WebFetchTool()
    ctx = ToolContext(session_id="s", user_id="u")
    with pytest.raises(ValueError, match="private|local|Refusing"):
        await tool.execute({"url": "http://127.0.0.1/secret"}, ctx)
