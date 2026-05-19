"""Pluggable web image search — shared types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ImageHit:
    """One image result suitable for follow-up ``web_image_download``."""

    url: str
    title: str
    thumbnail_url: str | None = None
    source_host: str | None = None


@runtime_checkable
class ImageSearchProvider(Protocol):
    async def search(
        self,
        query: str,
        *,
        max_results: int,
    ) -> list[ImageHit]:
        ...
