"""``StartNode`` — entry-point marker. Emits the workflow's input bag."""

from __future__ import annotations

from typing import Any

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode


class StartNode(WorkflowNode):
    NODE_ID = "StartNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="StartNode",
            display_name="Start",
            category="workflow/control",
            description="Workflow entry point.",
            inputs=[],
            outputs=[IO.Object.Output(id="inputs")],
            hidden=[Hidden.UNIQUE_ID, Hidden.EXECUTION_ID, Hidden.WORKFLOW_STATE],
            is_output_node=False,
            control_flow=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        bag = dict(state.variables) if state is not None else {}
        return NodeOutput(values=(bag,))
