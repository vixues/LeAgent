"""Run chat workflow steps through the workflow engine kernel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from leagent.chat_workflow.compile import compile_chat_workflow_to_document
from leagent.chat_workflow.schema import ChatWorkflowSpec
from leagent.tools.base import ToolContext, ToolResult


@dataclass
class ChatWorkflowStepRunOutcome:
    """Result of a chat workflow step run including execution-plane ids."""

    tool_result: ToolResult
    prompt_id: str | None = None
    run_id: str | None = None


async def run_chat_workflow_step_via_engine(
    *,
    spec: ChatWorkflowSpec,
    step_id: str,
    resolved_args: dict[str, Any],
    tool_ctx: ToolContext,
    service_manager: Any | None,
    user_id: str,
    session_id: str,
    parent_run_id: str | None = None,
) -> ChatWorkflowStepRunOutcome:
    """Execute one step via :meth:`WorkflowService.run_compiled_document`."""
    from leagent.tools.executor import ToolExecutor
    from leagent.workflow.io.loader import load

    wf_service = getattr(service_manager, "workflow_service", None) if service_manager else None
    step = next((s for s in spec.steps if s.id == step_id), None)
    if step is None:
        return ChatWorkflowStepRunOutcome(
            tool_result=ToolResult(success=False, error=f"Unknown step: {step_id}"),
        )

    if wf_service is None:
        from leagent.tools.registry import get_registry

        executor = ToolExecutor(registry=get_registry())
        if service_manager is not None:
            executor.set_service_manager(service_manager)
        result = await executor.run_tool(step.action.tool_id, resolved_args, tool_ctx)
        return ChatWorkflowStepRunOutcome(tool_result=result)

    raw_doc = compile_chat_workflow_to_document(spec)
    raw_doc["nodes"][step_id]["inputs"]["params"] = dict(resolved_args)
    document = load(raw_doc)

    import time
    from uuid import UUID

    started = time.perf_counter()
    try:
        run_out = await wf_service.run_compiled_document(
            document,
            user_id=UUID(user_id),
            session_id=session_id,
            inputs={
                "session_id": session_id,
                "user_id": user_id,
            },
            outputs_to_execute=[step_id],
            trigger_type="chat_step",
            parent_run_id=parent_run_id,
            extra_data={
                "session_id": session_id,
                "user_id": user_id,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return ChatWorkflowStepRunOutcome(
            tool_result=ToolResult(
                success=False,
                error=str(exc),
                duration_ms=int((time.perf_counter() - started) * 1000),
            ),
        )

    result = run_out["result"]
    duration_ms = int((time.perf_counter() - started) * 1000)
    if not result.success:
        err = "; ".join(result.errors) if result.errors else "Workflow step failed"
        return ChatWorkflowStepRunOutcome(
            tool_result=ToolResult(success=False, error=err, duration_ms=duration_ms),
            prompt_id=run_out.get("prompt_id"),
            run_id=run_out.get("run_id"),
        )

    step_output = (result.state.outputs or {}).get(step_id)
    data = step_output if isinstance(step_output, dict) else {"result": step_output}
    return ChatWorkflowStepRunOutcome(
        tool_result=ToolResult(success=True, data=data, duration_ms=duration_ms),
        prompt_id=run_out.get("prompt_id"),
        run_id=run_out.get("run_id"),
    )


__all__ = ["ChatWorkflowStepRunOutcome", "run_chat_workflow_step_via_engine"]
