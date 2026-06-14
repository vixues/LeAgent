"""Unified tool execution module.

This is the single, authoritative executor for every caller — chat agents,
subagents, workflow nodes, the MCP bridge, cron jobs, and background
workers. It owns:

* Registry lookup and alias resolution via :class:`ToolRegistry`
* Permission enforcement (:func:`check_tool_permission`) with the real
  :class:`ToolContext` threaded through
* Context construction via :func:`build_tool_context` when the caller
  passes something that isn't already a :class:`ToolContext` (e.g. an
  :class:`AgentContext`)
* Single-tool dispatch (:meth:`execute`, :meth:`run_tool`)
* Batch dispatch with concurrency-safe partitioning, parallel/sequential
  modes, fail-fast, and explicit dependencies
* Optional progress callbacks and cancellation through
  :class:`ToolContext.abort_signal`
* Lightweight execution metrics per tool

There is no separate "agent adapter" class; agents and workflows both
use :class:`ToolExecutor` directly. :class:`ToolResult` is the single
result envelope (see :mod:`leagent.tools.base`).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from leagent.tools.base import (
    ToolContext,
    ToolPermissionContext,
    ToolProgressCallback,
    ToolResult,
    check_tool_permission,
)
from leagent.tools.context import build_tool_context
from leagent.tools.pipeline import MiddlewareContext, MiddlewarePipeline
from leagent.tools.rate_limit import tool_rate_limit_from_env
from leagent.tools.registry import ToolNotFoundError, ToolRegistry, get_registry

if TYPE_CHECKING:
    from collections.abc import Sequence

    from leagent.services.service_manager import ServiceManager

logger = structlog.get_logger(__name__)


SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password", "token", "secret", "key", "credential", "auth",
})
_AUDIT_VALUE_LIMIT = 20_000


def _strip_json_code_fence(raw: str) -> str:
    """Remove optional markdown code fences around JSON payloads."""
    text = _strip_json_prefix(raw).strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if match:
        return _strip_json_prefix(match.group(1)).strip()
    return text


def _strip_json_prefix(raw: str) -> str:
    """Trim BOM and invisible prefix characters that commonly precede JSON."""
    return raw.lstrip("\ufeff\u200b\u200c\u200d\u2060")


def _repair_trailing_commas(raw: str) -> str:
    """Remove trailing commas before object/array terminators outside strings."""
    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < len(raw) and raw[j].isspace():
                j += 1
            if j < len(raw) and raw[j] in "}]":
                i += 1
                continue

        out.append(ch)
        i += 1
    return "".join(out)


def _escape_control_chars_in_json_strings(raw: str) -> str:
    """Escape raw control characters that appear inside JSON strings."""
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in raw:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == '"':
                out.append(ch)
                in_string = False
                continue
            if ch == "\n":
                out.append("\\n")
                continue
            if ch == "\r":
                out.append("\\r")
                continue
            if ch == "\t":
                out.append("\\t")
                continue
            if ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
                continue
            out.append(ch)
            continue

        out.append(ch)
        if ch == '"':
            in_string = True
    return "".join(out)


def _candidate_json_texts(raw: str) -> list[str]:
    """Return increasingly repaired JSON candidates, preserving order."""
    candidates: list[str] = []

    def add(value: str) -> None:
        if value not in candidates:
            candidates.append(value)

    add(raw)
    add(_strip_json_prefix(raw).strip())
    fenced = _strip_json_code_fence(raw)
    add(fenced)
    for value in list(candidates):
        repaired = _repair_trailing_commas(value)
        add(repaired)
        escaped = _escape_control_chars_in_json_strings(value)
        add(escaped)
        add(_repair_trailing_commas(escaped))
    return candidates


def _loads_json_dict(candidate: str) -> dict[str, Any] | None:
    """Parse a JSON object candidate, including double-encoded objects."""
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, str):
        for nested in _candidate_json_texts(parsed):
            try:
                parsed = json.loads(nested)
            except json.JSONDecodeError:
                continue
            break
        else:
            return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _try_json_dict_raw_decode_trailing_junk(candidate: str) -> dict[str, Any] | None:
    """When ``json.loads`` fails with trailing garbage, accept a leading object if junk is only ``]``/``}``."""
    text = candidate.strip()
    try:
        obj, end = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    rest = text[end:].strip()
    if not rest:
        return obj
    if all(ch in "]}" for ch in rest):
        return obj
    return None


def _try_repair_superfluous_closing_delimiter(candidate: str, *, max_deletions: int = 3) -> dict[str, Any] | None:
    """Drop a few stray ``]``/``}`` near decode errors (common LLM nesting mistakes)."""
    stripped = candidate.strip()

    def parse_or_error(value: str) -> tuple[dict[str, Any] | None, int | None]:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as e:
            pos = getattr(e, "pos", None)
            return None, pos if isinstance(pos, int) else None
        return (parsed if isinstance(parsed, dict) else None), None

    parsed, pos = parse_or_error(stripped)
    if parsed is not None:
        return parsed
    queue: list[tuple[str, int | None, int]] = [(stripped, pos, 0)]
    seen = {stripped}
    window = 24
    while queue:
        text, err_pos, deletions = queue.pop(0)
        if err_pos is None or deletions >= max_deletions:
            continue
        lo = max(0, err_pos - window)
        hi = min(len(text), err_pos + window + 1)
        for i in range(lo, hi):
            if text[i] not in "]}":
                continue
            cand = text[:i] + text[i + 1 :]
            if cand in seen:
                continue
            seen.add(cand)
            parsed, next_pos = parse_or_error(cand)
            if parsed is not None:
                return parsed
            queue.append((cand, next_pos, deletions + 1))
    return None


def _find_json_string_end(raw: str, start: int) -> int | None:
    """Find the end quote for a JSON string by normal escape rules."""
    escaped = False
    for i in range(start, len(raw)):
        ch = raw[i]
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            return i
    return None


def _extract_json_string_value(raw: str, key: str) -> tuple[str, int, int] | None:
    """Extract a normally escaped JSON string value for *key*."""
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"', raw)
    if not match:
        return None
    value_start = match.end()
    value_end = _find_json_string_end(raw, value_start)
    if value_end is None:
        return None
    try:
        value = json.loads(f'"{raw[value_start:value_end]}"')
    except json.JSONDecodeError:
        return None
    return value, value_start, value_end


def _extract_malformed_quoted_field(
    raw: str,
    field: str,
    allowed_next_keys: tuple[str, ...],
) -> tuple[str, int, int] | None:
    """Best-effort extraction when *field*'s JSON string value contains raw newlines.

    Models occasionally emit multiline text inside a JSON string without
    escaping newlines or inner quotes. The heuristic finds a closing ``"``
    whose suffix resumes the outer object (comma + next known key, or ``}``).
    """
    match = re.search(rf'"{re.escape(field)}"\s*:\s*"', raw)
    if not match:
        return None
    value_start = match.end()
    escaped = False
    fallback_end: int | None = None
    for i in range(value_start, len(raw)):
        ch = raw[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch != '"':
            continue

        suffix = raw[i + 1 :]
        stripped = suffix.lstrip()
        if stripped.startswith("}"):
            fallback_end = i
            continue
        if stripped.startswith(","):
            after_comma = stripped[1:].lstrip()
            if any(after_comma.startswith(f'"{key}"') for key in allowed_next_keys):
                return raw[value_start:i], value_start, i
    if fallback_end is not None:
        return raw[value_start:fallback_end], value_start, fallback_end
    return None


def _extract_malformed_source(raw: str) -> tuple[str, int, int] | None:
    """Best-effort extraction for ``code_execution`` ``source`` in broken JSON."""
    return _extract_malformed_quoted_field(
        raw,
        "source",
        (
            "inputs",
            "timeout_sec",
            "memory_bytes",
            "files",
            "reset_workspace",
        ),
    )


def _recover_code_execution_args(raw: str) -> dict[str, Any] | None:
    """Recover code_execution args when only the outer JSON is malformed."""
    text = _strip_json_code_fence(raw)
    source_info = _extract_json_string_value(text, "source") or _extract_malformed_source(text)
    if source_info is None:
        return None
    source, _, source_end = source_info
    recovered: dict[str, Any] = {"source": source}

    suffix = text[source_end + 1 :].strip()
    if suffix.startswith(","):
        suffix = "{" + suffix[1:]
        parsed_suffix = _loads_json_dict(_repair_trailing_commas(suffix))
        if parsed_suffix:
            for key in (
                "inputs",
                "timeout_sec",
                "memory_bytes",
                "files",
                "reset_workspace",
                "source_blob_id",
            ):
                if key in parsed_suffix:
                    recovered[key] = parsed_suffix[key]

    return recovered


def _recover_project_write_args(raw: str) -> dict[str, Any] | None:
    """Recover ``project_write`` args when ``content`` breaks outer JSON."""
    text = _strip_json_code_fence(raw)
    if '"path"' not in text or '"content"' not in text:
        return None
    path_info = _extract_json_string_value(text, "path")
    if path_info is None:
        return None
    path, _, _ = path_info
    if not path.strip():
        return None
    content_info = _extract_json_string_value(text, "content") or _extract_malformed_quoted_field(
        text,
        "content",
        ("overwrite", "create_parents", "project_path"),
    )
    if content_info is None:
        return None
    content, _, content_end = content_info
    recovered: dict[str, Any] = {"path": path, "content": content}
    suffix = text[content_end + 1 :].strip()
    if suffix.startswith(","):
        suffix = "{" + suffix[1:]
        parsed_suffix = _loads_json_dict(_repair_trailing_commas(suffix))
        if parsed_suffix:
            for key in ("overwrite", "create_parents", "project_path"):
                if key in parsed_suffix:
                    recovered[key] = parsed_suffix[key]
    return recovered


def _recover_project_edit_args(raw: str) -> dict[str, Any] | None:
    """Recover ``project_edit`` args when ``new_string`` breaks outer JSON."""
    text = _strip_json_code_fence(raw)
    if '"path"' not in text or '"new_string"' not in text:
        return None
    path_info = _extract_json_string_value(text, "path")
    if path_info is None:
        return None
    path, _, _ = path_info
    if not path.strip():
        return None
    old_info = _extract_json_string_value(text, "old_string")
    new_info = _extract_json_string_value(text, "new_string") or _extract_malformed_quoted_field(
        text,
        "new_string",
        ("project_path",),
    )
    if new_info is None:
        return None
    new_string, _, new_end = new_info
    recovered: dict[str, Any] = {"path": path, "new_string": new_string}
    if old_info is not None:
        recovered["old_string"] = old_info[0]
    suffix = text[new_end + 1 :].strip()
    if suffix.startswith(","):
        suffix = "{" + suffix[1:]
        parsed_suffix = _loads_json_dict(_repair_trailing_commas(suffix))
        if parsed_suffix:
            for key in ("project_path",):
                if key in parsed_suffix:
                    recovered[key] = parsed_suffix[key]
    return recovered


def _recover_project_apply_patch_args(raw: str) -> dict[str, Any] | None:
    """Recover ``project_apply_patch`` args when ``diff`` breaks outer JSON."""
    text = _strip_json_code_fence(raw)
    if '"diff"' not in text:
        return None
    diff_info = _extract_json_string_value(text, "diff") or _extract_malformed_quoted_field(
        text,
        "diff",
        ("project_path",),
    )
    if diff_info is None:
        return None
    diff_text, _, diff_end = diff_info
    if not diff_text.strip():
        return None
    recovered: dict[str, Any] = {"diff": diff_text}
    suffix = text[diff_end + 1 :].strip()
    if suffix.startswith(","):
        suffix = "{" + suffix[1:]
        parsed_suffix = _loads_json_dict(_repair_trailing_commas(suffix))
        if parsed_suffix and "project_path" in parsed_suffix:
            recovered["project_path"] = parsed_suffix["project_path"]
    return recovered


def _recover_canvas_publish_args(raw: str) -> dict[str, Any] | None:
    """Recover ``canvas_publish`` args when ``html`` breaks outer JSON."""
    text = _strip_json_code_fence(raw)
    if '"title"' not in text or '"mode"' not in text:
        return None
    if '"html"' not in text and '"html_blob_id"' not in text:
        return None
    title_info = _extract_json_string_value(text, "title")
    if title_info is None:
        return None
    title, _, _ = title_info
    mode_info = _extract_json_string_value(text, "mode")
    if mode_info is None:
        return None
    mode, _, _ = mode_info
    recovered: dict[str, Any] = {"title": title, "mode": mode}
    sid_info = _extract_json_string_value(text, "session_id")
    if sid_info is not None:
        recovered["session_id"] = sid_info[0]

    html_info = _extract_json_string_value(text, "html") or _extract_malformed_quoted_field(
        text,
        "html",
        (
            "embed_url",
            "ui_snapshot",
            "canvas_id",
            "message_id",
            "open_in_panel",
            "html_blob_id",
        ),
    )
    end_pos: int
    if html_info is not None:
        html_body, _, html_end = html_info
        recovered["html"] = html_body
        end_pos = html_end
    else:
        blob_info = _extract_json_string_value(text, "html_blob_id")
        if blob_info is None:
            return None
        bid, _, bid_end = blob_info
        recovered["html_blob_id"] = bid
        end_pos = bid_end

    suffix = text[end_pos + 1 :].strip()
    if suffix.startswith(","):
        suffix = "{" + suffix[1:]
        parsed_suffix = _loads_json_dict(_repair_trailing_commas(suffix))
        if parsed_suffix:
            for key in (
                "embed_url",
                "ui_snapshot",
                "canvas_id",
                "message_id",
                "open_in_panel",
                "html_blob_id",
                "html",
            ):
                if key in parsed_suffix and key not in recovered:
                    recovered[key] = parsed_suffix[key]
    return recovered


def _extract_json_object_value(raw: str, key: str) -> dict[str, Any] | None:
    """Extract a complete object value for *key* even when the outer object is malformed."""
    match = re.search(rf'"{re.escape(key)}"\s*:\s*', raw)
    if not match:
        return None
    value_start = match.end()
    while value_start < len(raw) and raw[value_start].isspace():
        value_start += 1
    if value_start >= len(raw) or raw[value_start] != "{":
        return None
    try:
        parsed, _ = json.JSONDecoder().raw_decode(raw[value_start:])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _close_truncated_json_object(raw: str) -> str | None:
    """Close an otherwise well-formed JSON object prefix after provider truncation.

    This is intentionally conservative: it only appends a missing string quote
    and the delimiters already implied by the parsed prefix. It does not create
    missing keys, values, or commas.
    """
    text = raw.strip()
    if not text.startswith("{"):
        return None
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if not stack or stack[-1] != ch:
                return None
            stack.pop()

    if not in_string and not stack:
        return None
    suffix = ""
    if in_string:
        if escaped:
            suffix += "\\"
        suffix += '"'
    suffix += "".join(reversed(stack))
    return text + suffix


def _close_truncated_json_array(raw: str) -> str | None:
    """Close a truncated JSON array prefix after provider truncation."""
    text = raw.strip()
    if not text.startswith("["):
        return None
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]":
            if not stack or stack[-1] != ch:
                return None
            stack.pop()

    if not in_string and not stack:
        return None
    suffix = ""
    if in_string:
        if escaped:
            suffix += "\\"
        suffix += '"'
    suffix += "".join(reversed(stack))
    return text + suffix


def _try_parse_closed_json_prefix(text: str) -> Any | None:
    """Bracket-close a truncated object/array prefix and parse when possible."""
    stripped = text.strip()
    if not stripped:
        return None
    closed: str | None = None
    if stripped.startswith("{"):
        closed = _close_truncated_json_object(stripped)
    elif stripped.startswith("["):
        closed = _close_truncated_json_array(stripped)
    if closed is None:
        return None
    for candidate in (closed, _repair_trailing_commas(closed)):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _salvage_truncated_json_prefix(raw: str, *, max_trim: int = 4000) -> Any | None:
    """Trim a truncated JSON prefix until bracket-closing yields valid parse."""
    text = raw.strip()
    if not text or text[0] not in "{[":
        return None
    min_len = max(1, len(text) - max_trim)
    for end in range(len(text), min_len - 1, -1):
        prefix = text[:end].rstrip()
        if not prefix:
            continue
        while prefix and prefix[-1] in ",:":
            prefix = prefix[:-1].rstrip()
        parsed = _try_parse_closed_json_prefix(prefix)
        if parsed is not None:
            return parsed
    return None


def _looks_like_stream_truncation(raw: str) -> bool:
    """Heuristic: provider cut the JSON stream mid-token (not a mid-string syntax error)."""
    text = raw.rstrip()
    if len(text) < 2:
        return False
    if text[-1] in "{[,:":
        return True
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
    if in_string:
        return True
    try:
        json.loads(text)
        return False
    except json.JSONDecodeError as exc:
        pos = getattr(exc, "pos", None)
        if isinstance(pos, int) and pos >= max(0, len(text) - 8):
            return True
        return False


def _salvage_truncated_json_after_key(raw: str, key: str) -> Any | None:
    """Salvage the JSON value for *key* when the stream was truncated mid-value."""
    match = re.search(rf'"{re.escape(key)}"\s*:\s*', raw)
    if not match:
        return None
    value_start = match.end()
    while value_start < len(raw) and raw[value_start].isspace():
        value_start += 1
    if value_start >= len(raw):
        return None
    fragment = raw[value_start:]
    if not _looks_like_stream_truncation(fragment):
        return None
    return _salvage_truncated_json_prefix(fragment)


def _extract_truncated_string_value(raw: str, key: str) -> str | None:
    """Extract a string value for *key* even when the closing quote is missing (truncated output)."""
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"', raw)
    if not match:
        return None
    value_start = match.end()
    value_end = _find_json_string_end(raw, value_start)
    if value_end is not None:
        try:
            return json.loads(f'"{raw[value_start:value_end]}"')
        except json.JSONDecodeError:
            return raw[value_start:value_end]
    # Truncated: take everything after the opening quote, stripping trailing whitespace
    return raw[value_start:].rstrip()


def _recover_tool_argument_blob_args(raw: str) -> dict[str, Any] | None:
    """Recover ``tool_argument_blob`` append args when ``chunk`` breaks outer JSON.

    When the LLM inlines HTML/JSX in ``chunk``, unescaped double quotes
    break the tool-call JSON. We extract the chunk content and re-encode
    it as ``chunk_base64`` so downstream processing never sees raw markup
    in a JSON string.

    Also handles truncated ``chunk_base64`` values where the output token
    limit cut the string before the closing quote — we take whatever base64
    was emitted and let downstream decode it tolerantly.
    """
    text = _strip_json_code_fence(raw)
    low = text.lower()
    if '"append"' not in low and "'append'" not in low:
        if '"create_and_finalize"' not in low:
            return None
    if '"blob_id"' not in text and '"chunk"' not in text and '"chunk_base64"' not in text:
        if '"create_and_finalize"' not in low:
            return None

    action_info = _extract_json_string_value(text, "action")
    action = action_info[0] if action_info else ""
    if action not in ("append", "create_and_finalize"):
        return None

    blob_id_info = _extract_json_string_value(text, "blob_id")
    blob_id = blob_id_info[0] if blob_id_info else ""

    b64_info = _extract_json_string_value(text, "chunk_base64")
    if b64_info is not None:
        recovered: dict[str, Any] = {"action": action, "chunk_base64": b64_info[0]}
        if blob_id:
            recovered["blob_id"] = blob_id
        return recovered

    # Truncated chunk_base64: the string was cut off before the closing quote
    truncated_b64 = _extract_truncated_string_value(text, "chunk_base64")
    if truncated_b64 and len(truncated_b64) > 8:
        recovered = {"action": action, "chunk_base64": truncated_b64}
        if blob_id:
            recovered["blob_id"] = blob_id
        return recovered

    chunk_info = (
        _extract_json_string_value(text, "chunk")
        or _extract_malformed_quoted_field(
            text,
            "chunk",
            ("blob_id", "action", "chunk_base64"),
        )
    )
    if chunk_info is None:
        return None
    chunk_text = chunk_info[0]
    if not chunk_text:
        return None

    import base64 as _b64

    encoded = _b64.b64encode(chunk_text.encode("utf-8")).decode("ascii")
    recovered = {"action": action, "chunk_base64": encoded}
    if blob_id:
        recovered["blob_id"] = blob_id
    return recovered


def _recover_emit_ui_tree_args(raw: str) -> dict[str, Any] | None:
    """Recover ``emit_ui_tree`` args when the outer JSON is malformed or truncated.

    Handles three scenarios:
    1. Outer JSON broken but the ``tree`` object value is complete (``raw_decode``).
    2. Outer + tree both truncated: close the brackets on the tree substring.
    3. Outer closed but inner tree still truncated: extract and close tree.
    """
    for candidate in _candidate_json_texts(_strip_json_code_fence(raw)):
        tree = _extract_json_object_value(candidate, "tree")

        if tree is None:
            closed = _close_truncated_json_object(candidate)
            if closed is not None:
                parsed = _loads_json_dict(closed)
                if parsed is not None and isinstance(parsed.get("tree"), dict):
                    tree = parsed["tree"]
                else:
                    tree = _extract_json_object_value(closed, "tree")

        if tree is None:
            tree = _extract_and_close_truncated_tree(candidate)

        if tree is None and _looks_like_stream_truncation(candidate):
            outer = _salvage_truncated_json_prefix(candidate)
            if isinstance(outer, dict):
                inner = outer.get("tree")
                if isinstance(inner, dict):
                    tree = inner
                elif "root" in outer or "schemaVersion" in outer:
                    tree = outer

        if tree is None:
            continue
        recovered: dict[str, Any] = {"tree": tree}
        canvas_info = _extract_json_string_value(candidate, "canvas_id")
        if canvas_info is not None:
            recovered["canvas_id"] = canvas_info[0]
        return recovered
    return None


def _extract_and_close_truncated_tree(raw: str) -> dict[str, Any] | None:
    """Extract the ``"tree"`` value from *raw* even when it is truncated mid-stream."""
    match = re.search(r'"tree"\s*:\s*', raw)
    if not match:
        return None
    value_start = match.end()
    while value_start < len(raw) and raw[value_start].isspace():
        value_start += 1
    if value_start >= len(raw) or raw[value_start] != "{":
        return None
    tree_fragment = raw[value_start:]

    closed = _close_truncated_json_object(tree_fragment)
    if closed is not None:
        try:
            parsed = json.loads(_repair_trailing_commas(closed))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    for wrapped in (tree_fragment, f'{{"tree":{tree_fragment}}}'):
        repaired = _try_repair_superfluous_closing_delimiter(wrapped, max_deletions=16)
        if isinstance(repaired, dict):
            inner = repaired.get("tree")
            if isinstance(inner, dict):
                return inner

    salvaged = _salvage_truncated_json_after_key(raw, "tree")
    return salvaged if isinstance(salvaged, dict) else None


def _recover_emit_ui_patch_args(raw: str) -> dict[str, Any] | None:
    """Recover ``emit_ui_patch`` args when outer JSON is malformed."""
    for candidate in _candidate_json_texts(_strip_json_code_fence(raw)):
        parsed = _loads_json_dict(candidate)
        if parsed is None:
            parsed = _try_json_dict_raw_decode_trailing_junk(candidate)
        if parsed is None:
            parsed = _try_repair_superfluous_closing_delimiter(candidate, max_deletions=16)
        if isinstance(parsed, dict) and isinstance(parsed.get("patches"), list):
            return {
                k: v
                for k, v in parsed.items()
                if k in ("patches", "canvas_id", "seq") and v is not None
            }

        patches = _salvage_truncated_json_after_key(candidate, "patches")
        if isinstance(patches, list) and patches:
            return {"patches": patches}

        if _looks_like_stream_truncation(candidate):
            outer = _salvage_truncated_json_prefix(candidate)
            if isinstance(outer, dict) and isinstance(outer.get("patches"), list):
                return {
                    k: v
                    for k, v in outer.items()
                    if k in ("patches", "canvas_id", "seq") and v is not None
                }
    return None


def _try_parse_raw_tool_args(raw: str) -> dict[str, Any] | None:
    """Parse a raw arguments string into a dict when possible."""
    for candidate in _candidate_json_texts(raw):
        parsed = _loads_json_dict(candidate)
        if parsed is not None:
            return parsed
        parsed = _try_json_dict_raw_decode_trailing_junk(candidate)
        if parsed is not None:
            return parsed
        parsed = _try_repair_superfluous_closing_delimiter(candidate)
        if parsed is not None:
            return parsed
    return (
        _recover_tool_argument_blob_args(raw)
        or _recover_emit_ui_patch_args(raw)
        or _recover_emit_ui_tree_args(raw)
        or _recover_canvas_publish_args(raw)
        or _recover_project_write_args(raw)
        or _recover_project_edit_args(raw)
        or _recover_project_apply_patch_args(raw)
        or _recover_code_execution_args(raw)
    )


def parse_tool_arguments_str(raw: str) -> dict[str, Any] | None:
    """Parse LLM ``function.arguments`` text into a parameter dict when possible.

    Uses the same recovery as the executor ``__raw__`` path: BOM trim, optional
    markdown code fences, trailing-comma repair, double-encoded JSON-string
    wrappers, :func:`json.JSONDecoder.raw_decode` when only stray ``]``/``}``
    trail a complete object, and a narrow single-character deletion near decode
    errors (common with over-nested ``emit_ui_tree`` / ``canvas_publish`` payloads).
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return _try_parse_raw_tool_args(stripped)


