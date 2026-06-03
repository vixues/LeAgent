"""Image generation result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ImageGenResult:
    """Result from an image generation provider."""

    success: bool = True
    b64_json: str | None = None
    url: str | None = None
    mime: str = "image/png"
    revised_prompt: str | None = None
    model: str = ""
    provider: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
