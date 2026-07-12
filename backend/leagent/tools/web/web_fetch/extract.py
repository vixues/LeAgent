"""Lightweight HTML → readable text extraction (stdlib only)."""

from __future__ import annotations

import re
from html.parser import HTMLParser


_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "noscript",
        "svg",
        "iframe",
        "template",
        "nav",
        "footer",
        "aside",
        "form",
    }
)
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "section",
        "article",
        "main",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "br",
        "tr",
        "blockquote",
        "pre",
        "hr",
    }
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0
        self.title: str = ""
        self._in_title = False
        self._prefer_depth = 0  # inside main/article
        self._prefer_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if t == "title":
            self._in_title = True
        if t in ("main", "article"):
            self._prefer_depth += 1
        if t in _BLOCK_TAGS:
            self._emit("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in _SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if t == "title":
            self._in_title = False
        if t in ("main", "article") and self._prefer_depth:
            self._prefer_depth -= 1
        if t in _BLOCK_TAGS:
            self._emit("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip() if self._in_title else data
        if self._in_title and text:
            self.title = (self.title + " " + text).strip()
            return
        if not data or not data.strip():
            if data and "\n" in data:
                self._emit("\n")
            return
        self._emit(re.sub(r"[ \t]+", " ", data))

    def _emit(self, s: str) -> None:
        if self._prefer_depth > 0:
            self._prefer_chunks.append(s)
        else:
            self._chunks.append(s)

    def text(self) -> str:
        raw = "".join(self._prefer_chunks) if self._prefer_chunks else "".join(self._chunks)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_readable_text(html: str) -> tuple[str, str]:
    """Return ``(title, text)`` extracted from HTML."""
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:
        # Extremely broken HTML — fall back to tag strip
        stripped = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
        stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        return "", stripped
    return parser.title, parser.text()
