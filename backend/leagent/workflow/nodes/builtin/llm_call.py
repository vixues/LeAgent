"""``LLMCallNode`` — call the LLMService with a templated prompt."""

from __future__ import annotations

import time
from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class LLMCallNode(WorkflowNode):
    NODE_ID = "LLMCallNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="LLMCallNode",
            display_name="LLM Call",
            category="workflow/ai",
            description="Call the configured LLM service with a templated prompt.",
            inputs=[
                IO.String.Input(id="prompt", multiline=True),
                IO.String.Input(id="model", optional=True, default=""),
                IO.Float.Input(id="temperature", optional=True, default=0.1,
                               min=0.0, max=2.0, step=0.1),
                IO.Int.Input(id="max_tokens", optional=True, default=4096,
                             min=1, max=32768),
                IO.String.Input(id="output", optional=True),
            ],
            outputs=[IO.String.Output(id="content")],
            hidden=[Hidden.UNIQUE_ID, Hidden.TOOL_CONTEXT, Hidden.WORKFLOW_STATE],
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        ctx = hidden.tool_context
        llm = getattr(ctx, "llm_service", None) if ctx else None
        if llm is None:
            return NodeOutput(error="LLM service not available")
        prompt = inputs.get("prompt")
        if not prompt:
            return NodeOutput(error="Missing 'prompt' input")

        state = hidden.workflow_state
        if state is not None:
            prompt = state.resolve_template(prompt)

        start = time.monotonic()
        try:
            from leagent.llm import ChatMessage
            messages = [ChatMessage.user(prompt)]
            response = await llm.complete(
                messages=messages,
                model=inputs.get("model") or None,
                temperature=float(inputs.get("temperature") or 0.1),
                max_tokens=int(inputs.get("max_tokens") or 4096),
            )
            content = response.content or ""
            duration_ms = int((time.monotonic() - start) * 1000)
            if state is not None and inputs.get("output"):
                state.set(inputs["output"], content)
            return NodeOutput(
                values=(content,),
                metadata={"model": inputs.get("model"), "duration_ms": duration_ms,
                          "response_length": len(content)},
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error("llm_call_failed", error=str(exc), duration_ms=duration_ms, exc_info=True)
            return NodeOutput(error=str(exc), metadata={"duration_ms": duration_ms})
