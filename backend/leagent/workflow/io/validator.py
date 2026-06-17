"""Workflow document validator.

Port of ComfyUI's ``execution.validate_prompt`` / ``validate_inputs``
adapted for the leagent control-flow domain. Returns a triple
``(ok, output_node_ids, errors_by_node)`` where each error dict follows
``{type, message, details, extra_info}``.

Checks performed:
- document-level: required keys, at least one output node.
- per-node: class_type registered, required inputs present, type compat
  on link-style inputs ``("<upstream_id>", <slot_index>)``, combo choices,
  numeric bounds.
- graph-level: every referenced target exists, no control-flow cycles
  (except ``_LOOP_SAFE_TYPES``), start/end reachable.
"""

from __future__ import annotations

from typing import Any

from .loader import WorkflowDocument


# Node classes that allow back-edges (e.g. retry/loop semantics).
_LOOP_SAFE_TYPES = {"ErrorHandlerNode", "WaitNode", "IterativeRefineNode"}


def _error(type_: str, message: str, details: str = "", **extra: Any) -> dict[str, Any]:
    return {"type": type_, "message": message, "details": details, "extra_info": extra}


def validate(
    doc: WorkflowDocument,
    *,
    registry: Any = None,
) -> tuple[bool, list[str], dict[str, list[dict[str, Any]]]]:
    """Validate a workflow document.

    ``registry`` is an optional ``NodeRegistry`` used for class-level checks.
    If ``None``, only document-level invariants are enforced.
    """

    errors: dict[str, list[dict[str, Any]]] = {}
    output_nodes: list[str] = []

    if not doc.nodes:
        errors["__root__"] = [_error("empty", "Workflow has no nodes")]
        return False, [], errors

    node_ids = set(doc.nodes.keys())

    for node_id, node_def in doc.nodes.items():
        node_errors: list[dict[str, Any]] = []
        class_type = node_def.get("class_type")
        if not class_type:
            node_errors.append(_error("missing_class_type", "Node has no class_type"))
            errors[node_id] = node_errors
            continue

        node_cls = None
        if registry is not None:
            node_cls = registry.get(class_type)
            if node_cls is None:
                node_errors.append(_error(
                    "unknown_node", f"Unknown node class: {class_type}",
                    details=f"Node '{node_id}' references unregistered class '{class_type}'",
                ))
                errors[node_id] = node_errors
                continue

        if node_cls is not None:
            schema = node_cls.get_schema()
            if schema.is_output_node:
                output_nodes.append(node_id)
            node_errors.extend(_validate_node_inputs(node_id, node_def, schema, node_ids))

        control = node_def.get("control", {}) or {}
        node_errors.extend(_validate_node_control(node_id, control, node_ids))

        if node_errors:
            errors[node_id] = node_errors

    # Ensure control.start and control.end exist
    start_id = doc.start_id
    if start_id not in node_ids:
        errors.setdefault("__root__", []).append(
            _error("missing_start", f"start node '{start_id}' is not defined"))
    end_id = doc.end_id
    if end_id and end_id not in node_ids:
        errors.setdefault("__root__", []).append(
            _error("missing_end", f"end node '{end_id}' is not defined"))

    if not output_nodes and end_id in node_ids:
        output_nodes.append(end_id)

    cycle_errors = _detect_cycles(doc)
    for node_id, err_list in cycle_errors.items():
        errors.setdefault(node_id, []).extend(err_list)

    ok = not errors
    return ok, output_nodes, errors


