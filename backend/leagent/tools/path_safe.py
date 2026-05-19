"""Filesystem helpers that resist symlink traversal where POSIX allows."""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import BinaryIO, TextIO


def open_read_bytes_nofollow(path: str | Path) -> BinaryIO:
    """Open a file for reading with ``O_NOFOLLOW`` when supported."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(os.fspath(path), flags)
    return os.fdopen(fd, "rb")


def open_read_text_nofollow(
    path: str | Path,
    *,
    encoding: str = "utf-8",
    errors: str = "replace",
    newline: str | None = "",
) -> TextIO:
    """Text mode read through a no-follow binary fd."""
    bio = open_read_bytes_nofollow(path)
    return io.TextIOWrapper(bio, encoding=encoding, errors=errors, newline=newline)


__all__ = ["open_read_bytes_nofollow", "open_read_text_nofollow"]
