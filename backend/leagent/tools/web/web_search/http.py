from __future__ import annotations

import httpx


def search_http_client(*, user_agent: str, timeout_sec: float) -> httpx.AsyncClient:
    """Async HTTP client that honors ``HTTP_PROXY`` / ``HTTPS_PROXY`` / ``ALL_PROXY``."""
    return httpx.AsyncClient(
        timeout=timeout_sec,
        follow_redirects=True,
        headers={"User-Agent": user_agent},
        trust_env=True,
    )
