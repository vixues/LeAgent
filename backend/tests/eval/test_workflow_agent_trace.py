"""Agent-side harness: a scripted LLM drives the real ``QueryEngine`` tool
loop and we assert — via :class:`EngineTrace` — that the agent turns an idea
into a *workflow on the canvas* (``chat_workflow_embed_emit``) whose graph
validates against the engine with a stable digest.

Fully offline: no API key, no DB. The model turns are canned
``ModelStreamEvent`` scripts, and the emitted graph is the flagship art
pipeline's canonical document (the kind of DAG the agent is expected to
produce for a game-art request).
"""

from __future__ import annotations

import uuid

import pytest

from leagent.chat_workflow.workflow_embed import validate_workflow_embed
from leagent.workflow.io import load
from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.nodes import get_registry as get_node_registry
from leagent.workflow.template_service import TemplateService
from tests.integration.conftest import (
    build_full_tool_registry,
    drive_query_engine,
    make_scripted_deps,
    scripted_text_turn,
    scripted_turn,
)

pytestmark = pytest.mark.asyncio

_WORKFLOW_AGENT_TOOLS = [
    "chat_workflow_embed_emit",
    "workflow_save",
    "workflow_run",
    "workflow_status",
    "todo_write",
    "task_done",
]


def _flagship_canonical() -> dict:
    svc = TemplateService()
    svc.load()
    raw = svc.get_template("TPL-ART-01")
    assert raw is not None
    return load(raw).to_dict()


async def test_agent_emits_valid_art_workflow_to_canvas(tmp_path) -> None:
    await bootstrap_nodes()
    registry = build_full_tool_registry()
    assert registry.has("chat_workflow_embed_emit")
    assert registry.has("workflow_save"), "workflow_save must be registered for the loop"

    flow_data = _flagship_canonical()
    script = [
        scripted_turn(
            {
                "id": "emit_1",
                "name": "chat_workflow_embed_emit",
                "arguments": {
                    "title": "Game Art Asset Pipeline",
                    "summary": "concept -> image -> quality gate -> self-correct -> 3D/video -> export",
                    "flow_data": flow_data,
                },
            },
        ),
        scripted_text_turn("Published the game-art pipeline to the canvas."),
    ]

    engine = build_engine(registry, script, tmp_path)
    trace = await drive_query_engine(
        engine,
        "Design a workflow that turns 'a heroic fantasy knight' into engine-ready game assets.",
    )

    # The agent published a workflow to the canvas via the embed tool.
    assert trace.used_tool("chat_workflow_embed_emit")

    # The embed tool ran its engine validation on entry; a successful trace
    # means the emitted graph is a valid canonical document. The tool's input
    # (the graph the agent put on the canvas) is reliably recorded in the trace.
    emit_inputs = [
        inp
        for name, inp in zip(trace.tool_uses, trace.tool_inputs, strict=False)
        if name == "chat_workflow_embed_emit"
    ]
    assert emit_inputs, "expected the embed tool input in the trace"
    emitted_flow = emit_inputs[0].get("flow_data")
    assert isinstance(emitted_flow, dict)

    # The canvas graph carries the first-class art + control nodes.
    nodes = emitted_flow["nodes"]
    class_types = {spec.get("class_type") for spec in nodes.values()}
    assert {"Art.ImageGen", "QualityGateNode", "IterativeRefineNode"}.issubset(class_types)

    # Independently confirm the agent-emitted graph validates with a stable
    # 64-char digest — the same guarantee workflow_save / the canvas rely on.
    _doc, digest = validate_workflow_embed(emitted_flow, node_registry=get_node_registry())
    assert isinstance(digest, str) and len(digest) == 64


def build_engine(registry, script, tmp_path):  # noqa: ANN001
    from leagent.agent.script_agent import build_script_agent_engine

    return build_script_agent_engine(
        llm=None,
        tools=registry,
        cwd=str(tmp_path),
        allowed_tools=_WORKFLOW_AGENT_TOOLS,
        max_turns=6,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        deps=make_scripted_deps(script),
    )
