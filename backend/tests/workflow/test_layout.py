"""Tests for :mod:`leagent.workflow.layout`.

Cover the four canonical graph shapes that the templates exercise:

* Linear — every edge comes from ``control.next``.
* Condition with else — ``control.conditions[].then`` + ``else_node``.
* Parallel branches — fan-out + in-branch sequencing.
* Cycle via ``wait`` — ``wait.next`` points back to an earlier node.

For each shape we assert that (a) every declared exit produces a
:class:`LayoutEdge`, (b) every node receives coordinates, and (c) no
two nodes share the exact same ``(x, y)``.
"""

from __future__ import annotations

from collections import Counter

import pytest

from leagent.workflow.io.authoring import to_canonical
from leagent.workflow.layout import (
    LayoutOptions,
    build_ui_block,
    compute_layout,
    extract_edges,
    layout_document,
)


def _canonical(raw: dict) -> dict:
    return to_canonical(raw)


def _assert_unique_positions(ui: dict) -> None:
    positions = Counter((n["position"]["x"], n["position"]["y"]) for n in ui["nodes"])
    duplicates = [p for p, c in positions.items() if c > 1]
    assert not duplicates, f"overlapping positions: {duplicates}"


def test_linear_flow_has_single_row_per_node() -> None:
    doc = _canonical(
        {
            "id": "linear",
            "nodes": [
                {"id": "start", "type": "start", "next": "a"},
                {"id": "a", "type": "tool_call", "tool": "x", "next": "b"},
                {"id": "b", "type": "tool_call", "tool": "y", "next": "end"},
                {"id": "end", "type": "end"},
            ],
        }
    )

    edges = extract_edges(doc)
    assert {(e.source, e.target) for e in edges} == {
        ("start", "a"),
        ("a", "b"),
        ("b", "end"),
    }

    coords = compute_layout(
        list(doc["nodes"].keys()),
        [(e.source, e.target) for e in edges],
        start=doc["control"]["start"],
    )
    assert set(coords) == {"start", "a", "b", "end"}
    # LR layout → unique x per rank; four ranks → four distinct x values.
    assert len({x for x, _ in coords.values()}) == 4


def test_condition_with_else_produces_both_branches() -> None:
    doc = _canonical(
        {
            "id": "cond",
            "nodes": [
                {"id": "start", "type": "start", "next": "check"},
                {
                    "id": "check",
                    "type": "condition",
                    "conditions": [
                        {"if": "${x} > 0", "then": "yes"},
                    ],
                    "else_node": "no",
                },
                {"id": "yes", "type": "transform", "transform": {}, "next": "end"},
                {"id": "no", "type": "transform", "transform": {}, "next": "end"},
                {"id": "end", "type": "end"},
            ],
        }
    )

    edges = extract_edges(doc)
    kinds = {(e.source, e.target): e.kind for e in edges}
    assert kinds[("check", "yes")] == "condition"
    assert kinds[("check", "no")] == "else"
    # Both branches must share the same rank so they render side-by-side.
    ui = build_ui_block(doc)
    yes_pos = next(n for n in ui["nodes"] if n["id"] == "yes")["position"]
    no_pos = next(n for n in ui["nodes"] if n["id"] == "no")["position"]
    assert yes_pos["x"] == no_pos["x"]
    assert yes_pos["y"] != no_pos["y"]
    _assert_unique_positions(ui)


def test_parallel_branches_emit_fanout_and_sequence_edges() -> None:
    doc = _canonical(
        {
            "id": "par",
            "nodes": [
                {"id": "start", "type": "start", "next": "split"},
                {
                    "id": "split",
                    "type": "parallel",
                    "branches": [
                        {"id": "left", "nodes": ["l1", "l2"]},
                        {"id": "right", "nodes": ["r1"]},
                    ],
                    "next": "merge",
                },
                {"id": "l1", "type": "tool_call", "tool": "a"},
                {"id": "l2", "type": "tool_call", "tool": "b"},
                {"id": "r1", "type": "tool_call", "tool": "c"},
                {"id": "merge", "type": "transform", "transform": {}, "next": "end"},
                {"id": "end", "type": "end"},
            ],
        }
    )

    edges = extract_edges(doc)
    pairs = {(e.source, e.target, e.kind) for e in edges}
    assert ("split", "l1", "branch") in pairs
    assert ("split", "r1", "branch") in pairs
    assert ("l1", "l2", "sequence") in pairs
    assert ("split", "merge", "next") in pairs

    ui = build_ui_block(doc)
    _assert_unique_positions(ui)


