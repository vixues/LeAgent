"""Recover tool-call arguments when large ``data`` / ``content`` breaks JSON escaping."""

from __future__ import annotations

import re
from typing import Any

_STRING_FIELD = re.compile(
    r'"(?P<key>operation|file_path|data|content)"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"',
    re.DOTALL,
)


def recover_doc_tool_args(raw: str, *, content_key: str) -> dict[str, Any] | None:
    """Best-effort extraction of common fields from malformed tool-call JSON."""
    if not raw or not raw.strip():
        return None
    out: dict[str, Any] = {}
    for m in _STRING_FIELD.finditer(raw):
        key = m.group("key")
        val = m.group("value")
        try:
            decoded = bytes(val, "utf-8").decode("unicode_escape")
        except (UnicodeDecodeError, ValueError):
            decoded = val.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
        if key == "operation":
            out["operation"] = decoded
        elif key == "file_path":
            out["file_path"] = decoded
        elif key in ("data", "content"):
            if key == content_key:
                out[key] = decoded
    if content_key not in out and "operation" not in out and "file_path" not in out:
        return None
    if "operation" not in out:
        out.setdefault("operation", "write")
    return out
