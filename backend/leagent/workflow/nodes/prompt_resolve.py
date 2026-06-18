"""Resolve workflow node ``prompt`` fields from widgets, templates, or Start bags."""

from __future__ import annotations

import json
from typing import Any

# Keys checked when an upstream Start node passes the workflow input bag.
_PROMPT_KEYS = ("prompt", "task", "query", "message", "text", "input")


def resolve_node_prompt(raw: Any, state: Any | None) -> str:
    """Turn a prompt widget, template string, or Start ``inputs`` bag into text.

    When ``StartNode`` is linked into ``prompt``, ``raw`` is the workflow input
    mapping (``state.inputs``). We prefer an explicit ``prompt`` (or similar)
    field, then fall back to workflow-level inputs on ``state``.
    """
    value = raw

    if isinstance(value, dict):
        for key in _PROMPT_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                value = candidate
                break
        else:
            if state is not None:
                for key in _PROMPT_KEYS:
                    candidate = _input_from_state(state, key)
                    if candidate:
                        value = candidate
                        break
                else:
                    value = json.dumps(value, ensure_ascii=False)
            else:
                value = json.dumps(value, ensure_ascii=False)

    if value is None:
        value = ""

    if not isinstance(value, str):
        value = str(value)

    text = value.strip()
    if not text and state is not None:
        for key in _PROMPT_KEYS:
            candidate = _input_from_state(state, key)
            if candidate:
                text = candidate
                break

    if state is not None and text:
        resolved = state.resolve_template(text)
        if isinstance(resolved, str):
            return resolved.strip()
        if resolved is not None:
            return str(resolved).strip()

    return text


def _input_from_state(state: Any, key: str) -> str | None:
    inputs = getattr(state, "inputs", None) or {}
    if isinstance(inputs, dict):
        val = inputs.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    variables = getattr(state, "variables", None) or {}
    if isinstance(variables, dict):
        val = variables.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None