def strict_json_loads_error(raw: str) -> json.JSONDecodeError | None:
    """Return the error from a strict :func:`json.loads` of *raw*, or ``None`` if it parses."""
    try:
        json.loads(raw)
    except json.JSONDecodeError as e:
        return e
    return None


def format_tool_arguments_json_error(
    raw: str,
    strict_err: json.JSONDecodeError | None = None,
    *,
    tool_name: str | None = None,
) -> str:
    """Return a bounded, model-actionable parse error.

    Generic tools keep the historical ``Malformed tool arguments JSON`` prefix
    for tests and log correlation. ``code_execution`` uses plain language: the
    usual failure mode is truncated streaming or quote-heavy inlined ``source``,
    not "invalid JSON syntax" in the abstract.
    """
    base = "Malformed tool arguments JSON"
    if not raw:
        return base
    err = strict_err or strict_json_loads_error(raw)
    if err is None:
        return base
    if tool_name == "code_execution" and '"source"' in raw:
        return _format_code_execution_raw_args_error(raw, err)
    if tool_name == "tool_argument_blob":
        low = raw.lower()
        if "append" in low and ("chunk" in low or "chunk_base64" in low):
            return _format_tool_argument_blob_raw_args_error(raw, err)

    pos = getattr(err, "pos", None)
    if not isinstance(pos, int):
        msg = f"{base}: {err.msg}"
    else:
        start = max(0, pos - 80)
        end = min(len(raw), pos + 80)
        snippet = raw[start:end].replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
        msg = (
            f"{base}: {err.msg} at line {err.lineno} column {err.colno}. "
            "Retry with strict JSON and correctly escaped string values. "
            f"Near: {snippet[:180]}"
        )
    return msg + _tool_json_parse_recovery_hint(tool_name, raw)


