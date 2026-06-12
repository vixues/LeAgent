"""Compile chat workflow step cards into linear WorkflowDocument graphs."""

from __future__ import annotations

from typing import Any

from leagent.chat_workflow.schema import ChatWorkflowSpec


def compile_chat_workflow_to_document(
    spec: ChatWorkflowSpec,
    *,
    workflow_id: str | None = None,
) -> dict[str, Any]:
    """Build a linear Start → ToolCall* → End document from a step card spec."""
    nodes: dict[str, Any] = {}
    edges: list[dict[str, str]] = []
    start_id = "start"
    nodes[start_id] = {"class_type": "StartNode", "inputs": {}}

    prev_id = start_id
    for step in spec.steps:
        node_id = step.id
        nodes[node_id] = {
            "class_type": "ToolCallNode",
            "inputs": {
                "tool": step.action.tool_id,
                "params": dict(step.action.arguments),
            },
            "meta": {"label": step.label, "hint": step.hint},
        }
        edges.append({"source": prev_id, "target": node_id})
        prev_id = node_id

    end_id = "end"
    nodes[end_id] = {"class_type": "EndNode", "inputs": {}}
    edges.append({"source": prev_id, "target": end_id})
    if prev_id in nodes:
        nodes[prev_id].setdefault("control", {})["next"] = end_id

    return {
        "id": workflow_id or f"chat-workflow-{spec.title[:40]}",
        "nodes": nodes,
        "edges": edges,
        "start_id": start_id,
        "outputs": [],
    }


__all__ = ["compile_chat_workflow_to_document"]
