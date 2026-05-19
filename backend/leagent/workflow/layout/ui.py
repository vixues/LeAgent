"""Build the ``ui`` sibling block attached to ``Flow.data`` payloads.

The frontend consumes two representations from ``Flow.data``:

* The canonical workflow document (``nodes`` as a dict keyed by node
  id, with ``class_type`` + ``control`` + ``meta`` per node) — used by
  the execution engine and validator.
* An optional ``ui`` block containing a ReactFlow-shaped ``nodes`` list
  (with ``position`` and ``data``) plus a pre-computed ``edges`` list.
  When present, the frontend skips its ad-hoc grid placement and renders
  the canvas immediately.

Keeping the UI projection as a sibling block (rather than replacing the
canonical shape) means the engine read paths stay untouched — they
continue to ignore unknown top-level keys — while the canvas gets a
deterministic, overlap-free layout the first time a template is
applied.
"""

from __future__ import annotations

from typing import Any

from .edges import LayoutEdge, extract_edges
from .engine import LayoutOptions, compute_layout


# Map canonical `class_type` → frontend category + authoring `type`.
# Mirrors the TypeScript mapping in `engineWorkflowToReactFlow` so
# nodes rendered from the backend-computed UI block look identical to
# nodes rendered by the legacy client-side fallback path.
_CLASS_TO_TYPE: dict[str, str] = {
    "StartNode": "start",
    "EndNode": "end",
    "ToolCallNode": "tool_call",
    "LLMCallNode": "llm_call",
    "ConditionNode": "condition",
    "ParallelNode": "parallel",
    "HumanReviewNode": "human_review",
    "ErrorHandlerNode": "error_handler",
    "TransformNode": "transform",
    "SubworkflowNode": "subworkflow",
    "WaitNode": "wait",
}

_TYPE_TO_CATEGORY: dict[str, str] = {
    "start": "trigger",
    "end": "trigger",
    "tool_call": "web",
    "llm_call": "llm",
    "condition": "condition",
    "parallel": "loop",
    "human_review": "notification",
    "error_handler": "transform",
    "transform": "transform",
    "subworkflow": "transform",
    "wait": "delay",
    "delay": "delay",
    "webhook": "webhook",
}


def _node_type(spec: dict[str, Any]) -> str:
    class_type = spec.get("class_type")
    if isinstance(class_type, str) and class_type in _CLASS_TO_TYPE:
        return _CLASS_TO_TYPE[class_type]
    raw_type = spec.get("type")
    if isinstance(raw_type, str) and raw_type:
        return raw_type
    return "tool_call"


def _node_label(node_id: str, spec: dict[str, Any]) -> str:
    meta = spec.get("meta") or spec.get("metadata") or {}
    if isinstance(meta, dict):
        name = meta.get("name")
        if isinstance(name, str) and name.strip():
            return name
    # Authoring shape stores `name` at top level.
    name = spec.get("name")
    if isinstance(name, str) and name.strip():
        return name
    return node_id


def _node_description(spec: dict[str, Any]) -> str | None:
    inputs = spec.get("inputs")
    if isinstance(inputs, dict):
        tool = inputs.get("tool")
        if isinstance(tool, str) and tool:
            return tool
    tool = spec.get("tool")
    if isinstance(tool, str) and tool:
        return tool
    meta = spec.get("meta") or spec.get("metadata") or {}
    if isinstance(meta, dict):
        desc = meta.get("description")
        if isinstance(desc, str) and desc:
            return desc
    return None


def _node_parameters(spec: dict[str, Any]) -> dict[str, Any]:
    inputs = spec.get("inputs")
    if isinstance(inputs, dict):
        params = inputs.get("params")
        if isinstance(params, dict):
            return params
        # Flat inputs already look like params for the UI.
        return dict(inputs)
    params = spec.get("params")
    if isinstance(params, dict):
        return params
    return {}


def _iter_node_pairs(document: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    nodes = document.get("nodes")
    pairs: list[tuple[str, dict[str, Any]]] = []
    if isinstance(nodes, dict):
        for node_id, spec in nodes.items():
            if isinstance(spec, dict):
                pairs.append((str(node_id), spec))
    elif isinstance(nodes, list):
        for spec in nodes:
            if isinstance(spec, dict):
                nid = spec.get("id")
                if isinstance(nid, str) and nid:
                    pairs.append((nid, spec))
    return pairs


def _start_node(document: dict[str, Any], pairs: list[tuple[str, dict[str, Any]]]) -> str | None:
    control = document.get("control")
    if isinstance(control, dict):
        start = control.get("start")
        if isinstance(start, str) and start:
            return start
    for nid, spec in pairs:
        if spec.get("class_type") == "StartNode" or spec.get("type") == "start":
            return nid
    return pairs[0][0] if pairs else None


def build_ui_block(
    document: dict[str, Any],
    *,
    options: LayoutOptions | None = None,
    edges: list[LayoutEdge] | None = None,
) -> dict[str, Any]:
    """Compute positions + UI-shaped nodes/edges for the document.

    Returns a dict shaped like ``{"nodes": [...], "edges": [...]}`` that
    is ready to drop under the ``ui`` key of ``Flow.data``.
    """
    pairs = _iter_node_pairs(document)
    node_ids = [nid for nid, _ in pairs]
    layout_edges = edges if edges is not None else extract_edges(document)
    start = _start_node(document, pairs)
    coords = compute_layout(
        node_ids,
        [(e.source, e.target) for e in layout_edges],
        start=start,
        options=options,
    )

    ui_nodes: list[dict[str, Any]] = []
    for node_id, spec in pairs:
        node_type = _node_type(spec)
        category = _TYPE_TO_CATEGORY.get(node_type, "transform")
        x, y = coords.get(node_id, (0.0, 0.0))
        ui_nodes.append(
            {
                "id": node_id,
                "type": "generic",
                "position": {"x": round(x, 2), "y": round(y, 2)},
                "data": {
                    "label": _node_label(node_id, spec),
                    "icon": node_type,
                    "category": category,
                    "description": _node_description(spec),
                    "parameters": _node_parameters(spec),
                    "inputs": ["input"],
                    "outputs": ["output"],
                },
            }
        )

    return {
        "nodes": ui_nodes,
        "edges": [e.to_dict() for e in layout_edges],
    }


def layout_document(
    document: dict[str, Any],
    *,
    options: LayoutOptions | None = None,
) -> dict[str, Any]:
    """Return a copy of ``document`` with a ``ui`` block attached.

    The canonical fields are preserved verbatim so the execution engine
    can continue to ``load()`` the document without any migration.
    """
    out = dict(document)
    out["ui"] = build_ui_block(document, options=options)
    return out