def _format_code_execution_raw_args_error(raw: str, err: json.JSONDecodeError) -> str:
    """Explain ``code_execution`` ``__raw__`` failures without blaming abstract JSON skill."""
    trimmed = raw.rstrip()
    incomplete_object = not trimmed.endswith("}")
    unterminated = "Unterminated string" in err.msg
    likely_truncated = incomplete_object and (unterminated or len(raw) > 800)

    parts = [
        "`code_execution` did not run: the tool-call JSON could not be decoded. "
        "The runtime usually auto-recovers inline `source`, but this call "
        "could not be salvaged.",
    ]
    if likely_truncated:
        parts.append(
            "The call appears truncated (JSON never reaches a closing `}` or "
            "closing quote on `source`)."
        )
    parts.append(
        "Retry with proper JSON escaping (escape `\"` as `\\\"` and newlines "
        "as `\\n`). If it fails again, use `tool_argument_blob` + `source_blob_id`."
    )
    return " ".join(parts)


def _format_tool_argument_blob_raw_args_error(raw: str, err: json.JSONDecodeError) -> str:
    """Explain ``tool_argument_blob`` ``__raw__`` failures (HTML-in-chunk JSON breaks)."""
    return (
        "`tool_argument_blob` did not run: the tool call is not valid JSON. "
        "For webpage HTML, prefer a single `canvas_publish(mode=html, html=...)` "
        "call; the runtime can auto-recover malformed inline HTML and publish it "
        "without this multi-step blob flow. If you are intentionally continuing "
        "blob staging, raw HTML in `chunk` often breaks parsing because JSON "
        "string literals cannot contain raw double quotes from attributes unless "
        "every quote is escaped correctly. "
        f"Parse error: {err.msg}. "
        "For blob staging, retry using `chunk_base64` (standard base64 of UTF-8 "
        "bytes, no data: URL prefix) instead of `chunk`."
    )


