"""In-process Streamable HTTP mock for :class:`leagent.mcp.client.MCPClient`.

Exposes a single MCP endpoint (``POST /mcp``) that speaks the standard
Streamable HTTP transport. It exercises both reply shapes the client must
handle:

- ``initialize`` returns a plain ``application/json`` body and stamps an
  ``Mcp-Session-Id`` response header.
- every other request replies with a ``text/event-stream`` body carrying one
  ``event: message`` block, so the SSE parsing path is covered.

The ``Authorization`` header sent by the client is echoed into the
``initialize`` result so tests can assert custom headers propagate.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import time
from collections.abc import AsyncIterator

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from tests.fixtures.mcp_mock_protocol import handle_mcp_message

_SESSION_ID = "mock-session-123"


async def _mcp_endpoint(request: Request) -> Response:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )

    method = body.get("method")
    out = handle_mcp_message(body)

    # Notifications: 202 Accepted, no body.
    if out is None:
        return Response(status_code=202)

    # Echo the auth header into the initialize result so tests can assert
    # custom headers reached the server.
    if method == "initialize" and "result" in out:
        out["result"]["_echo_authorization"] = request.headers.get("Authorization", "")
        return JSONResponse(out, headers={"Mcp-Session-Id": _SESSION_ID})

    # All other responses go out as an SSE ``message`` event.
    sse_body = f"event: message\ndata: {json.dumps(out)}\n\n"
    return Response(
        content=sse_body,
        media_type="text/event-stream",
        headers={"Mcp-Session-Id": _SESSION_ID},
    )


def build_streamable_app() -> Starlette:
    return Starlette(routes=[Route("/mcp", _mcp_endpoint, methods=["POST"])])


async def _wait_tcp(host: str, port: int, *, timeout_sec: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.0)
            writer.close()
            await writer.wait_closed()
            return
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
            await asyncio.sleep(0.05)
    raise TimeoutError(f"TCP {host}:{port} did not accept connections within {timeout_sec}s")


@contextlib.asynccontextmanager
async def mcp_streamable_http_server() -> AsyncIterator[str]:
    """Bind ``127.0.0.1:0``, run uvicorn until context exits, yield the endpoint URL."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()

    app = build_streamable_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        await _wait_tcp("127.0.0.1", port)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        await task
