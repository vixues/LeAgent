"""``WaitNode`` — sleep for a fixed duration before continuing."""

from __future__ import annotations

import asyncio
from typing import Any

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode


class WaitNode(WorkflowNode):
    NODE_ID = "WaitNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="WaitNode",
            display_name="Wait",
            category="workflow/control",
            description="Sleep for ``seconds`` before continuing. Allows cancel checks.",
            inputs=[
                IO.Float.Input(id="seconds", default=1.0, min=0.0, max=3600.0, step=0.1),
            ],
            outputs=[IO.Any.Output(id="noop")],
            hidden=[Hidden.UNIQUE_ID],
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        seconds = float(inputs.get("seconds") or 0.0)
        if seconds > 0:
            await asyncio.sleep(seconds)
        return NodeOutput(values=(None,), metadata={"slept_sec": seconds})