def _tool_json_parse_recovery_hint(tool_name: str | None, raw: str) -> str:
    """Append tool-specific guidance so the model retries with a safer transport."""
    if not tool_name:
        return ""
    if tool_name == "code_execution" and '"source"' in raw:
        return ""
    if tool_name in ("emit_ui_tree", "emit_ui_patch"):
        return " Prefer a smaller `tree` or incremental `emit_ui_patch`."
    if tool_name == "canvas_publish":
        return (
            " The runtime usually auto-recovers inline `html`. "
            "If this fails again, try `html_files` (map of path → source) "
            "or `tool_argument_blob` + `html_blob_id` as a last resort."
        )
    if tool_name in ("project_write", "project_apply_patch", "project_edit"):
        return (
            " The runtime usually auto-recovers inline content. "
            "If this fails again, use `*_blob_id` from `tool_argument_blob`."
        )
    if tool_name == "tool_argument_blob":
        return (
            " For webpage HTML, prefer direct `canvas_publish(html=...)`; "
            "for intentional blob append with HTML/JSX use `chunk_base64`."
        )
    return ""


def _json_dumps_limited(value: Any, limit: int = _AUDIT_VALUE_LIMIT) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"


def _uuid_or_none(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError):
        return None


def normalize_tool_parameters(
    parameters: dict[str, Any],
    tool: "BaseTool | None" = None,
) -> tuple[dict[str, Any], str | None]:
    """Normalize tool parameters and recover `__raw__` payloads when possible.

    When *tool* is provided, its :meth:`~BaseTool.recover_raw_args` is
    tried as a final fallback after the generic recovery pipeline.
    """
    params = dict(parameters or {})
    raw_payload = params.get("__raw__")
    if not isinstance(raw_payload, str):
        return params, None

    parsed = _try_parse_raw_tool_args(raw_payload)
    if parsed is not None:
        return parsed, None

    if tool is not None:
        try:
            tool_parsed = tool.recover_raw_args(raw_payload)
        except Exception:  # noqa: BLE001
            tool_parsed = None
        if tool_parsed is not None:
            return tool_parsed, None

    error = "Malformed tool arguments JSON"
    return params, error


