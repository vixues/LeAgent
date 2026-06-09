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
"""

from __future__ import annotations

from typing import Any
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

    Streams intermediate activity onto the node and falls back to a
    standalone run when no parent ``agent_controller`` is available.
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
            text = str(envelope.get("text") or "")
            success = bool(envelope.get("success"))
            steps = int(envelope.get("steps_count") or 0)
            activity = list(envelope.get("activity") or [])
            produced = _normalize_files(envelope.get("produced_files"))
            checkpoint_id = str(envelope.get("checkpoint_id") or "")
            meta["partial"] = bool(envelope.get("partial"))
            meta["mode"] = "delegate"
            if envelope.get("changed_files"):
                meta["changed_files"] = list(envelope["changed_files"])
            if envelope.get("error"):
                meta["agent_error"] = envelope["error"]
        else:
            text, success, steps, checkpoint_id, activity, produced, run_meta = (
                await _run_standalone_stream(
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
            )
            meta.update(run_meta)
            meta["mode"] = "standalone"
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "agent_node_error", agent=agent_name, error=str(exc), exc_info=True
        )
        return NodeOutput(
            error=str(exc),
            metadata={"node_id": hidden.unique_id, "agent": agent_name},
        )

    state = hidden.workflow_state
    if state is not None and output_var:
        state.set(output_var, text)
    if state is not None and checkpoint_id:
        # Stash the kernel checkpoint id so the executor can pause/resume
        # this agent turn (consumed by the resume path).
        try:
            state.metadata.setdefault("agent_checkpoints", {})[
                str(hidden.unique_id)
            ] = checkpoint_id
        except Exception:  # noqa: BLE001
            pass

    return NodeOutput(
        values=(text, success, steps, checkpoint_id, activity, produced),
        metadata=meta,
    )


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
) -> tuple[str, bool, int, str, list[Any], list[Any], dict[str, Any]]:
    """Drive ``runtime.stream`` standalone and aggregate node outputs."""
    definition = runtime.resolve(agent_name)
    if max_turns:
        definition = definition.with_overrides(max_turns=max_turns)
    if allowed_tools is not None:
        definition = definition.with_overrides(
            tools=definition.tools.model_copy(update={"allow": allowed_tools})
        )

    text_parts: list[str] = []
    final_text = ""
    tool_calls = 0
    produced: list[Any] = []
    activity: list[dict[str, Any]] = []
    checkpoint_id = ""
    reason = "completed"
    error: str | None = None

    async for event in runtime.stream(
        definition,
        prompt,
        session_id=_as_uuid(hidden.session_id),
        user_id=_as_uuid(hidden.user_id),
        cwd=cwd or ".",
        tool_extra=tool_extra,
    ):
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
            tool_calls += 1
            name = str(data.get("name") or data.get("tool") or "tool")
            activity.append({"type": "tool_use", "name": name})
            emit({"type": "tool_use", "name": name})
        elif etype == AgentEventType.TOOL_RESULT:
            name = str(data.get("name") or data.get("tool") or "tool")
            activity.append({"type": "tool_result", "name": name})
        elif etype == AgentEventType.WORKSPACE_ATTACHMENTS:
            for path in data.get("paths") or []:
                if path:
                    produced.append(str(path))
        elif etype == AgentEventType.RESULT:
            reason = str(data.get("reason") or "completed")
            error = data.get("error")
            checkpoint_id = str(data.get("checkpoint_id") or "")

    text = final_text or "".join(text_parts)
    success = error is None and reason in ("completed", "awaiting_user_input")
    run_meta = {
        "reason": reason,
        "partial": reason not in ("completed", ""),
    }
    if error:
        run_meta["agent_error"] = error
    return text, success, tool_calls, checkpoint_id, activity, produced, run_meta


__all__ = ["run_agent_node", "AGENT_OUTPUT_NAMES"]
