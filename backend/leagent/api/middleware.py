"""Custom ASGI middleware for LeAgent."""

from __future__ import annotations

import time
import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_access_logger = structlog.get_logger("leagent.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a unique ``X-Request-ID`` header into every request/response.

    If the client already provides the header it is preserved; otherwise a
    new UUID4 is generated.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:  # type: ignore[type-arg]
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        import structlog

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request and its response with timing information.

    Skips paths listed in *exclude_paths* (e.g. health/metrics endpoints that
    would otherwise flood the log).  Reads the ``request_id`` bound by
    ``RequestIDMiddleware`` from structlog context vars so each access log
    line carries the same correlation ID as other log records for that request.
    """

    _DEFAULT_EXCLUDE: frozenset[str] = frozenset({"/health", "/healthz", "/metrics"})

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: frozenset[str] | set[str] | None = None,
    ) -> None:
        super().__init__(app)
        self._exclude = frozenset(exclude_paths) if exclude_paths is not None else self._DEFAULT_EXCLUDE

    async def dispatch(self, request: Request, call_next: Callable) -> Response:  # type: ignore[type-arg]
        if request.url.path in self._exclude:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        status = response.status_code
        log_fn = _access_logger.warning if status >= 500 else (
            _access_logger.info if status < 400 else _access_logger.warning
        )
        log_fn(
            f"{request.method} {request.url.path}",
            method=request.method,
            path=request.url.path,
            status_code=status,
            duration_ms=duration_ms,
        )
        return response


class APIVersionMiddleware(BaseHTTPMiddleware):
    """Annotate versioned API responses and emit deprecation/sunset policy headers."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        deprecation_date: str = "",
        sunset_date: str = "",
        policy_url: str = "",
    ) -> None:
        super().__init__(app)
        self._deprecation_date = deprecation_date
        self._sunset_date = sunset_date
        self._policy_url = policy_url

    async def dispatch(self, request: Request, call_next: Callable) -> Response:  # type: ignore[type-arg]
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api/v1/") or path == "/api/v1":
            response.headers.setdefault("API-Version", "1")
            response.headers.setdefault("Deprecation", self._deprecation_date or "false")
            if self._sunset_date:
                response.headers.setdefault("Sunset", self._sunset_date)
            if self._policy_url:
                response.headers.setdefault(
                    "Link",
                    f'<{self._policy_url}>; rel="deprecation"; type="text/html"',
                )
        elif path.startswith("/api/v2/") or path == "/api/v2":
            response.headers.setdefault("API-Version", "2")
        return response


class ContentSizeLimitMiddleware:
    """Reject requests whose ``Content-Length`` exceeds *max_content_size* bytes."""

    def __init__(self, app: ASGIApp, max_content_size: int = 100 * 1024 * 1024) -> None:
        self.app = app
        self.max_content_size = max_content_size

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")

        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw)
            except (ValueError, TypeError):
                content_length = 0

            if content_length > self.max_content_size:
                response = _build_413_response(self.max_content_size)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def _build_413_response(max_bytes: int) -> Response:
    from fastapi.responses import JSONResponse

    max_mb = max_bytes / (1024 * 1024)
    return JSONResponse(
        status_code=413,
        content={
            "error": True,
            "error_code": "CONTENT_TOO_LARGE",
            "message": f"Request body exceeds the {max_mb:.0f} MB limit",
            "details": {"max_bytes": max_bytes},
        },
    )


# NOTE: The ``LicenseGateMiddleware`` and licensing fingerprint helpers from
# the ``leagent-win`` upgrade plan (M12) are intentionally NOT shipped on
# this branch. The license system is excluded per project owner request.
# When the licensing module is reintroduced, restore this section together
# with ``leagent.services.licensing``.
