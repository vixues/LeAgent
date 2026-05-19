"""Extract control-flow edges from a canonical workflow document.

The canonical shape stores every navigation decision inside each node's
``control`` block (or ``meta`` for UI-only affordances like human-review
action buttons). The naive ReactFlow converter only picked up ``next``
and ``error_handler``, so conditional branches, parallel fan-out, and
human-review action targets were silently dropped — that is the primary
cause of the "densely packed overlapping" rendering this module exists
to fix.

This file walks every control-flow exit and emits a typed
:class:`LayoutEdge` for each one. The output feeds
:func:`leagent.workflow.layout.engine.compute_layout` and is also
serialised into the ``ui.edges`` block so the frontend does not need to
re-derive edges client-side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


EdgeKind = str  # one of: next, error, condition, else, branch, sequence, action, reject


@dataclass(frozen=True)
class LayoutEdge:
    """A single directed edge in the workflow's control-flow graph."""

    source: str
    target: str
    kind: EdgeKind = "next"
    label: str = ""
    # Stable identity so two calls on the same document return equal results.
    id: str = field(default="")

    def with_id(self) -> "LayoutEdge":
        if self.id:
            return self
        token = self.label or self.kind
        new_id = f"e-{self.source}-{self.target}-{token}".replace(" ", "_")
        return LayoutEdge(
            source=self.source,
            target=self.target,
            kind=self.kind,
            label=self.label,
            id=new_id,
        )

    def to_dict(self) -> dict[str, Any]:
        self_ = self.with_id()
        out: dict[str, Any] = {
            "id": self_.id,
            "source": self_.source,
            "target": self_.target,
            "type": "default",
            "data": {"kind": self_.kind},
        }
        if self_.label:
            out["label"] = self_.label
        return out


def _condition_label(cond: Any) -> str:
    """Render a condition expression in a compact, human-readable form."""
    if not isinstance(cond, dict):
        return str(cond)
    expr = cond.get("if") or cond.get("if_expr")
    if isinstance(expr, str):
        # Trim mustache braces so the edge label stays tight.
        text = expr.strip()
        if text.startswith("${") and text.endswith("}"):
            text = text[2:-1]
        return text[:40]
    if isinstance(expr, dict):
        left = expr.get("left", "")
        op = expr.get("operator", "eq")
        right = expr.get("right", "")
        return f"{left} {op} {right}"[:40]
    return ""


def _iter_nodes(document: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield ``(node_id, node_spec)`` for both canonical and authoring shapes.

    Canonical stores ``nodes`` as ``dict[id, spec]``; the authoring YAML
    shape uses a ``list[{"id", ...}]``. We support both so this module
    can be reused during migration of legacy rows.
    """
    nodes = document.get("nodes")
    if isinstance(nodes, dict):
        for node_id, spec in nodes.items():
            if isinstance(spec, dict):
                yield str(node_id), spec
    elif isinstance(nodes, list):
        for spec in nodes:
            if isinstance(spec, dict):
                node_id = spec.get("id")
                if node_id:
                    yield str(node_id), spec


def _control_of(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the control block regardless of shape.

    Canonical nodes wrap control inside ``spec["control"]``. Authoring
    nodes keep ``next`` / ``conditions`` / ``branches`` at the top level.
    """
    if isinstance(spec.get("control"), dict):
        return spec["control"]
    return spec


def _meta_of(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the meta/metadata block regardless of shape."""
    meta = spec.get("meta")
    if isinstance(meta, dict):
        return meta
    metadata = spec.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    return {}


def extract_edges(document: dict[str, Any]) -> list[LayoutEdge]:
    """Return every control-flow edge declared by the document.

    Edges are emitted in source-then-kind order so the list is stable
    across runs and safe to snapshot in tests.
    """
    edges: list[LayoutEdge] = []
    known_ids: set[str] = {node_id for node_id, _ in _iter_nodes(document)}

    def add(source: str, target: str, kind: str, label: str = "") -> None:
        if not source or not target:
            return
        if target not in known_ids:
            return
        edges.append(LayoutEdge(source=source, target=target, kind=kind, label=label).with_id())

    for node_id, spec in _iter_nodes(document):
        control = _control_of(spec)
        meta = _meta_of(spec)

        # 1. Linear successor.
        nxt = control.get("next")
        if isinstance(nxt, str):
            add(node_id, nxt, "next")

        # 2. Error handler.
        err = control.get("error_handler")
        if isinstance(err, str):
            add(node_id, err, "error", "on_error")

        # 3. Condition branches + else.
        conditions = control.get("conditions") or []
        if isinstance(conditions, list):
            for cond in conditions:
                if not isinstance(cond, dict):
                    continue
                target = cond.get("then")
                if isinstance(target, str):
                    add(node_id, target, "condition", _condition_label(cond))

        for else_key in ("else_node", "else"):
            else_target = control.get(else_key)
            if isinstance(else_target, str):
                add(node_id, else_target, "else", "else")
                break

        # 4. Parallel branches — fan-out from parallel node then sequence
        # within each branch body.
        branches = control.get("branches") or []
        if isinstance(branches, list):
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                branch_id = str(branch.get("id", ""))
                branch_nodes = branch.get("nodes") or []
                if not isinstance(branch_nodes, list):
                    continue
                branch_ids: list[str] = []
                for ref in branch_nodes:
                    if isinstance(ref, str):
                        branch_ids.append(ref)
                    elif isinstance(ref, dict) and isinstance(ref.get("id"), str):
                        branch_ids.append(ref["id"])
                if not branch_ids:
                    continue
                add(node_id, branch_ids[0], "branch", branch_id)
                for a, b in zip(branch_ids, branch_ids[1:]):
                    add(a, b, "sequence")

        # 5. Human-review action buttons (stored under meta.actions after
        # template canonicalisation).
        actions = meta.get("actions") or control.get("actions") or []
        if isinstance(actions, list):
            for action in actions:
                if not isinstance(action, dict):
                    continue
                target = action.get("next")
                if isinstance(target, str):
                    label = str(action.get("label") or action.get("id") or "")
                    add(node_id, target, "action", label)

        # 6. Human-review on_reject shortcut.
        on_reject = control.get("on_reject")
        if isinstance(on_reject, str):
            add(node_id, on_reject, "reject", "rejected")

    # Deduplicate identical edges while preserving first-seen order.
    seen: set[tuple[str, str, str]] = set()
    unique: list[LayoutEdge] = []
    for edge in edges:
        key = (edge.source, edge.target, edge.kind)
        if key in seen:
            continue
        seen.add(key)
        unique.append(edge)
    return unique
