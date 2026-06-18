"""Provider-level result types for media generation HTTP clients."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResult:
    """Result from a vendor image/media generation HTTP client."""

    success: bool = True
    b64_json: str | None = None
    url: str | None = None
    mime: str = "image/png"
    revised_prompt: str | None = None
    model: str = ""
    provider: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# Backward-compatible alias for chat / domain-model paths.
ImageGenResult = ProviderResult

__all__ = ["ImageGenResult", "ProviderResult"]
