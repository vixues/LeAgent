"""Tests for chat-embedded workflow (Flow.data-shaped) validation."""

from __future__ import annotations

import pytest

from leagent.chat_workflow.workflow_embed import (
    WorkflowEmbedValidationError,
    build_extensions_payload,
    validate_workflow_embed,
)


@pytest.mark.asyncio
async def test_validate_workflow_embed_accepts_canonical(
    registered_builtins,
    sample_canonical_document,
) -> None:
    from leagent.workflow.nodes import get_registry

    doc, digest = validate_workflow_embed(sample_canonical_document, node_registry=get_registry())
    assert doc.start_id == "start"
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_validate_workflow_embed_accepts_camel_node_types(
    registered_builtins,  # noqa: ARG001
) -> None:
    """LLM-authored list graphs may use startNode/toolCallNode instead of StartNode."""
    from leagent.workflow.nodes import get_registry

    flow = {
        "id": "camel-nodes",
        "name": "Camel node types",
        "nodes": [
            {"id": "start", "type": "startNode", "data": {"label": "Start"}, "next": "end"},
            {"id": "end", "type": "endNode", "data": {"label": "End"}},
        ],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
        "start_node": "start",
        "end_node": "end",
    }
    doc, digest = validate_workflow_embed(flow, node_registry=get_registry())
    assert doc.start_id == "start"
    assert len(digest) == 64
    assert doc.nodes["start"]["class_type"] == "StartNode"
    assert doc.nodes["end"]["class_type"] == "EndNode"


@pytest.mark.asyncio
async def test_validate_workflow_embed_accepts_tool_class_alias(
    registered_builtins,  # noqa: ARG001
) -> None:
    """LLM graphs may use class_type ``tool`` and omit explicit end nodes."""
    from leagent.workflow.nodes import get_registry

    flow = {
        "id": "genui-guide",
        "name": "GenUI guide",
        "control": {"start": "start", "end": "end", "edges": []},
        "nodes": {
            "router": {
                "class_type": "tool",
                "inputs": {"tool": "get_genui_guide", "params": {}},
                "meta": {"name": "Guide"},
                "control": {"next": "build"},
            },
            "build": {
                "class_type": "tool",
                "inputs": {"tool": "emit_ui_tree", "params": {"tree": {"root": {"kind": "Text"}}}},
                "meta": {"name": "Build"},
                "control": {"next": "end"},
            },
        },
    }
    doc, digest = validate_workflow_embed(flow, node_registry=get_registry())
    assert doc.nodes["router"]["class_type"] == "ToolCallNode"
    assert doc.nodes["end"]["class_type"] == "EndNode"
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_validate_workflow_embed_accepts_comfy_style_class_aliases(
    registered_builtins,  # noqa: ARG001
) -> None:
    """LLM graphs may use Comfy-style class_type input/default/output."""
    from leagent.workflow.nodes import get_registry

    flow = {
        "id": "genui-comfy-aliases",
        "name": "GenUI Comfy aliases",
        "control": {"start": "start", "end": "end", "edges": []},
        "nodes": {
            "start": {
                "class_type": "input",
                "inputs": {},
                "meta": {"name": "Start"},
                "control": {"next": "router"},
            },
            "router": {
                "class_type": "default",
                "inputs": {"tool": "get_genui_guide", "params": {}},
                "meta": {"name": "Guide"},
                "control": {"next": "build"},
            },
            "build": {
                "class_type": "default",
                "inputs": {
                    "tool": "emit_ui_tree",
                    "params": {"tree": {"root": {"kind": "Text", "props": {"value": "hi"}}}},
                },
                "meta": {"name": "Build"},
                "control": {"next": "render"},
            },
            "render": {
                "class_type": "output",
                "inputs": {},
                "meta": {"name": "Render"},
                "control": {"next": "end"},
            },
        },
    }
    doc, digest = validate_workflow_embed(flow, node_registry=get_registry())
    assert doc.nodes["start"]["class_type"] == "StartNode"
    assert doc.nodes["router"]["class_type"] == "ToolCallNode"
    assert doc.nodes["render"]["class_type"] == "EndNode"
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_validate_rejects_list_nodes(registered_builtins) -> None:  # noqa: ARG001
    from leagent.workflow.nodes import get_registry

    bad = {
        "id": "x",
        "nodes": {
            "a": {
                "class_type": "NotARegisteredNode",
                "inputs": {},
                "meta": {},
                "control": {},
            },
        },
        "control": {"start": "a", "end": "end", "edges": []},
    }
    with pytest.raises(WorkflowEmbedValidationError):
        validate_workflow_embed(bad, node_registry=get_registry())


def test_build_extensions_payload_roundtrip_keys() -> None:
    fd = {"id": "1", "name": "n", "nodes": {}, "control": {"start": "s", "end": "e", "edges": []}}
    ext = build_extensions_payload(flow_data=fd, digest="a" * 64)
    assert ext["workflow_embed"]["data"] == fd
    assert ext["workflow_embed"]["digest"] == ext["workflow_embed_digest"]
