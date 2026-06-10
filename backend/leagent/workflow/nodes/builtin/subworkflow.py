"""``SubworkflowNode`` — invoke another Flow by id."""

from __future__ import annotations

import time
from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class SubworkflowNode(WorkflowNode):
    NODE_ID = "SubworkflowNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="SubworkflowNode",
            display_name="Subworkflow",
            category="workflow/control",
            description="Delegate execution to another flow by id.",
            inputs=[
                IO.String.Input(id="subworkflow_id"),
                IO.Object.Input(id="subworkflow_inputs", optional=True, default={}),
                IO.String.Input(id="output", optional=True),
            ],
            outputs=[IO.Object.Output(id="outputs")],
            hidden=[
                Hidden.UNIQUE_ID,
                Hidden.TOOL_CONTEXT,
                Hidden.WORKFLOW_STATE,
                Hidden.EXECUTION_ID,
                Hidden.AGENT_RUNTIME,
                Hidden.USER_ID,
                Hidden.SESSION_ID,
            ],
            enable_expand=True,
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        sub_id = inputs.get("subworkflow_id")
        if not sub_id:
            return NodeOutput(error="Subworkflow node missing 'subworkflow_id'")

        ctx = hidden.tool_context
        registry = getattr(ctx, "workflow_registry", None) if ctx else None
        if registry is None:
            return NodeOutput(error="Workflow registry not available")

        state = hidden.workflow_state
        resolved_inputs = state.resolve_template(inputs.get("subworkflow_inputs") or {}) if state is not None else inputs.get("subworkflow_inputs") or {}

        start = time.monotonic()
        try:
            sub_def = await registry.get(sub_id)
            if not sub_def:
                return NodeOutput(error=f"Subworkflow '{sub_id}' not found")

            from uuid import uuid4

            from leagent.workflow.engine.executor import (  # local import
                WorkflowExecutor,
                _ensure_document,
            )

            executor = WorkflowExecutor(
                tool_registry=getattr(ctx, "tool_registry", None),
                tool_executor=getattr(ctx, "tool_executor", None),
                llm_service=getattr(ctx, "llm_service", None),
                review_service=getattr(ctx, "review_service", None),
                agent_runtime=hidden.agent_runtime or getattr(ctx, "agent_runtime", None),
            )
            # Child run inherits the parent's identity (agent nodes need
            # user/session) and abort signal (cancelling the parent cancels
            # nested runs too).
            result = await executor.execute_async(
                _ensure_document(sub_def),
                resolved_inputs,
                prompt_id=str(uuid4()),
                extra_data={
                    "user_id": hidden.user_id,
                    "session_id": hidden.session_id,
                    "parent_execution_id": hidden.execution_id,
                },
                abort_event=hidden.abort_event,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            if result.success:
                if state is not None and inputs.get("output"):
                    state.set(inputs["output"], result.outputs)
                return NodeOutput(
                    values=(result.outputs,),
                    metadata={"subworkflow_id": sub_id, "duration_ms": duration_ms},
                )
            err = "; ".join(result.errors) if result.errors else "Subworkflow failed"
            return NodeOutput(error=err, metadata={"subworkflow_id": sub_id, "duration_ms": duration_ms})
        except Exception as exc:  # noqa: BLE001
            logger.error("subworkflow_error", subworkflow_id=sub_id, error=str(exc), exc_info=True)
            return NodeOutput(error=str(exc))
