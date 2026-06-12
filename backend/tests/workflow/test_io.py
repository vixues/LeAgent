"""Round-trip, canonicalization and validation tests for the IO module."""

from __future__ import annotations

import pytest

from leagent.workflow.io import (
    WorkflowDocument,
    WorkflowLoaderError,
    export,
    graph_hash,
    load,
    to_json,
    validate,
)
from leagent.workflow.io.authoring import to_canonical


def test_load_accepts_canonical(sample_canonical_document):
    doc = load(sample_canonical_document)
    assert isinstance(doc, WorkflowDocument)
    assert set(doc.nodes.keys()) == {"start", "xform", "end"}


def test_roundtrip_preserves_structure(sample_canonical_document):
    doc = load(sample_canonical_document)
    exported = export(doc)
    doc2 = load(exported)
    assert doc.nodes == doc2.nodes
    assert doc.control == doc2.control


def test_to_json_is_deterministic(sample_canonical_document):
    doc = load(sample_canonical_document)
    assert to_json(doc, indent=None) == to_json(load(sample_canonical_document), indent=None)


def test_graph_hash_is_stable(sample_canonical_document):
    doc = load(sample_canonical_document)
    h1 = graph_hash(doc)
    h2 = graph_hash(load(sample_canonical_document))
    assert h1 == h2
    assert len(h1) >= 16


def test_graph_hash_changes_with_content(sample_canonical_document):
    doc1 = load(sample_canonical_document)
    modified = dict(sample_canonical_document)
    modified_nodes = dict(sample_canonical_document["nodes"])
    modified_nodes["xform"] = {
        **sample_canonical_document["nodes"]["xform"],
        "inputs": {"transform": {"name": "different"}},
    }
    modified["nodes"] = modified_nodes
    doc2 = load(modified)
    assert graph_hash(doc1) != graph_hash(doc2)


def test_load_rejects_non_canonical_list_nodes():
    raw = {
        "id": "x",
        "nodes": [{"id": "a", "class_type": "StartNode"}],
        "control": {},
    }
    with pytest.raises(WorkflowLoaderError):
        load(raw)


def test_load_rejects_missing_class_type():
    raw = {
        "id": "x",
        "nodes": {"a": {"inputs": {}, "control": {}}},
        "control": {},
    }
    with pytest.raises(WorkflowLoaderError):
        load(raw)


def test_to_canonical_accepts_authoring_list():
    raw = {
        "id": "auth",
        "name": "authored",
        "nodes": [
            {"id": "start", "type": "start", "next": "end"},
            {"id": "end", "type": "end"},
        ],
        "start_node": "start",
        "end_node": "end",
        "edges": [{"from": "start", "to": "end"}],
    }
    canonical = to_canonical(raw)
    assert isinstance(canonical["nodes"], dict)
    assert canonical["nodes"]["start"]["class_type"] == "StartNode"
    assert canonical["nodes"]["start"]["control"]["next"] == "end"
    assert canonical["control"]["start"] == "start"


def test_to_canonical_is_idempotent(sample_canonical_document):
    first = to_canonical(sample_canonical_document)
    second = to_canonical(first)
    assert first == second


def test_to_canonical_flattens_react_flow_node_with_outer_type_and_tool_inputs():
    """Editor graphs often put class on the node shell and fields inside ``data``."""
    raw = {
        "id": "rf",
        "name": "RF",
        "nodes": [
            {
                "id": "n1",
                "type": "ToolCallNode",
                "data": {
                    "label": "Read",
                    "tool": "csv_processor",
                    "tool_inputs": {"operation": "read"},
                },
            }
        ],
        "start_node": "n1",
        "end_node": "n1",
    }
    canonical = to_canonical(raw)
    spec = canonical["nodes"]["n1"]
    assert spec["class_type"] == "ToolCallNode"
    assert spec["inputs"]["tool"] == "csv_processor"
    assert spec["inputs"]["params"] == {"operation": "read"}


def test_to_canonical_maps_short_tool_type_alias():
    raw = {
        "id": "x",
        "name": "x",
        "nodes": [
            {
                "id": "t1",
                "type": "tool",
                "data": {"tool": "echo", "params": {"text": "hi"}},
            }
        ],
        "start_node": "t1",
        "end_node": "end",
    }
    canonical = to_canonical(raw)
    assert canonical["nodes"]["t1"]["class_type"] == "ToolCallNode"
    assert canonical["nodes"]["end"]["class_type"] == "EndNode"


def test_to_canonical_maps_camel_case_tool_call_type():
    raw = {
        "id": "x",
        "name": "x",
        "nodes": [
            {
                "id": "t1",
                "type": "toolCall",
                "data": {"tool": "echo", "params": {"text": "hi"}},
            }
        ],
        "start_node": "t1",
        "end_node": "t1",
    }
    canonical = to_canonical(raw)
    assert canonical["nodes"]["t1"]["class_type"] == "ToolCallNode"


def test_to_canonical_infers_type_from_generic_editor_node():
    raw = {
        "id": "editor-flow",
        "name": "editor flow",
        "nodes": [
            {
                "id": "start",
                "type": "generic",
                "data": {"icon": "start", "label": "Start"},
                "next": "end",
            },
            {
                "id": "end",
                "type": "generic",
                "data": {"icon": "end", "label": "End"},
            },
        ],
        "start_node": "start",
        "end_node": "end",
    }

    canonical = to_canonical(raw)
    assert canonical["nodes"]["start"]["class_type"] == "StartNode"
    assert canonical["nodes"]["end"]["class_type"] == "EndNode"


def test_to_canonical_generic_fallback_never_writes_generic_class():
    raw = {
        "id": "editor-flow",
        "name": "editor flow",
        "nodes": [
            {
                "id": "n1",
                "type": "generic",
                "data": {"label": "Unknown"},
            }
        ],
    }

    canonical = to_canonical(raw)
    assert canonical["nodes"]["n1"]["class_type"] != "generic"


async def test_validate_returns_errors_on_missing_targets():
    from leagent.workflow.nodes import bootstrap

    await bootstrap()
    bad = {
        "id": "x",
        "name": "bad",
        "inputs": [],
        "outputs": [],
        "metadata": {},
        "nodes": {
            "start": {
                "class_type": "StartNode",
                "inputs": {},
                "meta": {},
                "control": {"next": "ghost"},
            },
            "end": {
                "class_type": "EndNode",
                "inputs": {},
                "meta": {},
                "control": {},
            },
        },
        "control": {"start": "start", "end": "end", "edges": [], "timeout_sec": 3600, "max_retries": 3, "tags": []},
    }
    doc = load(bad)
    ok, _, errors = validate(doc)
    assert not ok
    assert any("ghost" in str(errs) for errs in errors.values())