def _validate_node_inputs(
    node_id: str,
    node_def: dict[str, Any],
    schema: Any,
    node_ids: set[str],
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    provided = node_def.get("inputs", {}) or {}

    for inp in schema.inputs:
        value = provided.get(inp.id, None)
        if value is None:
            if not inp.optional and inp.default is None:
                errors.append(_error(
                    "required_input_missing",
                    f"Required input '{inp.id}' missing on '{node_id}'",
                    details=f"input='{inp.id}' type={inp.get_io_type()}",
                ))
            continue

        # Link reference: [upstream_id, slot]
        if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
            up_id, slot = value
            if up_id not in node_ids:
                errors.append(_error(
                    "dangling_link",
                    f"Input '{inp.id}' on '{node_id}' links to missing node '{up_id}'",
                ))
            continue

        # Multi-link reference (ARRAY): [[upstream_id, slot], ...]
        if (
            isinstance(value, list)
            and value
            and all(
                isinstance(item, list)
                and len(item) == 2
                and isinstance(item[0], str)
                for item in value
            )
        ):
            if inp.get_io_type() != "ARRAY":
                errors.append(_error(
                    "type_mismatch",
                    f"Input '{inp.id}' on '{node_id}' does not accept multiple links",
                    details=f"type={inp.get_io_type()}",
                ))
                continue
            for up_id, _slot in value:
                if up_id not in node_ids:
                    errors.append(_error(
                        "dangling_link",
                        f"Input '{inp.id}' on '{node_id}' links to missing node '{up_id}'",
                    ))
            continue

        # Scalar value — run per-type checks.
        io_type = inp.get_io_type()
        if io_type == "COMBO":
            choices = getattr(inp, "choices", None) or []
            if choices and value not in choices:
                errors.append(_error(
                    "invalid_combo",
                    f"Input '{inp.id}' on '{node_id}' must be one of {choices}",
                    details=f"got {value!r}",
                ))
        elif io_type == "INT":
            if isinstance(value, bool) or not isinstance(value, int):
                if isinstance(value, str):
                    try:
                        value = int(value)
                    except ValueError:
                        errors.append(_error("type_mismatch", f"'{inp.id}' must be int"))
                        continue
                else:
                    errors.append(_error("type_mismatch", f"'{inp.id}' must be int"))
                    continue
            mn = getattr(inp, "min", None)
            mx = getattr(inp, "max", None)
            if mn is not None and value < mn:
                errors.append(_error("out_of_range", f"'{inp.id}' below min {mn}"))
            if mx is not None and value > mx:
                errors.append(_error("out_of_range", f"'{inp.id}' above max {mx}"))
        elif io_type == "FLOAT":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(_error("type_mismatch", f"'{inp.id}' must be number"))
        elif io_type == "BOOLEAN":
            if not isinstance(value, bool):
                errors.append(_error("type_mismatch", f"'{inp.id}' must be bool"))

    return errors


def _validate_node_control(
    node_id: str, control: dict[str, Any], node_ids: set[str]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for key in ("next", "error_handler", "else_node", "on_reject"):
        target = control.get(key)
        if target and target not in node_ids:
            errors.append(_error(
                "dangling_edge",
                f"Control edge '{key}' on '{node_id}' targets missing node '{target}'",
            ))
    for cond in control.get("conditions", []) or []:
        target = cond.get("then_node") or cond.get("then")
        if target and target not in node_ids:
            errors.append(_error(
                "dangling_edge",
                f"Condition on '{node_id}' targets missing node '{target}'",
            ))
    for branch in control.get("branches", []) or []:
        for ref in branch.get("nodes", []) or []:
            if ref not in node_ids:
                errors.append(_error(
                    "dangling_edge",
                    f"Parallel branch on '{node_id}' references missing node '{ref}'",
                ))
    return errors


def _detect_cycles(doc: WorkflowDocument) -> dict[str, list[dict[str, Any]]]:
    """DFS-based cycle detection skipping back-edges into loop-safe nodes."""

    errors: dict[str, list[dict[str, Any]]] = {}
    adj: dict[str, list[str]] = {nid: [] for nid in doc.nodes}

    for nid, node_def in doc.nodes.items():
        class_type = node_def.get("class_type", "")
        control = node_def.get("control", {}) or {}
        succ: list[str] = []
        for key in ("next", "else_node", "on_reject"):
            v = control.get(key)
            if v:
                succ.append(v)
        if class_type == "ErrorHandlerNode":
            # error_handler targets are treated as separate non-contributing edges
            pass
        elif control.get("error_handler"):
            succ.append(control["error_handler"])
        for cond in control.get("conditions", []) or []:
            t = cond.get("then_node") or cond.get("then")
            if t:
                succ.append(t)
        adj[nid] = succ

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in adj}

    def dfs(nid: str, path: list[str]) -> None:
        color[nid] = GRAY
        path.append(nid)
        for nxt in adj.get(nid, []):
            if nxt not in adj:
                continue
            if color[nxt] == GRAY:
                nxt_cls = doc.nodes.get(nxt, {}).get("class_type", "")
                src_cls = doc.nodes.get(nid, {}).get("class_type", "")
                if nxt_cls in _LOOP_SAFE_TYPES or src_cls in _LOOP_SAFE_TYPES:
                    continue
                cycle = path[path.index(nxt):] + [nxt]
                errors.setdefault(nid, []).append(_error(
                    "cycle",
                    f"Control-flow cycle: {' -> '.join(cycle)}",
                ))
            elif color[nxt] == WHITE:
                dfs(nxt, path)
        path.pop()
        color[nid] = BLACK

    for nid in list(adj.keys()):
        if color[nid] == WHITE:
            dfs(nid, [])

    return errors
