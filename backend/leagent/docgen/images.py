"""Image resolution for document / deck generation.

Resolves image sources into bytes suitable for embedding in PDF, Word, and
PowerPoint. Supported inputs (priority order):

1. ``base64_data`` — raw or ``data:`` URI
2. ``file_id`` — managed artifact UUID (also extracted from preview / download
   URLs and bare-UUID ``path`` / ``url`` values)
3. ``path`` — local filesystem path
4. ``url`` — remote ``http(s)://`` download

Managed ``file_id`` values resolve via a sync scan of
``LEAGENT_HOME/working/uploads`` (and knowledge storage) so renderers stay
synchronous. Includes optional downsampling to keep file sizes manageable.
"""

from __future__ import annotations

import base64
import io
import mimetypes
import re
from pathlib import Path
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB hard limit
_DEFAULT_MAX_DIMENSION = 2048  # px — downsample larger images

# /api/v1/files/{uuid}/preview|download|content (optional query string)
_FILE_API_RE = re.compile(
    r"(?:^|/)(?:api/v\d+/)?files/"
    r"(?P<fid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
    r"(?:/(?:preview|download|content))?",
    re.IGNORECASE,
)
_BARE_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}


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


def extract_file_id(*candidates: str | None) -> str | None:
    """Pull a managed file UUID out of a file_id, path, or URL-like string."""
    for raw in candidates:
        if not raw or not isinstance(raw, str):
            continue
        text = raw.strip()
        if not text:
            continue
        # Strip query/fragment for matching.
        bare = text.split("?", 1)[0].split("#", 1)[0].strip()
        m = _FILE_API_RE.search(bare)
        if m:
            return m.group("fid").lower()
        # Path basename may be ``{uuid}_{filename}``.
        name = Path(bare).name
        if "_" in name:
            prefix = name.split("_", 1)[0]
            if _BARE_UUID_RE.match(prefix):
                return prefix.lower()
        if _BARE_UUID_RE.match(bare) or _BARE_UUID_RE.match(name):
            return (bare if _BARE_UUID_RE.match(bare) else name).lower()
    return None


def resolve_image(
    *,
    path: str | None = None,
    base64_data: str | None = None,
    mime: str | None = None,
    url: str | None = None,
    file_id: str | None = None,
    max_dimension: int = _DEFAULT_MAX_DIMENSION,
    max_bytes: int = _MAX_IMAGE_BYTES,
) -> ResolvedImage | None:
    """Resolve an image from one of the supported sources.

    Priority: base64_data > file_id (incl. embedded in path/url) > path > url.
    Returns None if the image cannot be resolved.
    """
    data: bytes | None = None
    resolved_mime = mime or "image/png"
    source_desc = ""

    if base64_data:
        try:
            payload = base64_data
            if "," in payload[:80]:
                payload = payload.split(",", 1)[1]
            data = base64.b64decode(payload)
            source_desc = "base64"
        except Exception:
            logger.warning("image_resolve_base64_failed")
            return None
    else:
        fid = extract_file_id(file_id, path, url)
        if fid:
            found = _resolve_managed_file(fid)
            if found is not None:
                data, resolved_mime, source_desc = found
            elif file_id or (path and not Path(path).is_file()):
                # Explicit file_id, or a path/URL that only carried a UUID /
                # preview reference and is not a real filesystem path.
                logger.warning("image_resolve_file_id_not_found", file_id=fid)
                if file_id or not (url and url.startswith(("http://", "https://"))):
                    return None

        if data is None and path:
            p = Path(path)
            if not p.is_file():
                logger.warning("image_resolve_path_not_found", path=path)
                return None
            data = p.read_bytes()
            source_desc = str(p.name)
            guessed = mimetypes.guess_type(str(p))[0]
            if guessed:
                resolved_mime = guessed

        if data is None and url:
            if url.startswith(("http://", "https://")):
                data = _download_url(url, max_bytes=max_bytes)
                source_desc = url[:80]
                if data is None:
                    return None
                guessed = mimetypes.guess_type(url.split("?", 1)[0])[0]
                if guessed:
                    resolved_mime = guessed
            else:
                # Relative preview path that failed file_id lookup.
                logger.warning("image_resolve_url_unsupported", url=url[:80])
                return None

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


def _resolve_managed_file(file_id: str) -> tuple[bytes, str, str] | None:
    """Locate ``{file_id}_*`` under known storage roots and return bytes."""
    try:
        UUID(file_id)
    except ValueError:
        return None

    for path in _iter_managed_candidates(file_id):
        try:
            if not path.is_file():
                continue
            # Prefer real image files over sidecar text (e.g. base64 dumps).
            if path.suffix.lower() not in _IMAGE_SUFFIXES and path.suffix.lower() not in {
                "",
                ".bin",
            }:
                # Still allow extensionless / odd names if PIL can open them later.
                if path.suffix.lower() in {".txt", ".json", ".md", ".csv"}:
                    continue
            data = path.read_bytes()
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            return data, mime, f"file_id:{file_id}:{path.name}"
        except OSError:
            continue
    return None


def _iter_managed_candidates(file_id: str) -> list[Path]:
    """Return candidate paths for a managed file_id, newest first."""
    roots: list[Path] = []
    try:
        from leagent.config.constants import KNOWLEDGE_DIR, UPLOAD_DIR

        roots.extend([UPLOAD_DIR, KNOWLEDGE_DIR])
    except Exception:  # noqa: BLE001 — settings import must not break resolve
        pass

    try:
        from leagent.config.settings import get_settings

        settings = get_settings()
        files = getattr(settings, "files", None)
        if files is not None:
            upload = getattr(files, "upload_dir", None)
            if upload:
                roots.append(Path(str(upload)))
            getter = getattr(files, "resolved_knowledge_storage_dir", None)
            if callable(getter):
                try:
                    roots.append(Path(getter()))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass

    seen: set[Path] = set()
    matches: list[Path] = []
    needle = f"{file_id}_"
    for root in roots:
        try:
            root = root.resolve()
        except OSError:
            continue
        if not root.is_dir() or root in seen:
            continue
        seen.add(root)
        try:
            # Session uploads live one level deep: uploads/<session_id>/<id>_name
            for path in root.rglob(f"{needle}*"):
                if path.is_file():
                    matches.append(path)
        except OSError:
            continue

    matches.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0, reverse=True)
    return matches


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
