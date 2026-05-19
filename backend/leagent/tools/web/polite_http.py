"""Per-host request pacing, jitter, and retry for outbound web tools (single-machine friendly).

Serializes HTTP requests to the same hostname and enforces a minimum interval with random
jitter so bursts are less likely to trigger simple rate limits. Retries a few times on
429 / 5xx with ``Retry-After`` or exponential backoff. This is **not** CAPTCHA bypass or
fingerprint evasion; use ``HTTP(S)_PROXY`` if you need egress isolation.
"""

from __future__ import annotations

import asyncio
import email.utils
import random
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import httpx
import structlog

logger = structlog.get_logger(__name__)

_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_last_start_monotonic: dict[str, float] = {}


def _host_key(url: str) -> str:
    try:
        h = (urlparse(url).hostname or "").lower()
        return h or "_"
    except Exception:
        return "_"


def public_fetch_user_agent() -> str:
    from leagent.config.settings import get_settings

    wf = get_settings().web_fetch
    if (wf.user_agent or "").strip():
        return wf.user_agent.strip()
    ws = get_settings().web_search
    if (ws.user_agent or "").strip():
        return ws.user_agent.strip()
    return "LeAgent/1.0 (+local respectful-fetch)"


def _merge_headers(kwargs: dict[str, Any]) -> dict[str, Any]:
    headers = dict(kwargs.get("headers") or {})
    if not any(k.lower() == "user-agent" for k in headers):
        headers["User-Agent"] = public_fetch_user_agent()
    return headers


async def _sleep_interval(host: str) -> None:
    from leagent.config.settings import get_settings

    wf = get_settings().web_fetch
    if not wf.enabled:
        return
    min_s = max(0.0, float(wf.min_interval_ms) / 1000.0)
    jitter_s = max(0.0, float(wf.jitter_ms_max) / 1000.0)
    need = min_s + (random.uniform(0, jitter_s) if jitter_s > 0 else 0.0)
    now = time.monotonic()
    last = _last_start_monotonic.get(host, 0.0)
    elapsed = now - last
    if last > 0 and elapsed < need:
        await asyncio.sleep(need - elapsed)


def _parse_retry_after(resp: httpx.Response) -> float | None:
    raw = (resp.headers.get("Retry-After") or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return min(float(raw), 120.0)
    try:
        exp = email.utils.parsedate_to_datetime(raw)
        if exp is None:
            return None
        return min(max(0.0, exp.timestamp() - time.time()), 120.0)
    except Exception:
        return None


@asynccontextmanager
async def host_request_gate(url: str) -> AsyncIterator[None]:
    """Hold a per-host lock and enforce minimum spacing between request starts."""
    host = _host_key(url)
    lock = _locks[host]
    async with lock:
        await _sleep_interval(host)
        _last_start_monotonic[host] = time.monotonic()
        yield


async def polite_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Non-streaming HTTP request with per-host pacing and limited retries on 429 / 5xx."""
    from leagent.config.settings import get_settings

    wf = get_settings().web_fetch
    kwargs = dict(kwargs)
    kwargs["headers"] = _merge_headers(kwargs)
    max_retries = max(0, int(wf.max_retries))
    base_ms = max(50.0, float(wf.retry_backoff_base_ms))

    async with host_request_gate(url):
        attempt = 0
        while True:
            try:
                resp = await client.request(method, url, **kwargs)
            except httpx.TimeoutException:
                if attempt >= max_retries:
                    raise
                await asyncio.sleep((base_ms / 1000.0) * (2**attempt))
                attempt += 1
                continue

            if resp.status_code == 429 or resp.status_code in (500, 502, 503, 504):
                if attempt >= max_retries:
                    resp.raise_for_status()
                wait = _parse_retry_after(resp)
                if wait is None:
                    wait = min((base_ms / 1000.0) * (2**attempt), 60.0)
                logger.warning(
                    "polite_http_retry",
                    url=url[:120],
                    status=resp.status_code,
                    attempt=attempt,
                    sleep_s=wait,
                )
                await asyncio.sleep(wait)
                attempt += 1
                continue

            resp.raise_for_status()
            return resp


@asynccontextmanager
async def polite_stream(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> AsyncIterator[httpx.Response]:
    """Streaming GET/POST after host pacing (no automatic body-level retries)."""
    kwargs = dict(kwargs)
    kwargs["headers"] = _merge_headers(kwargs)
    async with host_request_gate(url):
        async with client.stream(method, url, **kwargs) as resp:
            yield resp


async def polite_get(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    return await polite_request(client, "GET", url, **kwargs)
