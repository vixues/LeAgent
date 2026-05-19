"""``ToolCallNode`` — invoke a registered tool via the ToolExecutor."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class ToolCallNode(WorkflowNode):
    NODE_ID = "ToolCallNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="ToolCallNode",
            display_name="Tool Call",
            category="workflow/action",
            description="Execute a registered tool with templated params.",
            inputs=[
                IO.String.Input(id="tool", tooltip="Tool name as registered in ToolRegistry"),
                IO.Object.Input(id="params", optional=True, default={},
                                 tooltip="Tool parameters (templates resolved)"),
                IO.Int.Input(id="retry_count", optional=True, default=0, min=0, max=10),
                IO.Float.Input(id="retry_delay_sec", optional=True, default=1.0,
                               min=0.0, max=60.0, step=0.5),
                IO.String.Input(id="output", optional=True,
                                tooltip="Variable name to store the result in workflow state"),
            ],
            outputs=[IO.Any.Output(id="result")],
            hidden=[Hidden.UNIQUE_ID, Hidden.TOOL_CONTEXT, Hidden.WORKFLOW_STATE],
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        ctx = hidden.tool_context
        if ctx is None or getattr(ctx, "tool_executor", None) is None:
            return NodeOutput(error="Tool executor not available", metadata={"node_id": hidden.unique_id})

        tool = inputs.get("tool")
        if not tool:
            return NodeOutput(error="Missing required 'tool' input")

        state = hidden.workflow_state
        params = inputs.get("params") or {}
        if state is not None:
            params = state.resolve_template(params)

        retry_count = int(inputs.get("retry_count") or 0)
        retry_delay_sec = float(inputs.get("retry_delay_sec") or 1.0)

        tool_context = ctx.get_tool_context(state) if hasattr(ctx, "get_tool_context") else None
        last_error: str | None = None
        start = time.monotonic()
        for attempt in range(retry_count + 1):
            try:
                exec_result = await ctx.tool_executor.execute(tool, params, tool_context)
                tool_result = exec_result.result
                if tool_result.success:
                    duration_ms = int((time.monotonic() - start) * 1000)
                    if state is not None and inputs.get("output"):
                        state.set(inputs["output"], tool_result.data)
                    return NodeOutput(
                        values=(tool_result.data,),
                        metadata={"tool": tool, "attempts": attempt + 1,
                                  "duration_ms": duration_ms},
                    )
                last_error = tool_result.error or "Tool execution failed"
                logger.warning("tool_call_failed", tool=tool, attempt=attempt + 1, error=last_error)
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.error("tool_call_exception", tool=tool, attempt=attempt + 1,
                             error=last_error, exc_info=True)

            if attempt < retry_count:
                await asyncio.sleep(retry_delay_sec * (2 ** attempt))

        duration_ms = int((time.monotonic() - start) * 1000)
        return NodeOutput(
            error=last_error,
            metadata={"tool": tool, "attempts": retry_count + 1, "duration_ms": duration_ms},
        )
