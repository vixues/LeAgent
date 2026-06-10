"""Shared execution helper for agent-backed workflow nodes.

Both the builtin agent nodes (``CodingAgentNode`` / ``ScriptAgentNode``)
and the auto-generated ``Agent.<name>`` nodes route through
:func:`run_agent_node`, so they behave as first-class graph citizens:

* **Dual path** — when a parent ``agent_controller`` is on the tool
  context the step runs as a sub-agent fork (:meth:`AgentRuntime.delegate`);
  otherwise it runs standalone via the streaming kernel
  (:meth:`AgentRuntime.stream`). No more hard failure when a workflow runs
  outside a chat turn.
* **Live streaming** — agent/sub-agent activity (assistant deltas, tool
  calls, results) is forwarded onto the node body through the
  :class:`~leagent.workflow.engine.progress.ProgressRegistry` carried on
  the :class:`~leagent.workflow.io.HiddenHolder`.
* **Rich outputs** — every agent node emits a uniform 6-tuple:
  ``(text, success, steps_count, checkpoint_id, activity, produced_files)``
  so downstream nodes can branch on success, resume from a checkpoint, or
  consume produced files.
* **Pause / resume** — a standalone run that ends ``awaiting_user_input``
  returns ``block_execution`` so the scheduler pauses the workflow. When the
  caller resumes with an answer (``POST /prompts/{id}/resume`` →
  ``state.variables["__resume__<node>"]``), the node continues the turn from
  its kernel checkpoint via :meth:`AgentRuntime.resume` instead of starting
  over.
* **Abort propagation** — the executor's per-run ``abort_event`` (set on
  cancel) is forwarded to the agent kernel so cancelling a workflow aborts
  the in-flight agent turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator
from uuid import UUID

import structlog

from leagent.sdk.events import AgentEventType
from leagent.workflow.io import HiddenHolder, NodeOutput

logger = structlog.get_logger(__name__)

#: Canonical output slot order shared by every agent node. Keep in sync
#: with the ``outputs=[...]`` in each node's ``define_schema``.
AGENT_OUTPUT_NAMES = (
    "text",
    "success",
    "steps_count",
    "checkpoint_id",
    "activity",
    "produced_files",
)

#: ``block_execution`` tag used when an agent turn pauses for user input.
AWAITING_USER_INPUT = "awaiting_user_input"


def _as_uuid(raw: Any) -> UUID | None:
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return UUID(raw)
        except ValueError:
            return None
    return None


def _progress_emitter(hidden: HiddenHolder):
    """Return a callback that forwards a preview row onto the node body."""
    progress = getattr(hidden, "progress", None)
    node_id = hidden.unique_id

    def _emit(row: Any) -> None:
        if progress is None or not node_id:
            return
        try:
            progress.update(preview=row, node_id=node_id)
        except Exception:  # noqa: BLE001 - progress is best-effort
            pass

    return _emit


def _normalize_files(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return list(raw)
    return []


@dataclass
class _AggregatedRun:
    """Uniform aggregate of one agent turn, however it was driven."""

    text: str = ""
    success: bool = False
    steps: int = 0
    checkpoint_id: str = ""
    activity: list[dict[str, Any]] = field(default_factory=list)
    produced: list[Any] = field(default_factory=list)
    reason: str = "completed"
    meta: dict[str, Any] = field(default_factory=dict)


async def _aggregate_agent_events(
    events: AsyncIterator[Any], *, emit: Any
) -> _AggregatedRun:
    """Drive an :class:`AgentEvent` stream and fold it into an aggregate."""
    text_parts: list[str] = []
    final_text = ""
    agg = _AggregatedRun()
    error: str | None = None

    async for event in events:
        etype = event.type
        data = event.data or {}
        if etype == AgentEventType.STREAM_DELTA:
            delta = data.get("content")
            if delta:
                text_parts.append(str(delta))
                emit({"type": "delta", "content": str(delta)})
        elif etype == AgentEventType.ASSISTANT:
            final_text = str(data.get("content") or "")
            if final_text:
                emit({"type": "assistant", "content": final_text})
        elif etype == AgentEventType.TOOL_USE:
            agg.steps += 1
            name = str(data.get("name") or data.get("tool") or "tool")
            agg.activity.append({"type": "tool_use", "name": name})
            emit({"type": "tool_use", "name": name})
        elif etype == AgentEventType.TOOL_RESULT:
            name = str(data.get("name") or data.get("tool") or "tool")
            agg.activity.append({"type": "tool_result", "name": name})
        elif etype == AgentEventType.WORKSPACE_ATTACHMENTS:
            for path in data.get("paths") or []:
                if path:
                    agg.produced.append(str(path))
        elif etype == AgentEventType.RESULT:
            agg.reason = str(data.get("reason") or "completed")
            error = data.get("error")
            agg.checkpoint_id = str(data.get("checkpoint_id") or "")

    agg.text = final_text or "".join(text_parts)
    agg.success = error is None and agg.reason in ("completed", AWAITING_USER_INPUT)
    agg.meta = {
        "reason": agg.reason,
        "partial": agg.reason not in ("completed", ""),
    }
    if error:
        agg.meta["agent_error"] = error
    return agg


def _take_resume_payload(
    state: Any, node_id: str | None
) -> tuple[str, str] | None:
    """Pop this node's resume answer + stashed checkpoint id, if any.

    Returns ``(checkpoint_id, answer)`` when the executor resumed a paused
    run and this node previously checkpointed; ``None`` otherwise.
    """
    if state is None or not node_id:
        return None
    try:
        payload = state.variables.pop(f"__resume__{node_id}", None)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    checkpoint_id = str(
        payload.get("checkpoint_id")
        or state.metadata.get("agent_checkpoints", {}).get(str(node_id))
        or ""
    )
    if not checkpoint_id:
        return None
    answer = str(
        payload.get("answer")
        or payload.get("input")
        or payload.get("comments")
        or ""
    )
    return checkpoint_id, answer or "continue"


def _stash_checkpoint(state: Any, node_id: str | None, checkpoint_id: str) -> None:
    """Record the kernel checkpoint id so the executor resume path finds it."""
    if state is None or not node_id or not checkpoint_id:
        return
    try:
        state.metadata.setdefault("agent_checkpoints", {})[str(node_id)] = checkpoint_id
    except Exception:  # noqa: BLE001
        pass


def _finalize(
    agg: _AggregatedRun,
    *,
    hidden: HiddenHolder,
    state: Any,
    meta: dict[str, Any],
    output_var: str | None,
) -> NodeOutput:
    if state is not None and output_var:
        state.set(output_var, agg.text)
    _stash_checkpoint(state, hidden.unique_id, agg.checkpoint_id)
    return NodeOutput(
        values=(
            agg.text,
            agg.success,
            agg.steps,
            agg.checkpoint_id,
            agg.activity,
            agg.produced,
        ),
        metadata=meta,
    )


async def run_agent_node(
    *,
    hidden: HiddenHolder,
    agent_name: str,
    prompt: str,
    allowed_tools: list[str] | None,
    max_turns: int | None,
    tool_extra: dict[str, Any] | None = None,
    cwd: str | None = None,
    output_var: str | None = None,
    log_event: str = "agent_node",
    extra_metadata: dict[str, Any] | None = None,
) -> NodeOutput:
    """Execute an agent step and return the uniform agent NodeOutput.

    Streams intermediate activity onto the node, falls back to a standalone
    run when no parent ``agent_controller`` is available, pauses the workflow
    when the agent asks for user input, and resumes from the kernel
    checkpoint when the executor re-runs the node with resume data.
    """
    runtime = hidden.agent_runtime
    if runtime is None:
        return NodeOutput(
            error="Agent runtime not available on the workflow executor",
            metadata={"node_id": hidden.unique_id, "agent": agent_name},
        )

    ctx = hidden.tool_context
    parent = getattr(ctx, "agent_controller", None) if ctx else None
    emit = _progress_emitter(hidden)
    meta: dict[str, Any] = {"agent": agent_name, **(extra_metadata or {})}
    state = hidden.workflow_state

    # Resume path: the executor stashes the caller's answer under
    # ``__resume__<node_id>`` when a paused run is resumed. If this node
    # previously checkpointed (awaiting_user_input), continue that turn from
    # the kernel checkpoint instead of starting a fresh run.
    resume_payload = _take_resume_payload(state, hidden.unique_id)
    if resume_payload is not None:
        checkpoint_id, answer = resume_payload
        try:
            agg = await _aggregate_agent_events(
                runtime.resume(
                    agent_name,
                    checkpoint_id,
                    answer,
                    user_id=_as_uuid(hidden.user_id),
                    cwd=cwd or ".",
                    tool_extra=tool_extra,
                    abort_event=hidden.abort_event,
                ),
                emit=emit,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "agent_node_resume_error",
                agent=agent_name,
                checkpoint_id=checkpoint_id,
                error=str(exc),
                exc_info=True,
            )
            return NodeOutput(
                error=str(exc),
                metadata={
                    "node_id": hidden.unique_id,
                    "agent": agent_name,
                    "mode": "resume",
                },
            )
        meta.update(agg.meta)
        meta["mode"] = "resume"
        meta["resumed_from"] = checkpoint_id
        return _finalize(agg, hidden=hidden, state=state, meta=meta,
                         output_var=output_var)

    try:
        if parent is not None:
            envelope = await runtime.delegate(
                parent,
                agent_name,
                prompt,
                allowed_tools=allowed_tools,
                max_turns=max_turns,
                tool_extra=tool_extra,
                cwd=cwd,
                inherit_abort=True,
                nested_preview_emit=emit,
                log_event=log_event,
                log_fields={"node_id": hidden.unique_id},
            )
            agg = _AggregatedRun(
                text=str(envelope.get("text") or ""),
                success=bool(envelope.get("success")),
                steps=int(envelope.get("steps_count") or 0),
                checkpoint_id=str(envelope.get("checkpoint_id") or ""),
                activity=list(envelope.get("activity") or []),
                produced=_normalize_files(envelope.get("produced_files")),
            )
            meta["partial"] = bool(envelope.get("partial"))
            meta["mode"] = "delegate"
            if envelope.get("changed_files"):
                meta["changed_files"] = list(envelope["changed_files"])
            if envelope.get("error"):
                meta["agent_error"] = envelope["error"]
        else:
            agg = await _run_standalone_stream(
                runtime=runtime,
                hidden=hidden,
                agent_name=agent_name,
                prompt=prompt,
                allowed_tools=allowed_tools,
                max_turns=max_turns,
                tool_extra=tool_extra,
                cwd=cwd,
                emit=emit,
            )
            meta.update(agg.meta)
            meta["mode"] = "standalone"

            # The agent paused asking the user a question: checkpoint the
            # turn and pause the whole workflow so the caller can answer via
            # the resume endpoint (first-class checkpoint/resume).
            if agg.reason == AWAITING_USER_INPUT and agg.checkpoint_id:
                _stash_checkpoint(state, hidden.unique_id, agg.checkpoint_id)
                return NodeOutput(
                    values=(
                        agg.text,
                        agg.success,
                        agg.steps,
                        agg.checkpoint_id,
                        agg.activity,
                        agg.produced,
                    ),
                    block_execution=AWAITING_USER_INPUT,
                    ui={
                        "question": agg.text,
                        "checkpoint_id": agg.checkpoint_id,
                        "agent": agent_name,
                    },
                    metadata=meta,
                )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "agent_node_error", agent=agent_name, error=str(exc), exc_info=True
        )
        return NodeOutput(
            error=str(exc),
            metadata={"node_id": hidden.unique_id, "agent": agent_name},
        )

    return _finalize(agg, hidden=hidden, state=state, meta=meta,
                     output_var=output_var)


async def _run_standalone_stream(
    *,
    runtime: Any,
    hidden: HiddenHolder,
    agent_name: str,
    prompt: str,
    allowed_tools: list[str] | None,
    max_turns: int | None,
    tool_extra: dict[str, Any] | None,
    cwd: str | None,
    emit: Any,
) -> _AggregatedRun:
    """Drive ``runtime.stream`` standalone and aggregate node outputs."""
    definition = runtime.resolve(agent_name)
    if max_turns:
        definition = definition.with_overrides(max_turns=max_turns)
    if allowed_tools is not None:
        definition = definition.with_overrides(
            tools=definition.tools.model_copy(update={"allow": allowed_tools})
        )

    return await _aggregate_agent_events(
        runtime.stream(
            definition,
            prompt,
            session_id=_as_uuid(hidden.session_id),
            user_id=_as_uuid(hidden.user_id),
            cwd=cwd or ".",
            tool_extra=tool_extra,
            abort_event=hidden.abort_event,
        ),
        emit=emit,
    )


__all__ = ["run_agent_node", "AGENT_OUTPUT_NAMES", "AWAITING_USER_INPUT"]
