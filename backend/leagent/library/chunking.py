"""Deterministic, offset-preserving text chunking for the knowledge base.

Chunks are the addressable units of the Storage Layer. Each chunk records its
``[start_offset, end_offset)`` span in the *source extracted text* so that a
retrieval hit can be verified and cited back to an exact location in the
original document (the basis for the EOKA Evidence Layer).

The splitter is intentionally simple and dependency-free: it packs whole
paragraphs (blank-line separated) into windows of at most ``max_chars`` with a
``overlap`` character tail carried into the next window. Paragraphs larger than
a window are hard-split on character boundaries. Offsets always index into the
*original* string, never a normalized copy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP = 150

_PARAGRAPH_RE = re.compile(r"\n\s*\n")


@dataclass(frozen=True)
class Chunk:
    """An offset-addressed slice of the source text."""

    seq: int
    start_offset: int
    end_offset: int
    text: str


def _iter_paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` spans for blank-line separated paragraphs."""
    spans: list[tuple[int, int]] = []
    cursor = 0
    for match in _PARAGRAPH_RE.finditer(text):
        end = match.start()
        if end > cursor:
            spans.append((cursor, end))
        cursor = match.end()
    if cursor < len(text):
        spans.append((cursor, len(text)))
    return spans


def chunk_text(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """Split *text* into overlapping, offset-addressed chunks.

    Args:
        text: The source extracted text.
        max_chars: Maximum characters per chunk.
        overlap: Characters of trailing context carried into the next chunk.

    Returns:
        Ordered chunks whose spans index into *text*. Empty/whitespace-only
        input yields an empty list.
    """
    if not text or not text.strip():
        return []
    max_chars = max(1, max_chars)
    overlap = max(0, min(overlap, max_chars - 1))

    # Build candidate segments: whole paragraphs, hard-split when oversized.
    segments: list[tuple[int, int]] = []
    for start, end in _iter_paragraph_spans(text):
        if end - start <= max_chars:
            segments.append((start, end))
            continue
        pos = start
        while pos < end:
            seg_end = min(pos + max_chars, end)
            segments.append((pos, seg_end))
            pos = seg_end

    chunks: list[Chunk] = []
    seq = 0
    cur_start: int | None = None
    cur_end: int | None = None
    for seg_start, seg_end in segments:
        if cur_start is None:
            cur_start, cur_end = seg_start, seg_end
            continue
        # Extend the current window if the packed paragraph still fits.
        if seg_end - cur_start <= max_chars:
            cur_end = seg_end
            continue
        chunk_str = text[cur_start:cur_end]
        if chunk_str.strip():
            chunks.append(Chunk(seq, cur_start, cur_end, chunk_str))
            seq += 1
        # Start the next window, carrying an overlap tail from the previous one.
        overlap_start = max(cur_start, (cur_end or seg_start) - overlap)
        cur_start = min(overlap_start, seg_start)
        cur_end = seg_end

    if cur_start is not None and cur_end is not None:
        chunk_str = text[cur_start:cur_end]
        if chunk_str.strip():
            chunks.append(Chunk(seq, cur_start, cur_end, chunk_str))

    return chunks
