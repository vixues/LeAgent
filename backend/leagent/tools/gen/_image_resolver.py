"""Shared image resolution utility for document generation tools.

Resolves image sources (file paths, base64, URLs) into bytes suitable for
embedding in PDF, Word, and PowerPoint documents. Includes optional resizing
to keep document file sizes manageable.
"""

from __future__ import annotations

import base64
import io
import mimetypes
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB hard limit
_DEFAULT_MAX_DIMENSION = 2048  # px — downsample larger images


class ResolvedImage:
    """Container for a resolved image ready for embedding."""

    __slots__ = ("data", "mime", "width", "height", "source_desc")

    def __init__(
        self,
        data: bytes,
        mime: str = "image/png",
        width: int | None = None,
        height: int | None = None,
        source_desc: str = "",
    ) -> None:
        self.data = data
        self.mime = mime
        self.width = width
        self.height = height
        self.source_desc = source_desc

    @property
    def stream(self) -> io.BytesIO:
        return io.BytesIO(self.data)

    @property
    def suffix(self) -> str:
        ext = mimetypes.guess_extension(self.mime)
        return ext or ".png"


def resolve_image(
    *,
    path: str | None = None,
    base64_data: str | None = None,
    mime: str | None = None,
    url: str | None = None,
    max_dimension: int = _DEFAULT_MAX_DIMENSION,
    max_bytes: int = _MAX_IMAGE_BYTES,
) -> ResolvedImage | None:
    """Resolve an image from one of the supported sources.

    Priority: base64_data > path > url
    Returns None if the image cannot be resolved.
    """
    data: bytes | None = None
    resolved_mime = mime or "image/png"
    source_desc = ""

    if base64_data:
        try:
            if "," in base64_data[:80]:
                base64_data = base64_data.split(",", 1)[1]
            data = base64.b64decode(base64_data)
            source_desc = "base64"
        except Exception:
            logger.warning("image_resolve_base64_failed")
            return None
    elif path:
        p = Path(path)
        if not p.is_file():
            logger.warning("image_resolve_path_not_found", path=path)
            return None
        data = p.read_bytes()
        source_desc = str(p.name)
        guessed = mimetypes.guess_type(str(p))[0]
        if guessed:
            resolved_mime = guessed
    elif url:
        data = _download_url(url, max_bytes=max_bytes)
        source_desc = url[:80]
        if data is None:
            return None
        guessed = mimetypes.guess_type(url)[0]
        if guessed:
            resolved_mime = guessed

    if data is None:
        return None

    if len(data) > max_bytes:
        logger.warning("image_too_large", size=len(data), max=max_bytes)
        return None

    width, height = None, None
    try:
        data, width, height = _maybe_resize(data, max_dimension)
    except Exception:
        logger.debug("image_resize_skipped")

    return ResolvedImage(
        data=data,
        mime=resolved_mime,
        width=width,
        height=height,
        source_desc=source_desc,
    )


def _download_url(url: str, *, max_bytes: int, timeout: float = 15.0) -> bytes | None:
    """Download an image URL synchronously with size guard."""
    try:
        import httpx

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            if len(resp.content) > max_bytes:
                logger.warning("image_url_too_large", url=url[:80], size=len(resp.content))
                return None
            return resp.content
    except Exception:
        logger.warning("image_url_download_failed", url=url[:80])
        return None


def _maybe_resize(data: bytes, max_dim: int) -> tuple[bytes, int | None, int | None]:
    """Resize image if either dimension exceeds max_dim. Returns (data, w, h)."""
    try:
        from PIL import Image
    except ImportError:
        return data, None, None

    img = Image.open(io.BytesIO(data))
    w, h = img.size

    if w <= max_dim and h <= max_dim:
        return data, w, h

    ratio = min(max_dim / w, max_dim / h)
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    buf = io.BytesIO()
    fmt = "PNG" if img.mode == "RGBA" else "JPEG"
    img.save(buf, format=fmt, quality=85, optimize=True)
    return buf.getvalue(), new_w, new_h
