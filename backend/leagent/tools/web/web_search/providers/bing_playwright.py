"""Bing search — Playwright first, then Bing RSS, then DuckDuckGo HTML.

Zero-config default floor. Headless Bing often serves challenges or junk SERPs;
we discard low-relevance hits and fall through to DuckDuckGo HTML which handles
CJK queries reliably without an API key.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote_plus, unquote

import structlog

from leagent.tools.web.polite_http import polite_get
from leagent.tools.web.web_search.providers.ddg_html import search_duckduckgo_html
from leagent.tools.web.web_search.protocol import SearchHit

logger = structlog.get_logger(__name__)

_CHALLENGE_MARKERS = (
    "please solve the challenge",
    "one last step",
    "cf-challenge",
    "captcha",
)


def _playwright_importable() -> bool:
    try:
        import importlib

        importlib.import_module("playwright.async_api")
        return True
    except ImportError:
        return False


def _decode_bing_url(href: str) -> str:
    """Unwrap Bing click-tracking URLs when present."""
    if "bing.com/ck/a" in href or "u=a1" in href:
        m = re.search(r"[?&]u=a1([^&]+)", href)
        if m:
            import base64

            raw = m.group(1) + "==="
            try:
                decoded = base64.urlsafe_b64decode(raw.encode("ascii")).decode("utf-8", "ignore")
                if decoded.startswith("http"):
                    return decoded
            except Exception:
                pass
    return href


def _query_tokens(query: str) -> list[str]:
    # Keep CJK runs and latin/number tokens of length >= 2.
    cjk = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    latin = [t.lower() for t in re.findall(r"[A-Za-z0-9]{2,}", query)]
    # Drop ultra-common filler words that cause false "relevant" matches.
    stop = {"the", "and", "for", "with", "from", "how", "to", "in", "of", "on", "a", "an"}
    latin = [t for t in latin if t not in stop]
    return cjk + latin


def hits_look_relevant(query: str, hits: list[SearchHit]) -> bool:
    """Heuristic: at least one result should share a query token in title/url."""
    tokens = _query_tokens(query)
    if not tokens or not hits:
        return False
    for h in hits:
        blob = f"{h.title} {h.url} {h.snippet}".lower()
        for tok in tokens:
            if tok.lower() in blob:
                return True
    return False


class BingPlaywrightWebSearchProvider:
    """Zero-config Bing search with DuckDuckGo HTML safety net."""

    name = "bing_playwright"

    def available(self) -> bool:
        return True

    def missing_credential_hint(self) -> str:
        return ""

    async def search(
        self,
        query: str,
        *,
        max_results: int,
        client: Any,
        cfg: Any,
    ) -> list[SearchHit]:
        # 1) Playwright Bing SERP
        if _playwright_importable():
            try:
                hits = await self._search_playwright(query, max_results=max_results)
                if hits and hits_look_relevant(query, hits):
                    return hits
                if hits:
                    logger.info(
                        "bing_playwright_irrelevant",
                        query=query[:80],
                        sample=(hits[0].title if hits else "")[:80],
                    )
            except Exception as e:
                logger.warning("bing_playwright_browser_failed", error=str(e))

        # 2) Bing RSS
        try:
            hits = await self._search_rss(client, query, max_results=max_results)
            if hits and hits_look_relevant(query, hits):
                return hits
            if hits:
                logger.info("bing_rss_irrelevant", query=query[:80], count=len(hits))
        except Exception as e:
            logger.warning("bing_rss_failed", error=str(e))

        # 3) DuckDuckGo HTML — reliable free fallback (esp. CJK)
        try:
            hits = await search_duckduckgo_html(
                client, query, max_results=max_results, source="duckduckgo_html"
            )
            if hits:
                logger.info("bing_floor_ddg_fallback", query=query[:80], count=len(hits))
            return hits
        except Exception as e:
            logger.warning("ddg_html_failed", error=str(e))
            return []

    async def _search_playwright(self, query: str, *, max_results: int) -> list[SearchHit]:
        from leagent.tools.web.browser_pool import BrowserPool

        pool = await BrowserPool.get_instance()
        search_url = (
            f"https://www.bing.com/search?q={quote_plus(query)}"
            f"&count={max(1, min(int(max_results), 25))}"
        )

        async with pool.get_page() as page:
            await page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45_000)
            for sel in (
                "#bnp_btn_accept",
                "button#bnp_btn_accept",
                "#bnp_container button[aria-label='Accept']",
            ):
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0 and await btn.is_visible(timeout=800):
                        await btn.click(timeout=1500)
                        break
                except Exception:
                    pass

            body_text = ""
            try:
                body_text = (await page.locator("body").inner_text(timeout=3000))[:800].lower()
            except Exception:
                pass
            if any(m in body_text for m in _CHALLENGE_MARKERS):
                logger.info("bing_playwright_challenge_detected")
                return []

            try:
                await page.wait_for_selector("li.b_algo, #b_results h2 a", timeout=10_000)
            except Exception:
                pass

            raw = await page.evaluate(
                """(limit) => {
                  const out = [];
                  const nodes = Array.from(
                    document.querySelectorAll('li.b_algo')
                  );
                  for (const el of nodes) {
                    if (out.length >= limit) break;
                    const a = el.querySelector('h2 a');
                    if (!a) continue;
                    const href = a.href || '';
                    if (!href.startsWith('http')) continue;
                    if (href.includes('bing.com/search') || href.includes('microsoft.com/')) continue;
                    const title = (a.innerText || a.textContent || '').trim();
                    const cap =
                      el.querySelector('.b_caption p') ||
                      el.querySelector('p') ||
                      el.querySelector('.b_algoSlug');
                    const snippet = (cap ? (cap.innerText || cap.textContent || '') : '').trim();
                    out.push({ title: title || href, url: href, snippet });
                  }
                  return out;
                }""",
                max_results,
            )

        if not isinstance(raw, list) or not raw:
            logger.warning("bing_playwright_empty", query=query[:80])
            return []

        out: list[SearchHit] = []
        for i, row in enumerate(raw[:max_results]):
            if not isinstance(row, dict):
                continue
            url = _decode_bing_url(str(row.get("url") or "").strip())
            if not url.startswith("http"):
                continue
            out.append(
                SearchHit(
                    title=str(row.get("title") or url),
                    url=url,
                    snippet=str(row.get("snippet") or "")[:500],
                    source="bing_playwright",
                    position=i + 1,
                )
            )
        return out

    async def _search_rss(
        self,
        client: Any,
        query: str,
        *,
        max_results: int,
    ) -> list[SearchHit]:
        url = f"https://www.bing.com/search?q={quote_plus(query)}&format=rss"
        r = await polite_get(client, url)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        items = root.findall("./channel/item")
        if not items:
            items = root.findall(".//{*}item")
        out: list[SearchHit] = []
        for item in items[:max_results]:
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")
            if title_el is None:
                title_el = item.find("{*}title")
            if link_el is None:
                link_el = item.find("{*}link")
            if desc_el is None:
                desc_el = item.find("{*}description")
            title = (title_el.text or "").strip() if title_el is not None else ""
            link = (link_el.text or "").strip() if link_el is not None else ""
            snippet = (desc_el.text or "").strip() if desc_el is not None else ""
            snippet = re.sub(r"<[^>]+>", " ", snippet)
            snippet = re.sub(r"\s+", " ", snippet).strip()
            if not link.startswith("http"):
                continue
            out.append(
                SearchHit(
                    title=title or link,
                    url=unquote(link),
                    snippet=snippet[:500],
                    source="bing_rss",
                    position=len(out) + 1,
                )
            )
        if out:
            logger.info("bing_rss_ok", count=len(out), query=query[:80])
        return out
