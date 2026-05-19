"""Merge multi-file HTML/CSS/JS maps into one preview-safe document.

Agent-facing ``canvas_publish`` can pass ``html_files`` instead of a single
``html`` string. We resolve relative ``<link href=…>`` / ``<script src=…>``
references against the entry file path and inline local assets so the hosted
preview stays a single response (no extra asset routes or CSP changes).
"""

from __future__ import annotations

import posixpath
import re
from typing import Any

_LINK_STYLESHEET_RE = re.compile(
    r"<link\b(?P<attrs>[^>]*?)\s*/?>",
    re.IGNORECASE | re.DOTALL,
)
_SCRIPT_SRC_RE = re.compile(
    r"<script\b(?P<attrs>[^>]*?)\s*>(?P<body>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HREF_RE = re.compile(r"""\bhref\s*=\s*(?P<q>['"])(?P<href>.*?)(?P=q)""", re.IGNORECASE | re.DOTALL)
_SRC_RE = re.compile(r"""\bsrc\s*=\s*(?P<q>['"])(?P<src>.*?)(?P=q)""", re.IGNORECASE | re.DOTALL)
_REL_STYLESHEET_RE = re.compile(
    r"""\brel\s*=\s*(?P<q>['"])stylesheet(?P=q)""",
    re.IGNORECASE,
)


def _norm_rel_path(p: str) -> str:
    s = (p or "").strip().replace("\\", "/")
    if not s or s.startswith(("http://", "https://", "//", "data:", "blob:")):
        return ""
    s = posixpath.normpath(s)
    if s.startswith("..") or "/../" in f"/{s}/":
        raise ValueError(f"Unsafe path in html_files map: {p!r}")
    return s.lstrip("/")


def _resolve_against_entry(entry: str, href: str) -> str:
    base = posixpath.dirname(_norm_rel_path(entry)) or "."
    joined = posixpath.normpath(posixpath.join(base, href.strip()))
    if joined.startswith("..") or "/../" in f"/{joined}/":
        raise ValueError(f"Unsafe resolved asset path: {href!r}")
    return joined.lstrip("/")


def _normalize_files_map(raw: dict[str, Any]) -> dict[str, str]:
    if len(raw) > 40:
        raise ValueError("html_files: at most 40 paths allowed")
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not k.strip():
            raise ValueError("html_files: keys must be non-empty strings")
        if not isinstance(v, str):
            raise ValueError(f"html_files[{k!r}] must be a string")
        nk = _norm_rel_path(k)
        if not nk:
            raise ValueError(f"html_files: invalid key {k!r}")
        out[nk] = v
    return out


def merge_html_files_to_document(
    *,
    entry: str,
    files: dict[str, str],
    max_output_bytes: int,
) -> str:
    """Return one HTML document string (UTF-8) suitable for ``sanitize_html``."""
    entry_n = _norm_rel_path(entry)
    if not entry_n:
        raise ValueError("html_bundle_entry must be a relative path")
    norm_files = _normalize_files_map(dict(files))
    if entry_n not in norm_files:
        raise ValueError(f"html_bundle_entry {entry_n!r} missing from html_files keys")

    html = norm_files[entry_n]

    def replace_stylesheet(m: re.Match[str]) -> str:
        attrs = m.group("attrs") or ""
        if not _REL_STYLESHEET_RE.search(attrs):
            return m.group(0)
        hm = _HREF_RE.search(attrs)
        if not hm:
            return m.group(0)
        href_raw = (hm.group("href") or "").strip()
        key = _resolve_against_entry(entry_n, href_raw)
        if not key or key not in norm_files:
            return m.group(0)
        css = norm_files[key]
        return f"<style data-inlined-from={key!r}>\n{css}\n</style>"

    html = _LINK_STYLESHEET_RE.sub(replace_stylesheet, html)

    def replace_script(m: re.Match[str]) -> str:
        attrs = m.group("attrs") or ""
        body = m.group("body") or ""
        sm = _SRC_RE.search(attrs)
        if not sm:
            return m.group(0)
        if body.strip():
            return m.group(0)
        src_raw = (sm.group("src") or "").strip()
        key = _resolve_against_entry(entry_n, src_raw)
        if not key or key not in norm_files:
            return m.group(0)
        js = norm_files[key]
        return f"<script data-inlined-from={key!r}>\n{js}\n</script>"

    html = _SCRIPT_SRC_RE.sub(replace_script, html)

    raw_b = html.encode("utf-8")
    if len(raw_b) > max_output_bytes:
        raise ValueError(f"Merged HTML exceeds max size ({max_output_bytes} bytes)")
    return html
