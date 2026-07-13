"""Extractive one-line summaries for knowledge-base documents.

Summaries are generated after text extraction / chunk indexing so catalog
tools can advertise documents without calling an LLM. They are intentionally
short (~200 chars) to keep tool results cheap.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 200

_HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+|[A-Z][A-Za-z0-9 ,./&\-]{2,80}|[\u4e00-\u9fff]{2,40})$"
)
_WHITESPACE_RE = re.compile(r"\s+")


def summarize_extracted_text(
    text: str | None,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> str | None:
    """Build a short extractive summary from *text*.

    Prefers the first heading-like line, then packs following paragraph
    content until ``max_chars``. Returns ``None`` when there is no usable text.
    """
    if not text or not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", stripped) if p.strip()]
    if not paragraphs:
        paragraphs = [stripped]

    title: str | None = None
    body_parts: list[str] = []

    first_line = paragraphs[0].splitlines()[0].strip() if paragraphs else ""
    if first_line and (
        first_line.startswith("#")
        or (len(first_line) <= 80 and _HEADING_RE.match(first_line))
    ):
        title = _WHITESPACE_RE.sub(" ", first_line.lstrip("#").strip())
        rest = "\n".join(paragraphs[0].splitlines()[1:]).strip()
        if rest:
            body_parts.append(rest)
        body_parts.extend(paragraphs[1:])
    else:
        body_parts.extend(paragraphs)

    pieces: list[str] = []
    if title:
        pieces.append(title)

    for part in body_parts:
        normalized = _WHITESPACE_RE.sub(" ", part).strip()
        if not normalized:
            continue
        pieces.append(normalized)

    if not pieces:
        return None

    summary = " — ".join(pieces) if title and len(pieces) > 1 else " ".join(pieces)
    summary = _WHITESPACE_RE.sub(" ", summary).strip()
    if len(summary) <= max_chars:
        return summary
    cut = summary[: max_chars - 1].rstrip()
    return cut + "…"
