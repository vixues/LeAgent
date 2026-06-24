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
async def test_validate_workflow_embed_aliases_tool_id_to_tool(
    registered_builtins,  # noqa: ARG001
) -> None:
    """LLM graphs that use ``tool_id`` should fold into the ``tool`` input."""
    from leagent.workflow.nodes import get_registry

    flow = {
        "id": "tool-id-alias",
        "name": "Tool id alias",
        "control": {"start": "start", "end": "end", "edges": []},
        "nodes": {
            "start": {"class_type": "StartNode", "control": {"next": "step"}},
            "step": {
                "class_type": "ToolCallNode",
                "inputs": {"tool_id": "get_genui_guide", "params": {}},
                "control": {"next": "end"},
            },
            "end": {"class_type": "EndNode"},
        },
    }
    doc, digest = validate_workflow_embed(flow, node_registry=get_registry())
    assert doc.nodes["step"]["inputs"]["tool"] == "get_genui_guide"
    assert "tool_id" not in doc.nodes["step"]["inputs"]
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_validate_workflow_embed_aliases_tool_name_in_list_shape(
    registered_builtins,  # noqa: ARG001
) -> None:
    """Flat list authoring with top-level ``tool_name`` folds into ``tool``."""
    from leagent.workflow.nodes import get_registry

    flow = {
        "id": "tool-name-alias",
        "name": "Tool name alias",
        "nodes": [
            {"id": "start", "type": "input", "next": "step"},
            {"id": "step", "type": "tool", "tool_name": "get_genui_guide", "next": "end"},
            {"id": "end", "type": "output"},
        ],
        "start_node": "start",
        "end_node": "end",
    }
    doc, _digest = validate_workflow_embed(flow, node_registry=get_registry())
    assert doc.nodes["step"]["inputs"]["tool"] == "get_genui_guide"


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


def test_sanitize_embed_inputs_whitelists_declared_and_user_input() -> None:
    from leagent.chat_workflow.runner import _sanitize_embed_inputs

    flow_data = {"inputs": [{"name": "prompt"}, {"name": "steps"}]}
    out = _sanitize_embed_inputs(
        {"prompt": "p", "steps": 5, "evil": "drop me", "user_input": "u"},
        None,
        flow_data,
    )
    assert out == {"prompt": "p", "steps": 5, "user_input": "u"}


def test_sanitize_embed_inputs_handles_empty_and_missing() -> None:
    from leagent.chat_workflow.runner import _sanitize_embed_inputs

    assert _sanitize_embed_inputs(None, None, {}) == {}
    assert _sanitize_embed_inputs({}, None, {}) == {}
    # No declared inputs: only the always-allowed user_input survives.
    assert _sanitize_embed_inputs({"x": 1, "user_input": "u"}, None, {}) == {"user_input": "u"}


@pytest.mark.asyncio
async def test_start_embed_merges_structured_inputs_into_engine_state(
    registered_builtins,  # noqa: ARG001
    sample_canonical_document,
) -> None:
    """Structured run inputs are whitelisted and merged into engine inputs."""
    from uuid import uuid4

    from leagent.chat_workflow.runner import start_chat_workflow_embed_via_engine

    captured: dict[str, object] = {}

    class _FakeWorkflowService:
        async def start_compiled_document(self, _document, **kwargs):
            captured.update(kwargs)
            return {"prompt_id": "p1", "run_id": "r1"}

    class _FakeServiceManager:
        workflow_service = _FakeWorkflowService()

    outcome = await start_chat_workflow_embed_via_engine(
        flow_data=sample_canonical_document,
        service_manager=_FakeServiceManager(),
        user_id=str(uuid4()),
        session_id="sess-1",
        user_input="",
        inputs={"user_input": "override", "bogus": "drop"},
    )

    assert outcome.started is True
    assert outcome.prompt_id == "p1"
    engine_inputs = captured["inputs"]
    assert isinstance(engine_inputs, dict)
    # The structured user_input overrides the empty placeholder; unknown keys drop.
    assert engine_inputs["user_input"] == "override"
    assert "bogus" not in engine_inputs
    assert engine_inputs["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_validate_workflow_embed_accepts_editor_script_nodes_with_default_type(
    registered_builtins,  # noqa: ARG001
) -> None:
    """React Flow graphs with ``type: default`` + ``config.node_type: script``."""
    from leagent.workflow.nodes import get_registry

    flow = {
        "id": "TPL-11",
        "name": "文档多级审批流程",
        "nodes": [
            {
                "id": "start",
                "type": "default",
                "class_type": "StartNode",
                "data": {
                    "label": "提交",
                    "config": {"node_type": "start", "inputs": {}, "outputs": {}},
                },
            },
            {
                "id": "tech_review",
                "type": "default",
                "class_type": "ToolCallNode",
                "data": {
                    "label": "技术评审",
                    "config": {
                        "node_type": "script",
                        "inputs": {"tech_score": "{{input.tech_score}}"},
                        "output": "tech_out",
                        "timeout_sec": 10,
                        "source": "result = {'passed': tech_score >= 60}",
                    },
                },
            },
            {
                "id": "end",
                "type": "default",
                "class_type": "EndNode",
                "data": {
                    "label": "完成",
                    "config": {"node_type": "end", "outputs": {}},
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "start", "target": "tech_review"},
            {"id": "e2", "source": "tech_review", "target": "end"},
        ],
    }
    doc, digest = validate_workflow_embed(flow, node_registry=get_registry())
    assert doc.nodes["start"]["class_type"] == "StartNode"
    assert doc.nodes["tech_review"]["class_type"] == "ScriptNode"
    assert doc.nodes["tech_review"]["inputs"]["source"]
    assert doc.nodes["end"]["class_type"] == "EndNode"
    assert len(digest) == 64

