"""Shared file-management primitives used across the entire LeAgent stack.

This module is the **single source of truth** for:

* filename sanitisation
* MIME type detection
* file-kind classification (image / document / data / code / …)
* path-containment checking
* scope and kind enumerations
* global file-related constants

Every subsystem that needs these operations imports from here — no
inline re-implementations allowed.
"""

from __future__ import annotations

import mimetypes
import os
from enum import Enum
from pathlib import Path
from typing import Iterable


# ── Constants ────────────────────────────────────────────────────────

MAX_FILENAME_LENGTH: int = 180
DEFAULT_CHECKSUM_ALGO: str = "sha256"


# ── Enums ────────────────────────────────────────────────────────────

class FileScope(str, Enum):
    """Logical namespace that governs where a managed blob is stored."""

    SESSION = "session"
    KNOWLEDGE = "knowledge"
    OUTPUT = "output"
    ASSET = "asset"
    TEMP = "temp"


class FileKind(str, Enum):
    """Content-type classification for managed files.

    Replaces the previously scattered ``FileType``, ``FileCategory``,
    ``ATTACHMENT_KIND_*`` constants with a single canonical enum.
    """

    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    VIDEO = "video"
    ARCHIVE = "archive"
    DATA = "data"
    CODE = "code"
    TEXT = "text"
    OTHER = "other"


# ── Filename sanitisation ────────────────────────────────────────────

def sanitize_filename(
    raw: str,
    *,
    default: str = "file",
    max_length: int = MAX_FILENAME_LENGTH,
) -> str:
    """Return a filesystem-safe version of *raw*.

    * Strips directory components (path traversal prevention).
    * Allows only alphanumerics, ``.``, ``_``, ``-`` and CJK ideographs.
    * Collapses whitespace to ``_``.
    * Falls back to *default* when nothing useful remains.
    * Truncates at *max_length*.
    """
    base = os.path.basename(raw).strip() if raw else ""
    if not base:
        return default[:max_length]

    sanitised: list[str] = []
    for ch in base:
        if ch.isalnum() or ch in (".", "_", "-"):
            sanitised.append(ch)
        elif ch.isspace():
            sanitised.append("_")
    result = "".join(sanitised) or default
    return result[:max_length]


# ── MIME detection ───────────────────────────────────────────────────

def detect_mime(
    filename: str,
    content_type_hint: str | None = None,
) -> str:
    """Guess MIME type from *filename*, falling back to *content_type_hint*.

    Returns ``"application/octet-stream"`` when nothing can be determined.
    """
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    if content_type_hint:
        return content_type_hint
    return "application/octet-stream"


# ── File-kind classification ─────────────────────────────────────────

_IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".svg",
    ".ico",
})
_DOCUMENT_EXTS = frozenset({
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".rtf", ".odt", ".odp",
})
_DATA_EXTS = frozenset({
    ".csv", ".xls", ".xlsx", ".json", ".xml", ".yaml", ".yml", ".parquet",
    ".tsv", ".sqlite", ".db",
})
_AUDIO_EXTS = frozenset({".mp3", ".wav", ".ogg", ".flac", ".aac", ".wma"})
_VIDEO_EXTS = frozenset({".mp4", ".avi", ".mkv", ".webm", ".mov", ".wmv"})
_ARCHIVE_EXTS = frozenset({".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz"})
_CODE_EXTS = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".h",
    ".go", ".rs", ".rb", ".php", ".html", ".css", ".scss", ".sql",
    ".sh", ".bash", ".ps1", ".bat",
})
_TEXT_EXTS = frozenset({".txt", ".md", ".rst", ".log", ".ini", ".cfg", ".toml"})

_MIME_PREFIX_MAP: dict[str, FileKind] = {
    "image/": FileKind.IMAGE,
    "audio/": FileKind.AUDIO,
    "video/": FileKind.VIDEO,
    "text/html": FileKind.CODE,
    "text/css": FileKind.CODE,
    "text/javascript": FileKind.CODE,
    "application/javascript": FileKind.CODE,
    "text/": FileKind.TEXT,
}

_MIME_EXACT_MAP: dict[str, FileKind] = {
    "application/pdf": FileKind.DOCUMENT,
    "application/msword": FileKind.DOCUMENT,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": FileKind.DOCUMENT,
    "application/vnd.ms-excel": FileKind.DATA,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": FileKind.DATA,
    "application/vnd.ms-powerpoint": FileKind.DOCUMENT,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": FileKind.DOCUMENT,
    "application/zip": FileKind.ARCHIVE,
    "application/x-tar": FileKind.ARCHIVE,
    "application/gzip": FileKind.ARCHIVE,
    "application/json": FileKind.DATA,
    "application/xml": FileKind.DATA,
    "text/csv": FileKind.DATA,
    "text/markdown": FileKind.DOCUMENT,
    "text/plain": FileKind.TEXT,
    "image/svg+xml": FileKind.IMAGE,
}


def classify_file_kind(filename: str, mime: str | None = None) -> FileKind:
    """Determine the :class:`FileKind` of a file.

    Classification priority: extension → exact MIME → MIME prefix → OTHER.
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext:
        if ext in _IMAGE_EXTS:
            return FileKind.IMAGE
        if ext in _DOCUMENT_EXTS:
            return FileKind.DOCUMENT
        if ext in _DATA_EXTS:
            return FileKind.DATA
        if ext in _AUDIO_EXTS:
            return FileKind.AUDIO
        if ext in _VIDEO_EXTS:
            return FileKind.VIDEO
        if ext in _ARCHIVE_EXTS:
            return FileKind.ARCHIVE
        if ext in _CODE_EXTS:
            return FileKind.CODE
        if ext in _TEXT_EXTS:
            return FileKind.TEXT

    if mime:
        exact = _MIME_EXACT_MAP.get(mime)
        if exact:
            return exact
        for prefix, kind in _MIME_PREFIX_MAP.items():
            if mime.startswith(prefix):
                return kind

    return FileKind.OTHER


# ── Path containment ─────────────────────────────────────────────────

def is_path_inside(resolved: Path, roots: Iterable[Path]) -> bool:
    """Return ``True`` if *resolved* equals or is contained by any root.

    The caller is responsible for calling ``.resolve()`` on *resolved*
    before passing it in when symlink traversal must be accounted for.

    Accepts a single ``Path`` as *roots* (auto-wrapped in a tuple).
    """
    if isinstance(roots, Path):
        roots = (roots,)
    for root in roots:
        if resolved == root:
            return True
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False
