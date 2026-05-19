"""``ErrorHandlerNode`` — runs after an upstream failure and optionally invokes
a recovery tool."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class ErrorHandlerNode(WorkflowNode):
    NODE_ID = "ErrorHandlerNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="ErrorHandlerNode",
            display_name="Error Handler",
            category="workflow/control",
            description="Post-mortem node — optionally runs a recovery tool.",
            inputs=[
                IO.String.Input(id="tool", optional=True),
                IO.Object.Input(id="params", optional=True, default={}),
                IO.String.Input(id="output", optional=True),
            ],
            outputs=[IO.Object.Output(id="error_context")],
            hidden=[Hidden.UNIQUE_ID, Hidden.TOOL_CONTEXT, Hidden.WORKFLOW_STATE],
            control_flow=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        error_context = {
            "error_stack": list(getattr(state, "error_stack", []) or []) if state is not None else [],
            "last_error": (state.error_stack[-1] if state is not None and state.error_stack else None),
            "retry_count": getattr(state, "retry_count", 0) if state is not None else 0,
            "current_node": getattr(state, "current_node", None) if state is not None else None,
        }

        ctx = hidden.tool_context
        tool = inputs.get("tool")
        if tool and ctx is not None and getattr(ctx, "tool_executor", None) is not None:
            params = inputs.get("params") or {}
            if state is not None:
                params = state.resolve_template(params)
            params["_error_context"] = error_context
            try:
                tool_ctx = ctx.get_tool_context(state) if hasattr(ctx, "get_tool_context") else None
                exec_result = await ctx.tool_executor.execute(tool, params, tool_ctx)
                if exec_result.result.success and state is not None and inputs.get("output"):
                    state.set(inputs["output"], exec_result.result.data)
            except Exception as exc:  # noqa: BLE001
                logger.error("error_handler_tool_failed", tool=tool, error=str(exc))

        return NodeOutput(values=(error_context,),
                          metadata={"handled_errors": len(error_context["error_stack"])})
