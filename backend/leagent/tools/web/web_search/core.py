from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any, Literal
from urllib.parse import quote, urlencode

import httpx

import structlog

from leagent.config.settings import WebSearchSettings
from leagent.tools.web.polite_http import polite_get
from leagent.tools.web.web_search.http import search_http_client

logger = structlog.get_logger(__name__)

Focus = Literal["auto", "arxiv", "wikipedia", "crossref", "pubmed", "general"]

_ARXIV_ID = re.compile(r"^(?:arxiv:)?(?P<id>\d{4}\.\d{4,5})(?P<ver>v\d+)?$", re.IGNORECASE)


def _normalize_focus(query: str, focus: Focus) -> str:
    if focus != "auto":
        return focus
    q0 = query.strip().split()[0] if query.strip() else ""
    q0 = q0.strip()
    if _ARXIV_ID.match(q0):
        return "arxiv"
    low = query.lower()
    if "arxiv" in low and ("abs/" in low or "/pdf/" in low):
        return "arxiv"
    return "general"


async def _arxiv_search(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict[str, Any]]:
    q = query.strip()
    m = _ARXIV_ID.match(q.split()[0] if q else "")
    if m:
        aid = m.group("id")
        if m.group("ver"):
            aid = f"{aid}{m.group('ver')}"
        url = f"http://export.arxiv.org/api/query?id_list={quote(aid)}"
    else:
        url = f"http://export.arxiv.org/api/query?search_query=all:{quote(q)}&start=0&max_results={max_results}"

    r = await polite_get(client, url)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out: list[dict[str, Any]] = []
    for ent in root.findall("a:entry", ns):
        title_el = ent.find("a:title", ns)
        id_el = ent.find("a:id", ns)
        summ_el = ent.find("a:summary", ns)
        title = (title_el.text or "").strip().replace("\n", " ")
        aid = (id_el.text or "").strip()
        snippet = (summ_el.text or "").strip().replace("\n", " ")[:500]
        out.append({"title": title, "url": aid, "snippet": snippet, "source": "arxiv_api"})
        if len(out) >= max_results:
            break
    return out


async def _wikipedia_opensearch(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict[str, Any]]:
    params = {"action": "opensearch", "search": query, "limit": max_results, "namespace": "0", "format": "json"}
    url = "https://en.wikipedia.org/w/api.php?" + urlencode(params)
    r = await polite_get(client, url)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) < 4:
        return []
    titles, descs, urls = data[1], data[2], data[3]
    out: list[dict[str, Any]] = []
    for i, title in enumerate(titles):
        if i >= max_results:
            break
        out.append(
            {
                "title": str(title),
                "url": str(urls[i]) if i < len(urls) else "",
                "snippet": str(descs[i]) if i < len(descs) else "",
                "source": "wikipedia_opensearch",
            }
        )
    return out


async def _crossref_works(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict[str, Any]]:
    url = f"https://api.crossref.org/works?query={quote(query)}&rows={max_results}"
    r = await polite_get(client, url)
    r.raise_for_status()
    payload = r.json()
    items = (payload.get("message") or {}).get("items") or []
    out: list[dict[str, Any]] = []
    for it in items[:max_results]:
        title_list = it.get("title") or []
        title = title_list[0] if title_list else it.get("DOI", "untitled")
        doi = it.get("DOI", "")
        url_u = f"https://doi.org/{doi}" if doi else ""
        snippet = ""
        if it.get("container-title"):
            snippet = str(it["container-title"][0])
        if it.get("issued", {}).get("date-parts"):
            snippet = f"{snippet} ({it['issued']['date-parts'][0][0]})".strip()
        out.append({"title": str(title), "url": url_u, "snippet": snippet, "source": "crossref"})
    return out


async def _pubmed_esearch(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict[str, Any]]:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmax": max_results, "retmode": "json"}
    r = await polite_get(client, f"{base}?{urlencode(params)}")
    r.raise_for_status()
    data = r.json()
    idlist = (data.get("esearchresult") or {}).get("idlist") or []
    out: list[dict[str, Any]] = []
    for pmid in idlist[:max_results]:
        out.append(
            {
                "title": f"PubMed {pmid}",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "snippet": "",
                "source": "pubmed_esearch",
            }
        )
    return out


async def _duckduckgo_lite(client: httpx.AsyncClient, query: str, max_results: int) -> list[dict[str, Any]]:
    url = f"https://lite.duckduckgo.com/lite/?{urlencode({'q': query})}"
    r = await polite_get(client, url)
    r.raise_for_status()
    text = r.text
    out: list[dict[str, Any]] = []
    for m in re.finditer(
        r'<a[^>]*class="[^"]*result-link[^"]*"[^>]*href="([^"]+)"[^>]*>([^<]*)</a>',
        text,
        re.IGNORECASE,
    ):
        href, title = m.group(1), (m.group(2) or "").strip()
        if href.startswith("//"):
            href = "https:" + href
        if not href.startswith("http"):
            continue
        out.append({"title": title or href, "url": href, "snippet": "", "source": "duckduckgo_lite"})
        if len(out) >= max_results:
            break
    return out


async def _searxng(client: httpx.AsyncClient, base: str, query: str, max_results: int) -> list[dict[str, Any]]:
    base = base.rstrip("/")
    url = f"{base}/search?{urlencode({'q': query, 'format': 'json'})}"
    r = await polite_get(client, url)
    r.raise_for_status()
    data = r.json()
    results = data.get("results") or []
    out: list[dict[str, Any]] = []
    for row in results[:max_results]:
        out.append(
            {
                "title": str(row.get("title") or ""),
                "url": str(row.get("url") or ""),
                "snippet": str(row.get("content") or ""),
                "source": "searxng",
            }
        )
    return out


