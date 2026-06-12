"""Authoring helpers: convert human-friendly workflow definitions to the canonical shape.

This is NOT a schema migration layer. The engine exposes a single canonical
document shape (see :mod:`leagent.workflow.io.loader`). Two sources still
need a light conversion to reach that shape:

* **LLM-authored chat workflow embeds** (``chat_workflow_embed_emit``)
  — models may emit a flat ``nodes: [...]`` list with type strings like
  ``"tool_call"`` and top-level control keys (``next``, ``conditions``,
  ``error_handler``); that surface is easier to generate than the
  runtime-optimized ``nodes: {id: {class_type, control}}`` dict.
* **scripts/workflow/migrate_flows.py** — the one-shot upgrade tool for
  historical DB rows.

Both funnel through :func:`to_canonical`, which produces the canonical
document that :func:`leagent.workflow.io.load` accepts. Stored data
(flows table, templates, chat embed extensions) is always canonical.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


_TYPE_TO_CLASS: dict[str, str] = {
    "start": "StartNode",
    "end": "EndNode",
    # ComfyUI / LiteGraph shorthand LLMs often emit instead of StartNode/EndNode.
    "input": "StartNode",
    "output": "EndNode",
    # Generic processing step (not a socket/widget default).
    "default": "ToolCallNode",
    "generic": "ToolCallNode",
    "tool": "ToolCallNode",
    "tool_call": "ToolCallNode",
    "llm_call": "LLMCallNode",
    "condition": "ConditionNode",
    "parallel": "ParallelNode",
    "human_review": "HumanReviewNode",
    "error_handler": "ErrorHandlerNode",
    "transform": "TransformNode",
    "subworkflow": "SubworkflowNode",
    "wait": "WaitNode",
    "script": "ScriptNode",
    "script_agent": "ScriptAgentNode",
    "code_agent": "ScriptAgentNode",  # legacy authoring id → same node
}

# Editors and LLMs often emit camelCase (e.g. ``toolCall``) instead of ``tool_call``.
for _snake_key, _cls in list(_TYPE_TO_CLASS.items()):
    if "_" not in _snake_key:
        continue
    _parts = _snake_key.split("_")
    _camel = _parts[0] + "".join(p[:1].upper() + p[1:] if p else "" for p in _parts[1:])
    _TYPE_TO_CLASS.setdefault(_camel, _cls)

# LLMs often emit camelCase + ``Node`` suffix (e.g. ``startNode``, ``toolCallNode``).
for _cls in set(_TYPE_TO_CLASS.values()):
    if _cls.endswith("Node") and len(_cls) > 4:
        _camel_node = _cls[0].lower() + _cls[1:]
        _TYPE_TO_CLASS.setdefault(_camel_node, _cls)

# Prefer snake_case as the canonical authoring id when reversing class_type.
_CLASS_TO_TYPE: dict[str, str] = {}
for _k, _v in sorted(_TYPE_TO_CLASS.items(), key=lambda kv: (0 if "_" in kv[0] else 1, kv[0])):
    _CLASS_TO_TYPE.setdefault(_v, _k)
# Prefer ``script_agent`` as the canonical authoring id (``code_agent`` is legacy).
_CLASS_TO_TYPE["ScriptAgentNode"] = "script_agent"

_KNOWN_AUTHORING_TYPES: set[str] = set(_TYPE_TO_CLASS.keys())

_INPUT_KEYS: tuple[str, ...] = (
    "tool",
    "params",
    "prompt",
    "model",
    "temperature",
    "max_tokens",
    "transform",
    "subworkflow_id",
    "subworkflow_inputs",
    "reviewer",
    "review_prompt",
    "timeout_sec",
    "retry_count",
    "retry_delay_sec",
    "merge_strategy",
    "output",
    "source",
    "inputs",
    "allow_modules",
    "emit_locals",
    "max_iterations",
    "allowed_tools",
)

_CONTROL_KEYS: tuple[str, ...] = (
    "next",
    "error_handler",
    "else",
    "else_node",
    "on_reject",
    "conditions",
    "branches",
)


def _normalize_registered_class_type(class_type: str) -> str:
    """Map short LLM aliases (e.g. ``tool``) to registered ``*Node`` class names."""
    text = class_type.strip()
    if not text:
        return text
    mapped = _TYPE_TO_CLASS.get(text)
    if mapped is not None:
        return mapped
    if text in _CLASS_TO_TYPE:
        return text
    return class_type_for(text)


def _finalize_canonical_document(canon: dict[str, Any]) -> dict[str, Any]:
    """Normalize node class aliases and synthesize missing start/end boundary nodes."""
    out = dict(canon)
    nodes_raw = out.get("nodes")
    if not isinstance(nodes_raw, dict):
        return out

    nodes: dict[str, dict[str, Any]] = {}
    for node_id, node_def in nodes_raw.items():
        if not isinstance(node_def, dict):
            continue
        spec = dict(node_def)
        class_type = spec.get("class_type")
        if isinstance(class_type, str):
            spec["class_type"] = _normalize_registered_class_type(class_type)
        nodes[str(node_id)] = spec

    control_raw = out.get("control")
    control = dict(control_raw) if isinstance(control_raw, dict) else {}
    start_id = _safe_str(control.get("start")) or "start"
    end_id = _safe_str(control.get("end")) or "end"
    control["start"] = start_id
    control["end"] = end_id

    if start_id not in nodes:
        entry = next(iter(nodes.keys()), None)
        start_control: dict[str, Any] = {}
        if entry is not None:
            start_control["next"] = entry
        nodes[start_id] = {
            "class_type": "StartNode",
            "inputs": {},
            "meta": {"name": "Start"},
            "control": start_control,
        }

    if end_id not in nodes:
        nodes[end_id] = {
            "class_type": "EndNode",
            "inputs": {},
            "meta": {"name": "End"},
            "control": {},
        }

    out["nodes"] = nodes
    out["control"] = control
    return out


def class_type_for(type_str: str) -> str:
    """Map an authoring type string to its canonical ``class_type``."""
    mapped = _TYPE_TO_CLASS.get(type_str)
    if mapped is not None:
        return mapped
    if type_str.endswith("Node") and type_str[0].islower() and len(type_str) > 4:
        pascal = type_str[0].upper() + type_str[1:]
        mapped = _TYPE_TO_CLASS.get(pascal)
        if mapped is not None:
            return mapped
        return pascal
    return type_str


def _safe_str(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return None


def _infer_authoring_type(node: dict[str, Any], node_id: str) -> str:
    """Best-effort infer authoring node type from editor-shaped payloads."""
    raw_type = _safe_str(node.get("type"))
    if raw_type and raw_type != "generic":
        return raw_type

    class_type = _safe_str(node.get("class_type"))
    if class_type and class_type in _CLASS_TO_TYPE:
        return _CLASS_TO_TYPE[class_type]

    data = node.get("data")
    if isinstance(data, dict):
        for key in ("type", "icon"):
            candidate = _safe_str(data.get(key))
            if candidate and candidate in _KNOWN_AUTHORING_TYPES:
                return candidate

    for key in ("icon", "node_type"):
        candidate = _safe_str(node.get(key))
        if candidate and candidate in _KNOWN_AUTHORING_TYPES:
            return candidate

    if raw_type == "generic":
        logger.warning(
            "workflow_generic_type_fallback",
            extra={"node_id": node_id, "fallback_type": "tool_call"},
        )
    return "tool_call"


def to_canonical(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert an authoring dict into the canonical workflow document shape.

    Accepts either:

    1. ``{"workflow": {...}}`` — unwrap.
    2. ``{nodes: [...], edges: [...], inputs, outputs, start_node, end_node}``
       — the flat authoring shape.

    Already-canonical documents (``nodes`` is a dict, ``control`` is a dict)
    are returned unchanged.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"Workflow document must be a mapping, got {type(raw).__name__}")

    if "workflow" in raw and isinstance(raw["workflow"], dict):
        raw = raw["workflow"]

    if isinstance(raw.get("nodes"), dict) and isinstance(raw.get("control"), dict):
        return _finalize_canonical_document(dict(raw))

    legacy_nodes: list[dict[str, Any]] = list(raw.get("nodes", []) or [])

    normalized_nodes: list[dict[str, Any]] = []
    for node in legacy_nodes:
        data = node.get("data") if isinstance(node, dict) else None
        has_editor_shell = (
            isinstance(node, dict)
            and isinstance(data, dict)
            and (
                "type" in data
                or "class_type" in data
                or "type" in node
                or "class_type" in node
            )
        )
        if has_editor_shell:
            merged: dict[str, Any] = {
                **data,
                "id": node.get("id", ""),
                "metadata": node.get("metadata", {}) or {},
            }
            if merged.get("type") is None and node.get("type") is not None:
                merged["type"] = node["type"]
            if merged.get("class_type") is None and node.get("class_type") is not None:
                merged["class_type"] = node["class_type"]
            # React Flow / editor: tool_inputs matches engine input id ``params``.
            if merged.get("params") is None and merged.get("tool_inputs") is not None:
                merged["params"] = merged["tool_inputs"]
            normalized_nodes.append(merged)
        else:
            normalized_nodes.append(node)

    canonical_nodes: dict[str, dict[str, Any]] = {}
    for node in normalized_nodes:
        node_id = node.get("id")
        if not node_id:
            continue
        raw_type = _infer_authoring_type(node, str(node_id))
        class_type = class_type_for(raw_type)

        inputs: dict[str, Any] = {}
        for key in _INPUT_KEYS:
            if key in node and node[key] is not None:
                inputs[key] = node[key]

        control: dict[str, Any] = {}
        for key in _CONTROL_KEYS:
            if key in node and node[key] is not None:
                control[key] = node[key]

        canonical_nodes[node_id] = {
            "class_type": class_type,
            "inputs": inputs,
            "meta": {
                "name": node.get("name", "") or node.get("label", ""),
                "description": node.get("description", ""),
                **(node.get("metadata", {}) or {}),
            },
            "control": control,
        }

    control_block: dict[str, Any] = {
        "start": raw.get("start_node") or raw.get("start") or "start",
        "end": raw.get("end_node") or raw.get("end") or "end",
        "edges": list(raw.get("edges", []) or []),
        "timeout_sec": raw.get("timeout_sec", 3600),
        "max_retries": raw.get("max_retries", 3),
        "tags": list(raw.get("tags", []) or []),
    }

    return _finalize_canonical_document({
        "id": raw.get("id", "") or "",
        "name": raw.get("name", "Unnamed Workflow") or "Unnamed Workflow",
        "description": raw.get("description", "") or "",
        "inputs": list(raw.get("inputs", []) or []),
        "outputs": list(raw.get("outputs", []) or []),
        "metadata": dict(raw.get("metadata", {}) or {}),
        "nodes": canonical_nodes,
        "control": control_block,
    })
