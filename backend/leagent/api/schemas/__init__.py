"""Per-domain API DTOs (request/response models).

Schemas live here — not inline in routers — so contracts are stable, reusable,
and discoverable. Import the shared error envelope from :mod:`.errors`.
"""

from __future__ import annotations

from leagent.api.schemas.errors import (
    ErrorResponse,
    default_error_responses,
)

__all__ = [
    "ErrorResponse",
    "default_error_responses",
]
