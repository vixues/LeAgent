"""Assemble persisted ``Message`` columns from streamed agent output.

These helpers fold the incremental data produced during a stream (thinking
fragments, UI replay state, tool replies, workflow embeds) into the JSON/text
columns stored on the chat ``Message`` row. Pure functions — no DB access — so
they are unit-testable and reusable by any persistence path.
"""

from __future__ import annotations

import json
from typing import Any


def merge_message_extensions_json(
    workflow_json: str | None,
    *,
    thinking: str | None = None,
    task_progress: list[dict[str, Any]] | None = None,
    gen_ui: dict[str, Any] | None = None,
    pet_bubble: dict[str, Any] | None = None,
) -> str | None:
    """Merge workflow/embed JSON with UI replay fields for the ``extensions`` column."""
    merged: dict[str, Any] = {}
    if workflow_json:
        try:
            parsed = json.loads(workflow_json)
            if isinstance(parsed, dict):
                merged.update(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    if thinking and str(thinking).strip():
        merged["thinking"] = str(thinking).strip()
    if task_progress:
        merged["task_progress"] = task_progress
    if gen_ui:
        merged["gen_ui"] = gen_ui
    if pet_bubble:
        merged["pet_bubble"] = pet_bubble
    return json.dumps(merged, ensure_ascii=False) if merged else None


def merge_stream_thinking_for_persist(prev: str | None, raw_thought: str) -> str | None:
    """Fold successive ``thinking`` stream fragments for DB persistence.

    Cumulative fragments (each new string starts with the previous full text)
    replace the stored value; discrete fragments append with newlines.
    """
    if not isinstance(raw_thought, str) or not raw_thought.strip():
        return prev
    t = raw_thought.strip()
    base = (prev or "").strip()
    if not base:
        return t
    if t.startswith(base):
        return t
    return f"{base}\n{t}"


def parse_tool_replies_json(raw: str | None) -> list[dict[str, Any]]:
    """Parse a stored ``tool_replies`` JSON blob into normalized reply dicts."""
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tid = item.get("tool_call_id") or item.get("tool_use_id") or item.get("id")
        content = item.get("content")
        if tid is not None and content is not None:
            out.append({"tool_call_id": str(tid), "content": str(content)})
    return out
