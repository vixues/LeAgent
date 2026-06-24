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


@dataclass
class ChatWorkflowEmbedStartOutcome:
    """Result of starting a chat workflow DAG embed run (background execution)."""

    started: bool
    prompt_id: str | None = None
    run_id: str | None = None
    error: str | None = None


@dataclass
class ChatWorkflowEmbedResult:
    """Terminal result of an embed run, delivered to ``on_complete``."""

    success: bool
    outputs: dict[str, Any] | None = None
    error: str | None = None


def evaluate_embed_result(result: Any | None) -> ChatWorkflowEmbedResult:
    """Map a terminal :class:`WorkflowResult` to a chat-facing embed result.

    Honors the engine quality-gate convention: a completed run that scored
    below the bar surfaces ``success=False`` so the agent re-runs in-turn.
    """
    if result is None:
        return ChatWorkflowEmbedResult(success=False, error="Workflow failed")
    outputs = result.outputs if isinstance(getattr(result, "outputs", None), dict) else None
    if not getattr(result, "success", False):
        err = "; ".join(result.errors) if getattr(result, "errors", None) else "Workflow failed"
        return ChatWorkflowEmbedResult(success=False, outputs=outputs, error=err)
    below_bar_error = _quality_gate_error(outputs)
    return ChatWorkflowEmbedResult(
        success=below_bar_error is None,
        outputs=outputs,
        error=below_bar_error,
    )


async def start_chat_workflow_embed_via_engine(
    *,
    flow_data: dict[str, Any],
    service_manager: Any | None,
    user_id: str,
    session_id: str,
    user_input: str = "",
    inputs: dict[str, Any] | None = None,
    parent_run_id: str | None = None,
    on_complete: Any | None = None,
) -> ChatWorkflowEmbedStartOutcome:
    """Start a whole DAG embed run in the background via the workflow engine.

    ``flow_data`` is the same Flow.data-shaped JSON persisted in the chat embed.
    Returns execution-plane ids immediately so the client can subscribe to the
    per-node WebSocket and render live status while the graph runs.
    ``inputs`` carries structured run values from the GenUI operation panel,
    whitelisted against the document's declared inputs and merged into the
    engine state so ``${input.<name>}`` (and ``${user_input}``) resolve.
    ``on_complete`` (async callable) receives the terminal ``WorkflowResult``.
    """
    from uuid import UUID

    from leagent.chat_workflow.workflow_embed import (
        WorkflowEmbedValidationError,
        prepare_engine_document,
    )

    wf_service = getattr(service_manager, "workflow_service", None) if service_manager else None
    if wf_service is None:
        return ChatWorkflowEmbedStartOutcome(started=False, error="Workflow service unavailable")

    try:
        document = prepare_engine_document(flow_data)
    except WorkflowEmbedValidationError as exc:
        return ChatWorkflowEmbedStartOutcome(started=False, error=str(exc))

    engine_inputs: dict[str, Any] = {
        "session_id": session_id,
        "user_id": user_id,
        "user_input": user_input,
    }
    engine_inputs.update(_sanitize_embed_inputs(inputs, document, flow_data))

    try:
        start_out = await wf_service.start_compiled_document(
            document,
            user_id=UUID(user_id),
            session_id=session_id,
            inputs=engine_inputs,
            trigger_type="chat_embed",
            parent_run_id=parent_run_id,
            extra_data={"session_id": session_id, "user_id": user_id},
            on_complete=on_complete,
        )
    except Exception as exc:  # noqa: BLE001
        return ChatWorkflowEmbedStartOutcome(started=False, error=str(exc))

    return ChatWorkflowEmbedStartOutcome(
        started=True,
        prompt_id=start_out.get("prompt_id"),
        run_id=start_out.get("run_id"),
    )


def _declared_input_names(source: Any) -> set[str]:
    """Collect declared input names from a document/flow_data ``inputs`` array."""
    raw = source.get("inputs") if isinstance(source, dict) else getattr(source, "inputs", None)
    names: set[str] = set()
    if isinstance(raw, list):
        for spec in raw:
            name = spec.get("name") if isinstance(spec, dict) else getattr(spec, "name", None)
            if isinstance(name, str) and name:
                names.add(name)
    return names


def _sanitize_embed_inputs(
    inputs: dict[str, Any] | None,
    document: Any,
    flow_data: dict[str, Any],
) -> dict[str, Any]:
    """Whitelist structured run inputs against the document's declared inputs.

    Always permits ``user_input`` (the legacy single placeholder). Unknown keys
    are dropped so a stale or crafted form cannot inject arbitrary engine state.
    """
    if not isinstance(inputs, dict) or not inputs:
        return {}
    declared: set[str] = {"user_input"}
    declared |= _declared_input_names(flow_data)
    declared |= _declared_input_names(document)
    return {k: v for k, v in inputs.items() if isinstance(k, str) and k in declared}


def _quality_gate_error(outputs: dict[str, Any] | None) -> str | None:
    """Return an error string when outputs indicate a below-bar quality gate."""
    if not isinstance(outputs, dict):
        return None
    passed = outputs.get("quality_passed")
    if passed is None or bool(passed):
        return None
    score = outputs.get("quality_score")
    threshold = outputs.get("quality_threshold")
    try:
        shown = float(score) if score is not None else None
        bar = float(threshold) if threshold is not None else None
    except (TypeError, ValueError):
        shown = bar = None
    if shown is not None and bar is not None:
        return (
            f"Workflow completed but the asset scored {shown:.2f} below the "
            f"quality bar {bar:.2f}. Refine and re-run to close the loop."
        )
    return "Workflow completed but did not pass the quality gate."


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

    step_output = (result.outputs or {}).get(step_id)
    data = step_output if isinstance(step_output, dict) else {"result": step_output}
    return ChatWorkflowStepRunOutcome(
        tool_result=ToolResult(success=True, data=data, duration_ms=duration_ms),
        prompt_id=run_out.get("prompt_id"),
        run_id=run_out.get("run_id"),
    )


__all__ = [
    "ChatWorkflowStepRunOutcome",
    "ChatWorkflowEmbedStartOutcome",
    "ChatWorkflowEmbedResult",
    "run_chat_workflow_step_via_engine",
    "start_chat_workflow_embed_via_engine",
    "evaluate_embed_result",
]
