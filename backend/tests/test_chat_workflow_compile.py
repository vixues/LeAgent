"""Tests for chat workflow compilation."""

from __future__ import annotations

from leagent.chat_workflow.compile import compile_chat_workflow_to_document
from leagent.chat_workflow.schema import ChatWorkflowSpec, ChatWorkflowStep, ChatWorkflowToolAction


def test_compile_linear_document() -> None:
    spec = ChatWorkflowSpec(
        title="Demo",
        steps=[
            ChatWorkflowStep(
                id="s1",
                label="Step 1",
                action=ChatWorkflowToolAction(tool_id="echo", arguments={"x": 1}),
            ),
            ChatWorkflowStep(
                id="s2",
                label="Step 2",
                action=ChatWorkflowToolAction(tool_id="echo", arguments={"y": 2}),
            ),
        ],
    )
    doc = compile_chat_workflow_to_document(spec)
    assert doc["start_id"] == "start"
    assert "s1" in doc["nodes"]
    assert doc["nodes"]["s1"]["class_type"] == "ToolCallNode"
    assert doc["nodes"]["s1"]["inputs"]["tool"] == "echo"
    assert any(e["source"] == "start" and e["target"] == "s1" for e in doc["edges"])
    assert any(e["target"] == "end" for e in doc["edges"])
