"""Rate limit middleware stub — no-op for local deployment."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    """No-op rate limit middleware for standalone local deployment."""

    async def dispatch(self, request, call_next):
        return await call_next(request)