# ---------------------------------------------------------------------------
# Dispatch records
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single tool invocation request used by batch dispatch."""

    tool_name: str
    parameters: dict[str, Any]
    call_id: str | None = None

    def __post_init__(self) -> None:
        if self.call_id is None:
            self.call_id = f"{self.tool_name}_{id(self)}"


@dataclass
class ExecutionResult:
    """Per-call record returned by the executor."""

    call_id: str
    tool_name: str
    result: ToolResult
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def duration_ms(self) -> int:
        return int((self.finished_at - self.started_at) * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "result": self.result.to_dict(),
            "duration_ms": self.duration_ms,
        }


@dataclass
class AggregatedResult:
    """Aggregate of multiple :class:`ExecutionResult` instances."""

    results: list[ExecutionResult] = field(default_factory=list)
    total_duration_ms: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def all_successful(self) -> bool:
        return all(r.result.success for r in self.results)

    @property
    def any_successful(self) -> bool:
        return any(r.result.success for r in self.results)

    @property
    def successful_count(self) -> int:
        return sum(1 for r in self.results if r.result.success)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.result.success)

    def get_result(self, call_id: str) -> ExecutionResult | None:
        for result in self.results:
            if result.call_id == call_id:
                return result
        return None

    def get_by_tool(self, tool_name: str) -> list[ExecutionResult]:
        return [r for r in self.results if r.tool_name == tool_name]

    def get_successful(self) -> list[ExecutionResult]:
        return [r for r in self.results if r.result.success]

    def get_failed(self) -> list[ExecutionResult]:
        return [r for r in self.results if not r.result.success]

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [r.to_dict() for r in self.results],
            "total_duration_ms": self.total_duration_ms,
            "successful_count": self.successful_count,
            "failed_count": self.failed_count,
            "all_successful": self.all_successful,
        }


class ToolExecutionError(Exception):
    """Base exception for tool execution errors."""

    def __init__(self, message: str, call_id: str | None = None) -> None:
        self.call_id = call_id
        super().__init__(message)


# ---------------------------------------------------------------------------
# Context coercion
# ---------------------------------------------------------------------------


def _coerce_context(
    value: Any,
    *,
    service_manager: "ServiceManager | None" = None,
    temp_dir: str | None = None,
    extra: dict[str, Any] | None = None,
) -> ToolContext:
    """Return a :class:`ToolContext` built from ``value``.

    Accepts:
    * ``None`` — build a minimal anonymous context
    * :class:`ToolContext` — returned as-is (with optional extra merge)
    * :class:`leagent.agent.base.AgentContext` or any object exposing
      ``user_id`` / ``session_id`` / ``task_id`` / ``_abort_event``
    """
    if isinstance(value, ToolContext):
        if extra:
            value.extra.update(extra)
        return value

    user_id = getattr(value, "user_id", None) if value is not None else None
    session_id = getattr(value, "session_id", None) if value is not None else None
    task_id = getattr(value, "task_id", None) if value is not None else None
    abort_signal = (
        getattr(value, "abort_event", None)
        or getattr(value, "_abort_event", None)
        if value is not None
        else None
    )

    # Seed from the source object's own .extra dict (e.g. ToolUseContext
    # carries ``extra["attachments"]`` that the sandbox needs).
    source_extra = getattr(value, "extra", None)
    merged_extra: dict[str, Any] = dict(source_extra) if isinstance(source_extra, dict) else {}
    if extra:
        merged_extra.update(extra)
    if value is not None and not isinstance(value, ToolContext):
        merged_extra.setdefault("agent_context", value)

    return build_tool_context(
        service_manager=service_manager,
        user_id=user_id,
        session_id=session_id,
        task_id=task_id,
        abort_signal=abort_signal,
        temp_dir=temp_dir,
        extra=merged_extra,
    )


# ---------------------------------------------------------------------------
# ToolExecutor
# ---------------------------------------------------------------------------


class ToolExecutor:
    """Professional tool executor shared by agents and workflows.

    Construction takes a :class:`ToolRegistry` (defaults to the global
    singleton) and an optional :class:`ServiceManager` used to build rich
    :class:`ToolContext` instances whenever the caller doesn't pass one
    explicitly. Instances are stateful (metrics, semaphore) but safe to
    share across concurrent callers.
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        *,
        default_timeout: float = 300.0,
        max_parallel: int = 10,
        permission_context: ToolPermissionContext | None = None,
        service_manager: "ServiceManager | None" = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._default_timeout = default_timeout
        self._max_parallel = max_parallel
        self._semaphore = asyncio.Semaphore(max_parallel)
        self._permission_context = permission_context
        self._service_manager = service_manager
        self._metrics: dict[str, list[int]] = {}
        self._pipeline: MiddlewarePipeline | None = None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def default_timeout(self) -> float:
        return self._default_timeout

    @property
    def service_manager(self) -> "ServiceManager | None":
        return self._service_manager

    def set_service_manager(self, service_manager: "ServiceManager | None") -> None:
        """Attach (or clear) the :class:`ServiceManager` used for contexts."""
        self._service_manager = service_manager

    def set_permission_context(self, ctx: ToolPermissionContext | None) -> None:
        self._permission_context = ctx

    def set_pipeline(self, pipeline: MiddlewarePipeline | None) -> None:
        """Attach a custom middleware pipeline."""
        self._pipeline = pipeline

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        context: Any = None,
        *,
        call_id: str | None = None,
        on_progress: ToolProgressCallback | None = None,
        temp_dir: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute a single tool and return a rich :class:`ExecutionResult`.

        ``context`` may be a :class:`ToolContext`, an :class:`AgentContext`
        (or anything with ``user_id``/``session_id``), or ``None``; it is
        coerced into a full :class:`ToolContext` using the attached
        :class:`ServiceManager`.
        """
        call_id = call_id or f"{tool_name}_{uuid4().hex[:8]}"
        started_at = time.monotonic()

        try:
            tool = self._registry.get(tool_name)
        except ToolNotFoundError:
            logger.error("tool_not_found", tool=tool_name, call_id=call_id)
            return ExecutionResult(
                call_id=call_id,
                tool_name=tool_name,
                result=ToolResult.fail(f"Tool not found: {tool_name}"),
                started_at=started_at,
                finished_at=time.monotonic(),
            )

        if not tool.is_enabled:
            return ExecutionResult(
                call_id=call_id,
                tool_name=tool_name,
                result=ToolResult.fail(f"Tool '{tool_name}' is disabled"),
                started_at=started_at,
                finished_at=time.monotonic(),
            )

        normalized_params, normalize_error = normalize_tool_parameters(parameters, tool=tool)
        if normalize_error:
            raw_for_log = str(parameters.get("__raw__", "") or "")
            strict_err = strict_json_loads_error(raw_for_log) if raw_for_log else None
            result_error = format_tool_arguments_json_error(
                raw_for_log, strict_err, tool_name=tool_name,
            )
            blob_hint = any(
                s in raw_for_log
                for s in ("_blob_id", '"blob_id"')
            )
            logger.warning(
                "tool_args_parse_failed",
                tool=tool_name,
                call_id=call_id,
                args_len=len(raw_for_log),
                json_error=str(strict_err) if strict_err else None,
                json_lineno=getattr(strict_err, "lineno", None),
                json_colno=getattr(strict_err, "colno", None),
                json_pos=getattr(strict_err, "pos", None),
                raw_preview=raw_for_log[:400],
                tool_arguments_json_unrecoverable=True,
                blob_id_hint_present=blob_hint,
            )
            return ExecutionResult(
                call_id=call_id,
                tool_name=tool_name,
                result=ToolResult.fail(result_error),
                started_at=started_at,
                finished_at=time.monotonic(),
            )
        parameters = normalized_params

        merged_ctx_extra: dict[str, Any] = dict(extra or {})
        merged_ctx_extra["current_tool_call_id"] = call_id

        tool_ctx = _coerce_context(
            context,
            service_manager=self._service_manager,
            temp_dir=temp_dir,
            extra=merged_ctx_extra,
        )

        if on_progress:
            on_progress({"type": "tool_start", "tool": tool_name, "call_id": call_id})

        logger.info(
            "tool_execute_start",
            tool=tool_name,
            call_id=call_id,
            params=self._sanitize_params(parameters),
        )

        if self._pipeline is not None:
            mw_ctx = MiddlewareContext(
                tool_name=tool_name,
                parameters=parameters,
                call_id=call_id,
                tool_context=tool_ctx,
                registry=self._registry,
            )
            result = await self._pipeline.execute(
                mw_ctx,
                lambda ctx: self._execute_core(ctx, on_progress=on_progress),
            )
        else:
            if self._permission_context is not None:
                perm = check_tool_permission(
                    tool, parameters, self._permission_context, tool_context=tool_ctx,
                )
                if not perm.allowed:
                    return ExecutionResult(
                        call_id=call_id,
                        tool_name=tool_name,
                        result=ToolResult.fail(f"Permission denied: {perm.reason}"),
                        started_at=started_at,
                        finished_at=time.monotonic(),
                    )
                if perm.updated_params:
                    parameters = perm.updated_params

            rate_lim, _ = tool_rate_limit_from_env()
            if rate_lim is not None:
                uid = (getattr(tool_ctx, "user_id", None) or "anon")[:200]
                if not rate_lim.allow(f"{uid}\x00{tool_name}"):
                    return ExecutionResult(
                        call_id=call_id,
                        tool_name=tool_name,
                        result=ToolResult.fail(
                            "Tool rate limit exceeded for this user; retry shortly."
                        ),
                        started_at=started_at,
                        finished_at=time.monotonic(),
                    )

            async with self._semaphore:
                from leagent.telemetry.otel import get_tracer

                tracer = get_tracer("leagent.tools.executor")
                with tracer.start_as_current_span("agent.tool") as _span:
                    if hasattr(_span, "set_attribute"):
                        _span.set_attribute("tool.name", tool_name)
                    result = await tool.run(parameters, tool_ctx, on_progress=on_progress)

        finished_at = time.monotonic()
        execution_result = ExecutionResult(
            call_id=call_id,
            tool_name=tool_name,
            result=result,
            started_at=started_at,
            finished_at=finished_at,
        )

        self._record_metric(tool_name, execution_result.duration_ms, result.success)
        try:
            from leagent.utils.metrics import get_metrics

            get_metrics().record_tool_execution(
                tool_name,
                execution_result.duration_ms / 1000.0,
                result.success,
                "tool_error" if not result.success else None,
            )
        except Exception:  # noqa: BLE001
            logger.debug("tool_prometheus_metrics_failed", tool=tool_name)
        await self._audit_tool_execution(
            tool_name=tool_name,
            parameters=parameters,
            tool_ctx=tool_ctx,
            result=result,
            duration_ms=execution_result.duration_ms,
        )

        if on_progress:
            on_progress({
                "type": "tool_end",
                "tool": tool_name,
                "call_id": call_id,
                "success": result.success,
                "duration_ms": execution_result.duration_ms,
            })

        log_method = logger.info if result.success else logger.warning
        log_method(
            "tool_execute_completed",
            tool=tool_name,
            call_id=call_id,
            success=result.success,
            duration_ms=execution_result.duration_ms,
        )

        return execution_result

    async def _audit_tool_execution(
        self,
        *,
        tool_name: str,
        parameters: dict[str, Any],
        tool_ctx: ToolContext,
        result: ToolResult,
        duration_ms: int,
    ) -> None:
        pass

    async def _execute_core(
        self,
        ctx: MiddlewareContext,
        *,
        on_progress: ToolProgressCallback | None = None,
    ) -> ToolResult:
        """Execute the actual tool run inside the semaphore."""
        tool = self._registry.get(ctx.tool_name)
        async with self._semaphore:
            return await tool.run(ctx.parameters, ctx.tool_context, on_progress=on_progress)

    async def execute_call(
        self,
        call: ToolCall,
        context: Any = None,
        *,
        on_progress: ToolProgressCallback | None = None,
    ) -> ExecutionResult:
        return await self.execute(
            call.tool_name,
            call.parameters,
            context,
            call_id=call.call_id,
            on_progress=on_progress,
        )

    # ------------------------------------------------------------------
    # Convenience facade for the agent layer
    # ------------------------------------------------------------------

    async def run_tool(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        context: Any = None,
        *,
        timeout: int | None = None,
        retries: int | None = None,
        on_progress: ToolProgressCallback | None = None,
        temp_dir: str | None = None,
        call_id: str | None = None,
    ) -> ToolResult:
        """Execute one tool, returning the flat :class:`ToolResult` envelope.

        Convenience used by :class:`AgentController`. Per-call ``timeout``
        and ``retries`` override the tool's class-level defaults for the
        duration of this call.
        """
        tool = self._registry.get_optional(tool_name)
        original_timeout = getattr(tool, "timeout_sec", None) if tool else None
        original_retries = getattr(tool, "max_retries", None) if tool else None
        restore_timeout = timeout is not None and tool is not None
        restore_retries = retries is not None and tool is not None

        try:
            if restore_timeout:
                tool.timeout_sec = int(timeout)  # type: ignore[attr-defined,union-attr]
            if restore_retries:
                tool.max_retries = int(retries)  # type: ignore[attr-defined,union-attr]

            exec_result = await self.execute(
                tool_name,
                parameters,
                context,
                on_progress=on_progress,
                temp_dir=temp_dir,
                call_id=call_id,
            )
        finally:
            if restore_timeout and tool is not None and original_timeout is not None:
                tool.timeout_sec = original_timeout  # type: ignore[attr-defined]
            if restore_retries and tool is not None and original_retries is not None:
                tool.max_retries = original_retries  # type: ignore[attr-defined]

        # Annotate duration from the wrapper when the inner envelope
        # didn't record it (ToolResult.fail paths).
        if exec_result.result.duration_ms == 0:
            exec_result.result.duration_ms = exec_result.duration_ms
        return exec_result.result

    async def run_tools_parallel(
        self,
        tool_calls: "Sequence[Any]",
        context: Any = None,
        *,
        fail_fast: bool = False,
        timeout: float | None = None,
        on_progress: ToolProgressCallback | None = None,
    ) -> list[ToolResult]:
        """Run multiple tool calls in parallel, returning flat :class:`ToolResult`s.

        Accepts either :class:`ToolCall` or any object with ``.name`` /
        ``.arguments`` (e.g. :class:`leagent.agent.base.ToolCall`).
        Order is preserved.
        """
        calls = [_normalize_call(c) for c in tool_calls]
        if not calls:
            return []
        aggregated = await self.execute_parallel(
            calls, context,
            timeout=timeout, fail_fast=fail_fast, on_progress=on_progress,
        )
        by_id = {r.call_id: r.result for r in aggregated.results}
        out: list[ToolResult] = []
        for c in calls:
            result = by_id.get(c.call_id or "")
            out.append(result or ToolResult.fail("Missing execution result"))
        return out

    async def run_tools_sequential(
        self,
        tool_calls: "Sequence[Any]",
        context: Any = None,
        *,
        stop_on_error: bool = True,
        on_progress: ToolProgressCallback | None = None,
    ) -> list[ToolResult]:
        calls = [_normalize_call(c) for c in tool_calls]
        results: list[ToolResult] = []
        for call in calls:
            exec_result = await self.execute_call(call, context, on_progress=on_progress)
            results.append(exec_result.result)
            if stop_on_error and not exec_result.result.success:
                break
        return results

    # ------------------------------------------------------------------
    # Batch dispatch primitives
    # ------------------------------------------------------------------

    def partition_calls(
        self, calls: "Sequence[ToolCall]",
    ) -> tuple[list[ToolCall], list[ToolCall]]:
        """Partition calls into (concurrent_safe, serial) groups."""
        concurrent_safe: list[ToolCall] = []
        serial: list[ToolCall] = []
        for call in calls:
            tool = self._registry.get_optional(call.tool_name)
            if tool and getattr(tool, "is_concurrency_safe", False):
                concurrent_safe.append(call)
            else:
                serial.append(call)
        return concurrent_safe, serial

    async def execute_partitioned(
        self,
        calls: "Sequence[ToolCall]",
        context: Any = None,
        *,
        on_progress: ToolProgressCallback | None = None,
    ) -> AggregatedResult:
        """Concurrent-safe tools run in parallel; the rest serially."""
        if not calls:
            return AggregatedResult()

        started_at = time.monotonic()
        concurrent_safe, serial = self.partition_calls(calls)
        all_results: list[ExecutionResult] = []

        if concurrent_safe:
            parallel = await self.execute_parallel(
                concurrent_safe, context, on_progress=on_progress,
            )
            all_results.extend(parallel.results)

        for call in serial:
            result = await self.execute_call(call, context, on_progress=on_progress)
            all_results.append(result)

        finished_at = time.monotonic()
        try:
            from leagent.utils.metrics import get_metrics

            get_metrics().record_agent_turn_phase(
                "tool_execute_partitioned",
                finished_at - started_at,
                status="success" if all(r.result.success for r in all_results) else "failure",
            )
        except Exception:
            logger.debug("tool_partition_metrics_failed", exc_info=True)
        return AggregatedResult(
            results=all_results,
            total_duration_ms=int((finished_at - started_at) * 1000),
            started_at=started_at,
            finished_at=finished_at,
        )

    async def execute_parallel(
        self,
        calls: "Sequence[ToolCall]",
        context: Any = None,
        *,
        timeout: float | None = None,
        fail_fast: bool = False,
        on_progress: ToolProgressCallback | None = None,
    ) -> AggregatedResult:
        """Execute many calls concurrently with optional fail-fast."""
        if not calls:
            return AggregatedResult()

        timeout = timeout or self._default_timeout
        started_at = time.monotonic()

        logger.info(
            "tool_execute_parallel",
            tool_count=len(calls),
            tools=[c.tool_name for c in calls],
            timeout=timeout,
        )

        tasks: list[asyncio.Task[ExecutionResult]] = [
            asyncio.create_task(
                self.execute_call(call, context, on_progress=on_progress),
                name=f"tool_{call.call_id}",
            )
            for call in calls
        ]

        if fail_fast:
            results = await self._execute_fail_fast(tasks, timeout)
        else:
            results = await self._execute_wait_all(tasks, timeout)

        finished_at = time.monotonic()
        aggregated = AggregatedResult(
            results=results,
            total_duration_ms=int((finished_at - started_at) * 1000),
            started_at=started_at,
            finished_at=finished_at,
        )
        logger.info(
            "tool_execute_parallel_done",
            total_duration_ms=aggregated.total_duration_ms,
            successful=aggregated.successful_count,
            failed=aggregated.failed_count,
        )
        try:
            from leagent.utils.metrics import get_metrics

            get_metrics().record_agent_turn_phase(
                "tool_execute_parallel",
                finished_at - started_at,
                status="success" if aggregated.failed_count == 0 else "failure",
            )
        except Exception:
            logger.debug("tool_parallel_metrics_failed", exc_info=True)
        return aggregated

    async def _execute_wait_all(
        self,
        tasks: list[asyncio.Task[ExecutionResult]],
        timeout: float,
    ) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        try:
            done, pending = await asyncio.wait(
                tasks, timeout=timeout, return_when=asyncio.ALL_COMPLETED,
            )
            for task in done:
                try:
                    results.append(task.result())
                except Exception as e:  # noqa: BLE001
                    logger.error("tool_task_failed", error=str(e))
            for task in pending:
                task.cancel()
                task_name = task.get_name()
                results.append(
                    ExecutionResult(
                        call_id=task_name,
                        tool_name=task_name.replace("tool_", "", 1),
                        result=ToolResult.fail(f"Execution timed out after {timeout}s"),
                        started_at=0,
                        finished_at=time.monotonic(),
                    )
                )
        except Exception as e:  # noqa: BLE001
            logger.error("tool_execute_parallel_failed", error=str(e))
            for task in tasks:
                if not task.done():
                    task.cancel()
        return results

    async def _execute_fail_fast(
        self,
        tasks: list[asyncio.Task[ExecutionResult]],
        timeout: float,
    ) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        pending = set(tasks)
        try:
            async with asyncio.timeout(timeout):
                while pending:
                    done, pending = await asyncio.wait(
                        pending, return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        try:
                            result = task.result()
                            results.append(result)
                            if not result.result.success:
                                logger.warning(
                                    "tool_fail_fast_cancel",
                                    failed_tool=result.tool_name,
                                    remaining=len(pending),
                                )
                                for p in pending:
                                    p.cancel()
                                pending.clear()
                                break
                        except Exception as e:  # noqa: BLE001
                            logger.error("tool_task_failed", error=str(e))
        except asyncio.TimeoutError:
            logger.warning("tool_fail_fast_timeout", timeout=timeout)
            for task in pending:
                task.cancel()
        return results

    async def execute_sequential(
        self,
        calls: "Sequence[ToolCall]",
        context: Any = None,
        *,
        stop_on_failure: bool = False,
        on_progress: ToolProgressCallback | None = None,
    ) -> AggregatedResult:
        if not calls:
            return AggregatedResult()

        started_at = time.monotonic()
        results: list[ExecutionResult] = []
        for call in calls:
            result = await self.execute_call(call, context, on_progress=on_progress)
            results.append(result)
            if stop_on_failure and not result.result.success:
                logger.warning(
                    "tool_sequential_stopped",
                    failed_tool=call.tool_name,
                    completed=len(results),
                    remaining=len(calls) - len(results),
                )
                break

        finished_at = time.monotonic()
        return AggregatedResult(
            results=results,
            total_duration_ms=int((finished_at - started_at) * 1000),
            started_at=started_at,
            finished_at=finished_at,
        )

    async def execute_with_dependencies(
        self,
        calls: dict[str, ToolCall],
        dependencies: dict[str, list[str]],
        context: Any = None,
    ) -> AggregatedResult:
        started_at = time.monotonic()
        results: dict[str, ExecutionResult] = {}
        completed: set[str] = set()

        def get_ready() -> list[str]:
            ready = []
            for call_id in calls:
                if call_id in completed:
                    continue
                deps = dependencies.get(call_id, [])
                if all(d in completed for d in deps):
                    ready.append(call_id)
            return ready

        while len(completed) < len(calls):
            ready = get_ready()
            if not ready:
                missing = set(calls.keys()) - completed
                logger.error("tool_dependency_cycle", unresolved=list(missing))
                break
            batch_calls = [calls[call_id] for call_id in ready]
            batch_result = await self.execute_parallel(batch_calls, context)
            for exec_result in batch_result.results:
                results[exec_result.call_id] = exec_result
                completed.add(exec_result.call_id)

        finished_at = time.monotonic()
        return AggregatedResult(
            results=list(results.values()),
            total_duration_ms=int((finished_at - started_at) * 1000),
            started_at=started_at,
            finished_at=finished_at,
        )

    # ------------------------------------------------------------------
    # Metrics and introspection
    # ------------------------------------------------------------------

    def get_tool_stats(self, tool_name: str) -> dict[str, Any]:
        durations = self._metrics.get(tool_name, [])
        if not durations:
            return {
                "count": 0,
                "avg_duration_ms": 0,
                "min_duration_ms": 0,
                "max_duration_ms": 0,
            }
        return {
            "count": len(durations),
            "avg_duration_ms": sum(durations) // len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
        }

    def _record_metric(self, tool_name: str, duration_ms: int, success: bool) -> None:
        bucket = self._metrics.setdefault(tool_name, [])
        bucket.append(duration_ms)
        if len(bucket) > 1000:
            del bucket[:500]

    def _sanitize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for k, v in (params or {}).items():
            key_lower = k.lower()
            if any(s in key_lower for s in SENSITIVE_KEYS):
                sanitized[k] = "***REDACTED***"
            elif isinstance(v, str) and len(v) > 500:
                sanitized[k] = v[:100] + "...[truncated]"
            else:
                sanitized[k] = v
        return sanitized

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Shutdown hook. The executor owns no long-lived resources."""
        return None

    @classmethod
    def get_default(cls) -> "ToolExecutor":
        """Return the process-wide default executor."""
        return get_executor()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_call(call: Any) -> ToolCall:
    """Coerce any call-like object into a :class:`ToolCall`."""
    if isinstance(call, ToolCall):
        return call
    # leagent.agent.base.ToolCall (pydantic) exposes .name and .arguments
    name = getattr(call, "name", None) or getattr(call, "tool_name", None)
    args = getattr(call, "arguments", None) or getattr(call, "parameters", None) or {}
    call_id = getattr(call, "id", None) or getattr(call, "call_id", None)
    if not name:
        raise ValueError(f"Cannot derive tool name from {call!r}")
    return ToolCall(tool_name=name, parameters=dict(args), call_id=call_id)


_default_executor: ToolExecutor | None = None


def get_executor() -> ToolExecutor:
    """Return the process-wide default :class:`ToolExecutor`."""
    global _default_executor
    if _default_executor is None:
        _default_executor = ToolExecutor()
    return _default_executor


def reset_executor() -> None:
    """Reset the default executor (mainly for testing)."""
    global _default_executor
    _default_executor = None


__all__ = [
    "ToolCall",
    "ExecutionResult",
    "AggregatedResult",
    "ToolExecutionError",
    "ToolExecutor",
    "get_executor",
    "reset_executor",
]
