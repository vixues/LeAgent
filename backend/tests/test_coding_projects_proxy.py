"""Unit tests for ``forward_http`` against an upstream FastAPI app.

We can't easily ship a network listener inside the test runner, so
the test stands up a tiny FastAPI app **inside the same process**
and dispatches requests against it directly via ``httpx.ASGITransport``
when the test mode is "asgi-only". For the integration path that
uses real sockets we bind a uvicorn server on an ephemeral port and
send the proxied request through ``forward_http``.

This keeps the behaviour test honest without making CI flaky.
"""

from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from starlette.requests import Request

from leagent.services.coding_projects.proxy import forward_http


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@asynccontextmanager
async def _serve_upstream(port: int) -> AsyncIterator[None]:
    import uvicorn

    upstream = FastAPI()

    @upstream.get("/echo")
    async def echo() -> dict[str, str]:
        return {"hello": "world"}

    @upstream.get("/headers")
    async def headers(request: Request) -> dict[str, str]:
        return dict(request.headers)

    config = uvicorn.Config(
        upstream, host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    # Wait until the server is actually accepting connections.
    for _ in range(40):
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"http://127.0.0.1:{port}/echo")
                if r.status_code == 200:
                    break
        except httpx.RequestError:
            await asyncio.sleep(0.1)
    try:
        yield
    finally:
        server.should_exit = True
        await task


def _fake_request(path: str, method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [
            (b"host", b"leagent.local"),
            (b"x-test", b"yes"),
            (b"connection", b"keep-alive"),  # hop-by-hop, must be stripped
        ],
        "client": ("127.0.0.1", 12345),
    }

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_forward_http_proxies_simple_get() -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        pytest.skip("uvicorn not available; pip install uvicorn")

    port = _free_port()
    async with _serve_upstream(port):
        request = _fake_request("/echo")
        response = await forward_http(
            request,
            target_base=f"http://127.0.0.1:{port}",
            sub_path="echo",
        )
        # StreamingResponse: read the body iter into bytes.
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        assert response.status_code == 200
        assert body == b'{"hello":"world"}'
        # Hop-by-hop response headers should be stripped from the
        # outgoing response; the proxy stamps a marker header.
        assert response.headers.get("x-coding-projects-proxy") == "1"


@pytest.mark.asyncio
async def test_forward_http_strips_hop_by_hop_request_headers() -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        pytest.skip("uvicorn not available; pip install uvicorn")

    port = _free_port()
    async with _serve_upstream(port):
        request = _fake_request("/headers")
        response = await forward_http(
            request,
            target_base=f"http://127.0.0.1:{port}",
            sub_path="headers",
        )
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        import json

        echoed = json.loads(body)
        assert "connection" not in {k.lower() for k in echoed}
        assert "host" not in {k.lower() for k in echoed}
        assert echoed.get("x-test") == "yes"
        assert echoed.get("x-forwarded-host") is not None
