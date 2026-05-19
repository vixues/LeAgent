"""``EndNode`` — terminal marker. Collects ``WorkflowDefinition.outputs``."""

from __future__ import annotations

from typing import Any

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode


class EndNode(WorkflowNode):
    NODE_ID = "EndNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="EndNode",
            display_name="End",
            category="workflow/control",
            description="Workflow terminator. Marked as an output node so the "
                        "validator treats it as a required root.",
            inputs=[IO.Any.Input(id="value", optional=True)],
            outputs=[IO.Object.Output(id="outputs")],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
            is_output_node=True,
            control_flow=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        outs = dict(state.outputs) if state is not None else {}
        return NodeOutput(values=(outs,), next_node=None)
