"""``TaskHandler`` that runs a prompt through the :class:`QueryEngine`.

The ``AGENT`` task type is the default path for "run this natural
language prompt and stream the agent's work to the task output log".
This implementation is intentionally pluggable so sites can swap it for
a legacy :class:`AgentController` based handler via
:func:`leagent.tasks.registration.register_task_handler_builder`.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.agent.runtime_profile import resolve_runtime_budget
from leagent.db.models.task import (
    Task,
    TaskContext,
    TaskType,
)
from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from leagent.services.service_manager import ServiceManager

logger = get_logger(__name__)


class AgentTaskHandler:
    """Run an agent query via :class:`QueryEngine` and stream into the log."""

    name = "agent_task_handler"
    task_type: TaskType = TaskType.AGENT

    def __init__(self, *, service_manager: "ServiceManager | None" = None) -> None:
        self._sm = service_manager

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: "AsyncSession",
    ) -> dict[str, Any]:
        from leagent.config.settings import get_settings
        from leagent.sdk import AgentDefinition, AgentRuntime, MemoryPolicy
        from leagent.tools.executor import ToolExecutor
        from leagent.tools.registry import get_registry

        sm = self._sm
        prompt = _extract_prompt(params)
        if not prompt:
            raise ValueError("Agent task requires a 'prompt' or 'query' in input_data")

        llm = getattr(sm, "llm_service", None) if sm is not None else None
        if llm is None:
            raise RuntimeError("LLMService unavailable — agent task cannot run")

        tool_registry = get_registry()
        settings = get_settings()
        budget = resolve_runtime_budget(params.get("runtime_profile"), settings=settings)
        executor = ToolExecutor(
            registry=tool_registry,
            service_manager=sm,
            default_timeout=float(budget.tool_timeout_sec),
        )

        # ``system_prompt`` here is treated as an L0 persona override; when
        # empty the QueryEngine's prompt builder falls back to the named
        # variant (``default_agent`` by default, or the explicit
        # ``prompt_variant`` param for specialised task flows).
        system_prompt = params.get("system_prompt") or ""
        prompt_variant = params.get("prompt_variant") or "default_agent"
        max_turns = _int_param(params, "max_turns", budget.max_turns)
        max_tool_calls = _int_param(
            params,
            "max_tool_calls_per_turn",
            budget.max_tool_calls_per_turn,
        )
        user_id = _uuid_param(params.get("user_id"))
        session_id = _uuid_param(params.get("session_id"))
        project_roots = _str_list_param(params.get("project_roots"))
        authorized_roots = _str_list_param(params.get("authorized_roots"))
        cwd = project_roots[0] if project_roots else "."
        tool_extra: dict[str, Any] = {
            "runtime_profile": budget.name,
            "runtime_budget": {
                "task_timeout_sec": budget.task_timeout_sec,
                "tool_timeout_sec": budget.tool_timeout_sec,
                "code_execution_default_timeout_sec": budget.code_execution_default_timeout_sec,
                "code_execution_max_timeout_sec": budget.code_execution_max_timeout_sec,
            },
        }
        if project_roots:
            tool_extra["project_roots"] = project_roots
        if authorized_roots:
            tool_extra["authorized_roots"] = authorized_roots

        from leagent.runtime.execution_registry import get_execution_run_registry
        from leagent.runtime.execution_run import ExecutionRun, ExecutionScope
        from leagent.services.event.manager import EventType

        exec_run = get_execution_run_registry().register(
            ExecutionRun(
                scope=ExecutionScope.TASK,
                task_id=task_ctx.task_id,
                session_id=str(session_id) if session_id else None,
                user_id=str(user_id) if user_id else None,
            )
        )
        tool_extra["run_id"] = exec_run.run_id

        task_uuid = _uuid_param(params.get("__task_db_id"))
        event_manager = getattr(sm, "event", None) if sm is not None else None
        if event_manager is not None and task_uuid is not None:
            try:
                await event_manager.emit_task_event(
                    EventType.TASK_STARTED,
                    task_uuid,
                    "agent_task_handler",
                    task_name=prompt_variant,
                    data={"run_id": exec_run.run_id, "prompt_preview": prompt[:200]},
                )
            except Exception:
                logger.debug("agent_task_event_start_failed", exc_info=True)

        task_ctx.append_output(
            json.dumps(
                {
                    "event": "task_start",
                    "task_id": task_ctx.task_id,
                    "runtime_profile": budget.name,
                    "prompt": prompt[:2000],
                }
            )
            + "\n"
        )

        # Drive the run through the SDK kernel (run_loop) via AgentRuntime.stream
        # so background tasks share checkpoint/hook semantics with chat SSE.
        runtime = AgentRuntime.from_service_manager(sm, executor=executor)
        definition = AgentDefinition(
            name=prompt_variant,
            prompt_variant=prompt_variant,
            system_prompt=system_prompt,
            runtime_profile=budget.name,
            max_turns=max_turns,
            max_tool_calls_per_turn=max_tool_calls,
            memory=MemoryPolicy(enabled=False, formation=False),
        )

        final_text = ""
        final_usage: dict[str, Any] = {}
        tool_calls = 0
        last_progress_write = 0.0

        async for event in runtime.stream(
            definition,
            prompt,
            session_id=session_id,
            user_id=user_id,
            cwd=cwd,
            tool_extra=tool_extra,
            abort_event=task_ctx.abort_event,
        ):
            if task_ctx.is_aborted:
                break
            payload = {"type": event.type, **event.data}
            # Keep individual log lines modest; full transcripts are
            # reconstructable from the DB/memory systems.
            try:
                task_ctx.append_output(json.dumps(payload, default=str) + "\n")
            except Exception:
                logger.debug("append_output failed", exc_info=True)

            if event.type == "stream_delta":
                final_text += event.data.get("content", "") or ""
            elif event.type == "assistant":
                content = event.data.get("content") or ""
                if content:
                    final_text = content
            elif event.type == "tool_use":
                tool_calls += 1
            elif event.type == "result":
                final_usage = event.data.get("usage", {}) or {}
            now = time.monotonic()
            msg_type = event.type
            if msg_type != "stream_delta" or now - last_progress_write >= 10:
                last_progress_write = now
                await _update_task_progress(
                    session,
                    params.get("__task_db_id"),
                    progress=min(95, max(1, tool_calls * 5)),
                    message=_progress_message(msg_type, tool_calls),
                    output_offset=task_ctx.output_offset,
                )

        task_ctx.append_output(
            json.dumps(
                {
                    "event": "task_complete" if not task_ctx.is_aborted else "task_cancelled",
                    "task_id": task_ctx.task_id,
                    "tool_calls": tool_calls,
                    "run_id": exec_run.run_id,
                },
                default=str,
            )
            + "\n"
        )
        if event_manager is not None and task_uuid is not None:
            try:
                await event_manager.emit_task_event(
                    EventType.TASK_CANCELLED if task_ctx.is_aborted else EventType.TASK_COMPLETED,
                    task_uuid,
                    "agent_task_handler",
                    task_name=prompt_variant,
                    data={
                        "run_id": exec_run.run_id,
                        "tool_calls": tool_calls,
                        "usage": final_usage,
                    },
                )
            except Exception:
                logger.debug("agent_task_event_complete_failed", exc_info=True)
        get_execution_run_registry().remove(exec_run.run_id)
        return {
            "text": final_text,
            "tool_calls": tool_calls,
            "usage": final_usage,
            "runtime_profile": budget.name,
        }

    async def kill(self, task_id: str, session: "AsyncSession") -> None:
        # Abort propagation is handled by ``TaskManager.kill_task`` which
        # sets the context abort event; nothing extra to do here.
        return None


def _extract_prompt(params: dict[str, Any]) -> str:
    for key in ("prompt", "query", "input", "message"):
        v = params.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _int_param(params: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(params.get(key) or default)
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _uuid_param(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _str_list_param(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, str) and v.strip()]


def _progress_message(msg_type: str, tool_calls: int) -> str:
    if msg_type == "tool_use":
        return f"Running tool call {tool_calls}"
    if msg_type == "tool_result":
        return f"Processed tool result {tool_calls}"
    if msg_type == "assistant":
        return "Assistant response updated"
    if msg_type == "result":
        return "Finalising agent run"
    return "Agent is working"


async def _update_task_progress(
    session: "AsyncSession",
    task_id: Any,
    *,
    progress: int,
    message: str,
    output_offset: int,
) -> None:
    task_uuid = _uuid_param(task_id)
    if task_uuid is None:
        return
    try:
        task = await session.get(Task, task_uuid)
        if task is None:
            return
        task.progress = max(task.progress, min(99, progress))
        task.progress_message = message[:500]
        task.output_offset = output_offset
        session.add(task)
        await session.flush()
    except Exception:
        logger.debug("agent_task_progress_update_failed", exc_info=True)