def test_wait_cycle_does_not_flatten_the_layout() -> None:
    doc = _canonical(
        {
            "id": "wait",
            "nodes": [
                {"id": "start", "type": "start", "next": "collect"},
                {
                    "id": "collect",
                    "type": "tool_call",
                    "tool": "fetch",
                    "next": "check",
                },
                {
                    "id": "check",
                    "type": "condition",
                    "conditions": [{"if": "${ok}", "then": "end"}],
                    "else_node": "wait_more",
                },
                {
                    "id": "wait_more",
                    "type": "wait",
                    "next": "collect",  # back-edge into an earlier rank
                },
                {"id": "end", "type": "end"},
            ],
        }
    )

    edges = extract_edges(doc)
    pairs = {(e.source, e.target) for e in edges}
    assert ("wait_more", "collect") in pairs

    ui = build_ui_block(doc)
    _assert_unique_positions(ui)
    # Ensure the back-edge did not collapse the rank of collect onto wait_more.
    xs = {n["id"]: n["position"]["x"] for n in ui["nodes"]}
    assert xs["collect"] < xs["check"] < xs["wait_more"]


def test_human_review_actions_become_edges() -> None:
    doc = _canonical(
        {
            "id": "hr",
            "nodes": [
                {"id": "start", "type": "start", "next": "review"},
                {
                    "id": "review",
                    "type": "human_review",
                    "reviewer": "manager",
                    "metadata": {
                        "actions": [
                            {"id": "approve", "label": "Approve", "next": "approved"},
                            {"id": "reject", "label": "Reject", "next": "rejected"},
                        ]
                    },
                    "on_reject": "rejected",
                },
                {"id": "approved", "type": "transform", "transform": {}, "next": "end"},
                {"id": "rejected", "type": "transform", "transform": {}, "next": "end"},
                {"id": "end", "type": "end"},
            ],
        }
    )

    edges = extract_edges(doc)
    kinds = {(e.source, e.target): e.kind for e in edges}
    assert kinds.get(("review", "approved")) == "action"
    assert ("review", "rejected") in {(e.source, e.target) for e in edges}


def test_layout_document_attaches_ui_block_without_mutating_canonical() -> None:
    doc = _canonical(
        {
            "id": "simple",
            "nodes": [
                {"id": "start", "type": "start", "next": "end"},
                {"id": "end", "type": "end"},
            ],
        }
    )
    before = {k: doc[k] for k in ("id", "nodes", "control")}
    out = layout_document(doc, options=LayoutOptions(direction="LR"))
    assert out["id"] == before["id"]
    assert out["nodes"] == before["nodes"]
    assert out["control"] == before["control"]
    assert set(out["ui"].keys()) == {"nodes", "edges"}
    assert len(out["ui"]["nodes"]) == 2
    _assert_unique_positions(out["ui"])


@pytest.mark.asyncio
async def test_every_template_lays_out_without_overlap() -> None:
    from leagent.workflow.nodes import bootstrap
    from leagent.workflow.template_service import get_template_service

    await bootstrap()
    service = get_template_service()
    service.load()

    for info in service.list_templates():
        tid = info["id"]
        doc = service.get_template(tid)
        assert doc is not None, tid
        ui = build_ui_block(doc)
        assert ui["nodes"], tid
        seen: set[tuple[float, float]] = set()
        for node in ui["nodes"]:
            pos = (node["position"]["x"], node["position"]["y"])
            assert pos not in seen, f"overlap in template {tid} at {pos}"
            seen.add(pos)
