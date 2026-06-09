"""Canonical error envelope shared by every API handler.

All error responses use this single shape so clients can rely on a stable
contract:

```json
{
  "error": true,
  "error_code": "HTTP_404",
  "message": "Not found",
  "details": {},
  "recovery": null,
  "request_id": "…"
}
```

Use :func:`build_error_payload` from exception handlers / ad-hoc error bodies and
:data:`default_error_responses` to document the envelope on routes.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from starlette.requests import Request


class ErrorResponse(BaseModel):
    """Stable error envelope returned by all handlers."""

    error: bool = Field(default=True, description="Always ``true`` for error responses.")
    error_code: str = Field(description="Machine-readable error code, e.g. ``HTTP_404``.")
    message: str = Field(description="Human-readable error message.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Structured, error-specific context."
    )
    recovery: dict[str, Any] | None = Field(
        default=None, description="Optional recommended recovery strategy."
    )
    request_id: str | None = Field(
        default=None, description="Correlation id (mirrors the ``X-Request-ID`` header)."
    )


def request_id_of(request: Request | None) -> str | None:
    """Return the request id bound by ``RequestIDMiddleware`` (or ``None``)."""
    if request is None:
        return None
    return getattr(request.state, "request_id", None)


def build_error_payload(
    *,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
    recovery: dict[str, Any] | None = None,
    request: Request | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Build a canonical error envelope dict.

    Pass either *request* (request id is read from its state) or an explicit
    *request_id*.
    """
    rid = request_id if request_id is not None else request_id_of(request)
    payload: dict[str, Any] = {
        "error": True,
        "error_code": error_code,
        "message": message,
        "details": details or {},
        "recovery": recovery,
    }
    if rid is not None:
        payload["request_id"] = rid
    return payload


# Document the error envelope on routes/routers via ``responses=...``.
default_error_responses: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse, "description": "Bad request"},
    401: {"model": ErrorResponse, "description": "Unauthorized"},
    403: {"model": ErrorResponse, "description": "Forbidden"},
    404: {"model": ErrorResponse, "description": "Not found"},
    422: {"model": ErrorResponse, "description": "Validation error"},
    500: {"model": ErrorResponse, "description": "Internal server error"},
}
