"""``TransformNode`` — evaluate a template expression and emit the result."""

from __future__ import annotations

from typing import Any

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode


class TransformNode(WorkflowNode):
    NODE_ID = "TransformNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="TransformNode",
            display_name="Transform",
            category="workflow/data",
            description="Evaluate a template expression over the workflow state.",
            inputs=[
                IO.Any.Input(id="transform"),
                IO.String.Input(id="output", optional=True),
            ],
            outputs=[IO.Any.Output(id="result")],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        expr = inputs.get("transform")
        if expr is None:
            return NodeOutput(error="Transform node missing 'transform' input")
        state = hidden.workflow_state
        try:
            result = state.resolve_template(expr) if state is not None else expr
        except Exception as exc:  # noqa: BLE001
            return NodeOutput(error=str(exc))
        if state is not None and inputs.get("output"):
            state.set(inputs["output"], result)
        return NodeOutput(values=(result,))