async def _bing_web(client: httpx.AsyncClient, cfg: WebSearchSettings, query: str, max_results: int) -> list[dict[str, Any]]:
    key = (cfg.bing_api_key or "").strip()
    if not key:
        return []
    url = f"{cfg.bing_endpoint.rstrip('/')}?{urlencode({'q': query, 'count': max_results})}"
    r = await polite_get(client, url, headers={"Ocp-Apim-Subscription-Key": key})
    r.raise_for_status()
    data = r.json()
    web_pages = ((data.get("webPages") or {}).get("value")) or []
    out: list[dict[str, Any]] = []
    for row in web_pages[:max_results]:
        out.append(
            {
                "title": str(row.get("name") or ""),
                "url": str(row.get("url") or ""),
                "snippet": str(row.get("snippet") or ""),
                "source": "bing",
            }
        )
    return out


def _empty_result_guidance(*, focus_resolved: str, had_general_fallback: bool) -> str:
    base = (
        "No hits returned. You can still help: answer from prior context or attachments; ask the user for a "
        "direct https URL and use web_scraper if page text is needed; or narrow the query."
    )
    if focus_resolved in ("arxiv", "wikipedia", "crossref", "pubmed"):
        return base + " Academic APIs are free and need no API key—retry with a shorter query or different focus."
    if had_general_fallback:
        return (
            base + " Broad web search may be blocked or empty without Bing/SearXNG keys; set WEB_SEARCH_BING_API_KEY "
            "or WEB_SEARCH_SEARXNG_BASE_URL in Settings, or rely on user-provided links + web_scraper."
        )
    return base


async def run_web_search(
    *,
    query: str,
    focus: Focus,
    max_results: int,
    cfg: WebSearchSettings,
) -> dict[str, Any]:
    resolved = _normalize_focus(query, focus)
    max_results = max(1, min(max_results, 25))
    degraded_reasons: list[str] = []
    had_general_fallback = False

    async with search_http_client(user_agent=cfg.user_agent, timeout_sec=cfg.timeout_sec) as client:
        results: list[dict[str, Any]] = []
        strategy = ""

        async def _try_focused(name: str, coro: Any) -> bool:
            nonlocal results, strategy
            try:
                results = await coro
                strategy = name
                return True
            except (httpx.HTTPError, ET.ParseError, ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
                logger.warning("web_search_focused_failed", strategy=name, error=str(e))
                degraded_reasons.append(f"{name}:{e!s}")
                results = []
                strategy = name + "_failed"
                return False

        try:
            if resolved == "arxiv":
                await _try_focused("arxiv_api", _arxiv_search(client, query, max_results))
            elif resolved == "wikipedia":
                await _try_focused("wikipedia_opensearch", _wikipedia_opensearch(client, query, max_results))
            elif resolved == "crossref":
                await _try_focused("crossref_api", _crossref_works(client, query, max_results))
            elif resolved == "pubmed":
                await _try_focused("pubmed_esearch", _pubmed_esearch(client, query, max_results))
            else:
                prov = cfg.provider
                bing_key = (cfg.bing_api_key or "").strip()
                searx_base = (cfg.searxng_base_url or "").strip()

                if prov == "bing" and not bing_key:
                    degraded_reasons.append("WEB_SEARCH_BING_API_KEY unset; using duckduckgo_lite.")
                    prov = "duckduckgo_lite"
                    had_general_fallback = True
                if prov == "searxng" and not searx_base:
                    degraded_reasons.append("WEB_SEARCH_SEARXNG_BASE_URL unset; using duckduckgo_lite.")
                    prov = "duckduckgo_lite"
                    had_general_fallback = True

                async def _run_general(primary: str) -> None:
                    nonlocal results, strategy
                    if primary == "searxng":
                        results = await _searxng(client, searx_base, query, max_results)
                        strategy = "searxng"
                    elif primary == "bing":
                        results = await _bing_web(client, cfg, query, max_results)
                        strategy = "bing_api"
                    else:
                        results = await _duckduckgo_lite(client, query, max_results)
                        strategy = "duckduckgo_lite"

                try:
                    await _run_general(prov)
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
                    logger.warning("web_search_general_failed", provider=prov, error=str(e))
                    degraded_reasons.append(f"{prov}:{e!s}")
                    if prov != "duckduckgo_lite":
                        had_general_fallback = True
                        try:
                            results = await _duckduckgo_lite(client, query, max_results)
                            strategy = "duckduckgo_lite"
                            degraded_reasons.append("Fell back to duckduckgo_lite after primary failure.")
                        except (httpx.HTTPError, ValueError) as e2:
                            results = []
                            strategy = "duckduckgo_lite_failed"
                            degraded_reasons.append(f"duckduckgo_lite:{e2!s}")
                    else:
                        results = []
                        strategy = "duckduckgo_lite_failed"
        except Exception as e:
            logger.warning("web_search_unexpected", error=str(e))
            degraded_reasons.append(f"unexpected:{e!s}")
            results = []
            strategy = strategy or "error"

    degraded = len(results) == 0
    next_step = (
        "For full page text, call web_scraper on a chosen https URL when JS rendering is required; "
        "for arxiv PDFs prefer the abs page URL then scrape or download PDF if policy allows."
    )
    if not results:
        next_step = _empty_result_guidance(focus_resolved=resolved, had_general_fallback=had_general_fallback)

    return {
        "query": query,
        "focus_requested": focus,
        "focus_resolved": resolved,
        "strategy": strategy,
        "count": len(results),
        "results": results,
        "degraded": degraded,
        "degraded_reasons": degraded_reasons,
        "next_step": next_step,
    }
