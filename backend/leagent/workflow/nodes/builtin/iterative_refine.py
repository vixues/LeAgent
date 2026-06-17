"""``IterativeRefineNode`` — bounded self-correction loop controller.

Placed on the failure branch of a :class:`QualityGateNode`. Each pass it
increments a state-held iteration counter and, while under
``max_iterations``, routes back to the generation node
(``control.retry_node``) to regenerate. Once the budget is exhausted it
routes to ``control.exhausted_node`` so the workflow always terminates.

It is registered as a *loop-safe* node so the validator permits the
back-edge it creates without raising a dependency-cycle error.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema

from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class IterativeRefineNode(WorkflowNode):
    NODE_ID = "IterativeRefineNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="IterativeRefineNode",
            display_name="Iterative Refine",
            category="art/evaluate",
            description=(
                "Bounded regenerate loop: increments an iteration counter and "
                "routes back to control.retry_node until max_iterations, then "
                "to control.exhausted_node."
            ),
            inputs=[
                IO.Int.Input(id="max_iterations", optional=True, default=3, min=1, max=20,
                             tooltip="Maximum regeneration attempts."),
                IO.String.Input(id="iteration_var", optional=True, default="refine_iteration",
                                tooltip="State variable holding the iteration count."),
                IO.String.Input(id="feedback", optional=True, multiline=True,
                                tooltip="Optional critique fed back into regeneration."),
            ],
            outputs=[
                IO.Int.Output(id="iteration"),
                IO.Boolean.Output(id="exhausted"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
            control_flow=True,
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        node_id = hidden.unique_id
        var = str(inputs.get("iteration_var") or "refine_iteration")
        max_iter = int(inputs.get("max_iterations") if inputs.get("max_iterations") is not None else 3)

        current = 0
        if state is not None:
            try:
                current = int(state.get(var, 0) or 0)
            except (ValueError, TypeError):
                current = 0
        current += 1
        if state is not None:
            state.set(var, current)
            if inputs.get("feedback"):
                state.set("refine_feedback", inputs["feedback"])

        exhausted = current > max_iter
        control = _control_for(hidden, node_id)
        retry_node = control.get("retry_node") or control.get("next")
        exhausted_node = control.get("exhausted_node") or control.get("else_node")
        target = exhausted_node if exhausted else retry_node

        logger.info(
            "iterative_refine", node_id=node_id, iteration=current,
            max_iterations=max_iter, exhausted=exhausted, target=target,
        )
        return NodeOutput(
            values=(current, exhausted),
            next_node=target,
            metadata={"iteration": current, "max_iterations": max_iter, "exhausted": exhausted},
        )


def _control_for(hidden: HiddenHolder, node_id: str | None) -> dict[str, Any]:
    if not node_id:
        return {}
    prompt = hidden.prompt or {}
    node = prompt.get(node_id) if isinstance(prompt, dict) else None
    if isinstance(node, dict):
        return node.get("control", {}) or {}
    return {}
