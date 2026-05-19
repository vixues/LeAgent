"""Google Custom Search JSON API — image search (searchType=image)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from leagent.tools.web.image_search.protocol import ImageHit
from leagent.tools.web.polite_http import polite_get

logger = structlog.get_logger(__name__)


async def search_google_cse(
    query: str,
    *,
    api_key: str,
    cx: str,
    max_results: int,
    endpoint: str = "https://www.googleapis.com/customsearch/v1",
) -> list[ImageHit]:
    """Return HTTPS image URLs from Google Programmable Search (image mode).

    Requires a Search Engine configured for **Image search** in the CSE control panel.
    """
    q = (query or "").strip()
    if not q:
        return []

    # API allows num 1–10 per request
    num = max(1, min(int(max_results), 10))
    params: dict[str, Any] = {
        "key": api_key,
        "cx": cx,
        "q": q,
        "searchType": "image",
        "num": num,
        "safe": "active",
    }
    url = f"{endpoint.rstrip('/')}?{urlencode(params)}"

    async with httpx.AsyncClient(timeout=30.0, trust_env=True) as client:
        try:
            resp = await polite_get(client, url)
        except httpx.HTTPError as exc:
            r = getattr(exc, "response", None)
            detail = r.text[:500] if r is not None else ""
            logger.warning(
                "google_cse_http_error",
                status=r.status_code if r is not None else 0,
                detail=detail,
            )
            raise ValueError(
                f"Google Custom Search request failed ({r.status_code if r is not None else 'unknown'}): "
                f"{detail or exc!s}"
            ) from exc

        data = resp.json()

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []

    out: list[ImageHit] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        if not isinstance(link, str) or not link.startswith("https://"):
            continue
        title = item.get("title") if isinstance(item.get("title"), str) else ""
        thumb = None
        img_obj = item.get("image")
        if isinstance(img_obj, dict):
            tl = img_obj.get("thumbnailLink")
            if isinstance(tl, str) and tl.startswith("https://"):
                thumb = tl
        display = item.get("displayLink")
        host = display if isinstance(display, str) else None
        out.append(
            ImageHit(
                url=link,
                title=title or link,
                thumbnail_url=thumb,
                source_host=host,
            )
        )

    return out
