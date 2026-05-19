"""``ConditionNode`` — evaluate expressions, route to matching branch."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class ConditionNode(WorkflowNode):
    NODE_ID = "ConditionNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="ConditionNode",
            display_name="Condition",
            category="workflow/control",
            description=(
                "Evaluates each 'condition' in control.conditions and routes to "
                "the first matching ``then_node``. Falls back to ``else_node``."
            ),
            inputs=[],
            outputs=[IO.Object.Output(id="result")],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
            control_flow=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        node_id = hidden.unique_id
        control = _control_for(hidden, node_id)
        conditions = control.get("conditions", []) or []
        else_node = control.get("else_node") or control.get("else")

        for i, cond in enumerate(conditions):
            expr = cond.get("if") or cond.get("if_expr") or cond
            try:
                matched = _eval(state, expr)
            except Exception as exc:  # noqa: BLE001
                logger.warning("condition_eval_error", node_id=node_id,
                               index=i, error=str(exc))
                continue
            if matched:
                target = cond.get("then_node") or cond.get("then")
                return NodeOutput(
                    values=({"matched_condition": i, "target": target},),
                    next_node=target,
                    metadata={"matched_index": i},
                )

        if else_node:
            return NodeOutput(
                values=({"matched_condition": None, "target": else_node},),
                next_node=else_node,
                metadata={"used_else": True},
            )

        return NodeOutput(error="No condition matched and no else branch defined")


def _eval(state: Any, expr: Any) -> bool:
    if state is not None and hasattr(state, "evaluate_expression"):
        return bool(state.evaluate_expression(expr))
    return bool(expr)


def _control_for(hidden: HiddenHolder, node_id: str | None) -> dict[str, Any]:
    if not node_id:
        return {}
    prompt = hidden.prompt or {}
    node = prompt.get(node_id) if isinstance(prompt, dict) else None
    if isinstance(node, dict):
        return node.get("control", {}) or {}
    return {}
