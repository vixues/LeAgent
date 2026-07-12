"""Shared helpers for the agent running-trace plane."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4


SPAN_KINDS = frozenset(
    {
        "agent",
        "llm",
        "tool",
        "approval",
        "compact",
        "subagent",
        "error",
        "event",
    }
)


def new_span_id() -> str:
    return uuid4().hex


def new_experiment_id() -> str:
    return uuid4().hex


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:32]


def truncate_preview(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    else:
        text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def dumps_json(value: Any | None) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps(str(value), ensure_ascii=False)


def loads_json(raw: str | None, default: Any = None) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


__all__ = [
    "SPAN_KINDS",
    "dumps_json",
    "loads_json",
    "new_experiment_id",
    "new_span_id",
    "prompt_hash",
    "truncate_preview",
]
