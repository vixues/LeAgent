"""In-process HTTP mock exposing ``POST /rpc`` for :class:`leagent.mcp.client.MCPClient`."""

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
from starlette.responses import JSONResponse
from starlette.routing import Route

from tests.fixtures.mcp_mock_protocol import handle_mcp_message


async def _rpc_endpoint(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )
    if not isinstance(body, dict):
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}},
            status_code=400,
        )
    out = handle_mcp_message(body)
    if out is None:
        return JSONResponse({}, status_code=200)
    return JSONResponse(out)


def build_mcp_rpc_starlette_app() -> Starlette:
    return Starlette(routes=[Route("/rpc", _rpc_endpoint, methods=["POST"])])


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
async def mcp_rpc_http_server() -> AsyncIterator[int]:
    """Bind ``127.0.0.1:0``, run uvicorn until context exits, yield port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()

    app = build_mcp_rpc_starlette_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        await _wait_tcp("127.0.0.1", port)
        yield port
    finally:
        server.should_exit = True
        await task
