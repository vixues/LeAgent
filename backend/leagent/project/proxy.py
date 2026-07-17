"""HTTP and WebSocket reverse-proxy helpers.

The browser cannot reach a dev server bound to ``127.0.0.1:39042`` on
the user's machine when the front-end app runs from a remote origin,
and even on the same machine it would mix origins (CORS, cookies,
HMR) in unpleasant ways. So instead we expose a stable, signed
endpoint under the existing FastAPI app and forward bytes from
there:

* ``GET /api/v1/coding-projects/{id}/preview/{path:path}`` →
  ``GET http://127.0.0.1:<port>/<path>`` (similarly for POST/PUT
  /...)
* ``WS  /api/v1/coding-projects/{id}/preview-ws/{path:path}`` →
  ``ws://127.0.0.1:<port>/<path>`` (for Vite HMR and FastAPI WS
  endpoints)

Implementation notes:

* HTTP forwarding uses a minimal raw loopback HTTP/1.0 client so
  hop-by-hop headers stripped from the browser request are not
  reintroduced by a high-level client before reaching the dev server.
  The response body is streamed back to Starlette.
* WebSocket forwarding uses the ``websockets`` library which is
  already a dependency. We pump frames in both directions and close
  the proxy side as soon as either side finishes.
* The hop-by-hop headers are stripped on both legs so the upstream
  sees a clean request and the browser doesn't get confused by
  ``Transfer-Encoding`` collisions. The browser-facing ``Host`` is
  replaced with the loopback authority of the dev server
  (``127.0.0.1:<port>``) so host-checking dev servers (e.g. Vite's
  ``server.allowedHosts``) accept the proxied request.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Iterable, Mapping
from urllib.parse import urlsplit

import structlog
from fastapi import Request, WebSocket
from starlette.responses import StreamingResponse

logger = structlog.get_logger(__name__)


_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)


def _filter_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _HOP_BY_HOP:
            continue
        out[key] = value
    return out


def _filter_response_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers:
        if key.lower() in _HOP_BY_HOP:
            continue
        out[key] = value
    out["x-coding-projects-proxy"] = "1"
    out.setdefault("cache-control", "no-store")
    return out


def _path_and_query(url: str) -> str:
    """Return the origin-form target for an HTTP request line."""
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path


def _encode_header_line(key: str, value: str) -> bytes:
    """Encode one sanitized HTTP header line for the loopback upstream."""
    return f"{key}: {value}\r\n".encode("latin-1", errors="ignore")


async def _open_loopback_http(
    *,
    method: str,
    target_url: str,
    headers: Mapping[str, str],
    body: bytes | None,
) -> tuple[int, dict[str, str], bytes, asyncio.StreamReader, asyncio.StreamWriter]:
    """Send an HTTP/1.0 request without client-added hop-by-hop headers.

    High-level HTTP clients correctly add protocol-required headers
    like ``Host`` and connection management headers. For this proxy,
    those headers were explicitly filtered because they belong to the
    browser-to-LeAgent hop, not the LeAgent-to-dev-server hop.
    A raw loopback request keeps that contract exact and still lets us
    stream the response body back to Starlette.

    The upstream leg carries its own loopback ``Host`` (e.g.
    ``127.0.0.1:39042``): dev servers with host checking (Vite's
    ``server.allowedHosts``) reject requests whose Host is missing or
    unknown, and loopback authorities are always in their allowlist.
    """
    parsed = urlsplit(target_url)
    if parsed.scheme != "http":
        raise ValueError("coding project HTTP proxy only supports http upstreams")
    if not parsed.hostname:
        raise ValueError("target_url must include a hostname")

    port = parsed.port or 80
    reader, writer = await asyncio.open_connection(parsed.hostname, port)

    request_head = [
        f"{method.upper()} {_path_and_query(target_url)} HTTP/1.0\r\n".encode("ascii"),
        _encode_header_line("host", f"{parsed.hostname}:{port}"),
    ]
    for key, value in headers.items():
        if key.lower() in _HOP_BY_HOP:
            continue
        request_head.append(_encode_header_line(key, value))
    if body:
        request_head.append(_encode_header_line("content-length", str(len(body))))
    request_head.append(b"\r\n")
    writer.write(b"".join(request_head))
    if body:
        writer.write(body)
    await writer.drain()

    raw_head = await reader.readuntil(b"\r\n\r\n")
    head_text = raw_head.decode("iso-8859-1", errors="replace")
    lines = head_text.split("\r\n")
    status_line = lines[0] if lines else ""
    try:
        status_code = int(status_line.split(" ", 2)[1])
    except (IndexError, ValueError):
        status_code = HTTPStatus.BAD_GATEWAY

    response_headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        response_headers[key.strip()] = value.strip()

    return status_code, response_headers, b"", reader, writer


async def forward_http(
    request: Request,
    *,
    target_base: str,
    sub_path: str,
    timeout: float = 30.0,
) -> StreamingResponse:
    """Proxy ``request`` to ``target_base/sub_path`` and stream the response.

    ``target_base`` is a fully-qualified URL like
    ``http://127.0.0.1:39042``. ``sub_path`` is the path portion
    without leading slash (the FastAPI route declares it as
    ``{path:path}``).
    """
    query = request.url.query
    target_url = f"{target_base.rstrip('/')}/{sub_path.lstrip('/')}"
    if query:
        target_url = f"{target_url}?{query}"

    headers = _filter_request_headers(dict(request.headers))
    headers["x-forwarded-host"] = request.url.hostname or ""
    headers["x-forwarded-proto"] = request.url.scheme or "http"

    body = await request.body() if request.method.upper() not in {"GET", "HEAD"} else None

    try:
        status_code, upstream_headers, first_body, reader, writer = await asyncio.wait_for(
            _open_loopback_http(
                method=request.method,
                target_url=target_url,
                headers=headers,
                body=body,
            ),
            timeout=timeout,
        )
    except (OSError, asyncio.TimeoutError, ValueError) as exc:
        logger.warning(
            "coding_projects_proxy_upstream_error",
            target=target_url,
            error=str(exc),
        )
        raise

    response_headers = _filter_response_headers(upstream_headers.items())

    async def _body_iter():
        try:
            if first_body:
                yield first_body
            while chunk := await reader.read(65536):
                yield chunk
        finally:
            writer.close()
            await writer.wait_closed()

    return StreamingResponse(
        _body_iter(),
        status_code=status_code,
        headers=response_headers,
        media_type=upstream_headers.get("content-type"),
    )


async def forward_websocket(
    client_ws: WebSocket,
    *,
    target_url: str,
    subprotocols: Iterable[str] = (),
) -> None:
    """Bridge a client WebSocket to ``target_url``.

    The bridge auto-detects text vs binary frames and pumps in both
    directions. It closes both ends when either side disconnects.
    """
    try:
        from websockets.client import connect as ws_connect
    except ImportError as exc:  # pragma: no cover — websockets is a leagent dep
        raise RuntimeError(
            "websockets package is required for WS proxying"
        ) from exc

    accepted_subprotocol: str | None = None
    if subprotocols:
        await client_ws.accept(subprotocol=next(iter(subprotocols), None))
    else:
        await client_ws.accept()

    extra_headers = {
        "x-forwarded-for": client_ws.client.host if client_ws.client else "",
    }

    try:
        async with ws_connect(
            target_url,
            subprotocols=list(subprotocols) or None,
            extra_headers=extra_headers,
            open_timeout=10.0,
            ping_interval=20,
            close_timeout=2.0,
            max_size=None,
        ) as upstream:
            accepted_subprotocol = upstream.subprotocol  # noqa: F841 — debug

            async def client_to_upstream() -> None:
                try:
                    while True:
                        msg = await client_ws.receive()
                        if msg["type"] == "websocket.disconnect":
                            return
                        if (text := msg.get("text")) is not None:
                            await upstream.send(text)
                        elif (data := msg.get("bytes")) is not None:
                            await upstream.send(data)
                except Exception:  # noqa: BLE001
                    return

            async def upstream_to_client() -> None:
                try:
                    async for frame in upstream:
                        if isinstance(frame, str):
                            await client_ws.send_text(frame)
                        else:
                            await client_ws.send_bytes(frame)
                except Exception:  # noqa: BLE001
                    return

            await asyncio.gather(
                client_to_upstream(),
                upstream_to_client(),
                return_exceptions=True,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "coding_projects_proxy_ws_error",
            target=target_url,
            error=str(exc),
        )
    finally:
        try:
            await client_ws.close()
        except Exception:  # noqa: BLE001
            pass
