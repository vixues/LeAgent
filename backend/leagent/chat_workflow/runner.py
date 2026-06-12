"""Run chat workflow steps through the workflow engine kernel."""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from leagent.chat_workflow.compile import compile_chat_workflow_to_document
from leagent.chat_workflow.schema import ChatWorkflowSpec
from leagent.tools.base import ToolContext, ToolResult


async def run_chat_workflow_step_via_engine(
    *,
    spec: ChatWorkflowSpec,
    step_id: str,
    resolved_args: dict[str, Any],
    tool_ctx: ToolContext,
    service_manager: Any | None,
    user_id: str,
    session_id: str,
) -> ToolResult:
    """Execute one step via scoped :class:`WorkflowExecutor` invocation."""
    from leagent.tools.executor import ToolExecutor
    from leagent.workflow.io.loader import load

    wf_service = getattr(service_manager, "workflow_service", None) if service_manager else None
    step = next((s for s in spec.steps if s.id == step_id), None)
    if step is None:
        return ToolResult(success=False, error=f"Unknown step: {step_id}")

    if wf_service is None:
        from leagent.tools.registry import get_registry

        executor = ToolExecutor(registry=get_registry())
        if service_manager is not None:
            executor.set_service_manager(service_manager)
        return await executor.run_tool(step.action.tool_id, resolved_args, tool_ctx)

    raw_doc = compile_chat_workflow_to_document(spec)
    raw_doc["nodes"][step_id]["inputs"]["params"] = dict(resolved_args)
    document = load(raw_doc)

    prompt_id = f"chat-step-{step_id}-{uuid4().hex[:12]}"
    started = time.perf_counter()
    try:
        result = await wf_service._executor.execute_async(
            document,
            {
                "session_id": session_id,
                "user_id": user_id,
            },
            prompt_id=prompt_id,
            outputs_to_execute=[step_id],
            extra_data={
                "session_id": session_id,
                "user_id": user_id,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(
            success=False,
            error=str(exc),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    duration_ms = int((time.perf_counter() - started) * 1000)
    if not result.success:
        err = "; ".join(result.errors) if result.errors else "Workflow step failed"
        return ToolResult(success=False, error=err, duration_ms=duration_ms)

    step_output = (result.state.outputs or {}).get(step_id)
    data = step_output if isinstance(step_output, dict) else {"result": step_output}
    return ToolResult(success=True, data=data, duration_ms=duration_ms)


__all__ = ["run_chat_workflow_step_via_engine"]
