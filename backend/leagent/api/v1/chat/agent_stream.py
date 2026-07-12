"""Bridge ``AgentController.run_stream`` events into typed SSE tuples.

:func:`run_agent_stream` is the single adapter between the agent's event stream
and the chat endpoints: it enforces the per-conversation timeout, derives
``task_progress`` events from ``todo_write`` tool activity, and re-emits workflow
embeds. It yields ``(event_type, event_data, accumulated_text)`` triples that the
route handlers serialize via :mod:`leagent.api.v1.chat.sse`.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


# Monotonic rank used to suppress out-of-order todo status regressions in the
# derived task-progress stream (a task never moves backwards).
TASK_STATUS_RANK: dict[str, int] = {
    "pending": 0,
    "in_progress": 1,
    "completed": 2,
    "failed": 2,
    "cancelled": 2,
}


async def run_agent_stream(
    agent: Any,
    message: str,
    session_id: UUID,
    user_id: UUID,
    *,
    attachments: list[str] | None = None,
    project_roots: list[str] | None = None,
    authorized_roots: list[str] | None = None,
    skip_append_user: bool = False,
    persisted_user_message_id: UUID | None = None,
    conversation_timeout_sec: int = 600,
    agent_task_id: UUID | None = None,
    runtime_profile: str | None = None,
    checkpoint_id: str | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any], str]]:
    """Iterate agent events. Yields ``(event_type, event_data, accumulated_text)``."""
    response_content = ""
    todo_status_by_id: dict[str, str] = {}
    todo_order_by_id: dict[str, int] = {}
    _stream_start = time.monotonic()

    from leagent.runtime.execution_factory import (
        attach_run_id,
        begin_execution,
        end_execution_unless_blocked,
    )
    from leagent.runtime.execution_run import ExecutionScope

    exec_run = begin_execution(
        scope=ExecutionScope.CHAT_TURN,
        session_id=str(session_id),
        user_id=str(user_id),
    )

    def _normalize_task_status(raw: str | None) -> str:
        value = (raw or "").strip().lower()
        if value in {"in_progress", "running"}:
            return "in_progress"
        if value in {"completed", "success", "done"}:
            return "completed"
        if value in {"failed", "error"}:
            return "failed"
        if value in {"cancelled", "canceled"}:
            return "cancelled"
        return "pending"

    def _extract_todo_items_from_tool_result(data: dict[str, Any]) -> list[dict[str, Any]]:
        payload_data = data.get("data")
        if isinstance(payload_data, dict) and isinstance(payload_data.get("todos"), list):
            return [item for item in payload_data["todos"] if isinstance(item, dict)]
        raw_content = data.get("content")
        if isinstance(raw_content, str) and raw_content.strip():
            try:
                parsed = json.loads(raw_content)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and isinstance(parsed.get("todos"), list):
                return [item for item in parsed["todos"] if isinstance(item, dict)]
        return []

    def _session_todos_snapshot(data: dict[str, Any]) -> dict[str, Any] | None:
        if data.get("name") != "todo_write":
            return None
        todo_items = _extract_todo_items_from_tool_result(data)
        if not todo_items:
            return None
        todos: list[dict[str, Any]] = []
        for index, item in enumerate(todo_items):
            task_id = str(item.get("id") or "").strip() or f"todo-{index}"
            todos.append({
                "id": task_id,
                "content": str(item.get("content") or task_id),
                "status": _normalize_task_status(item.get("status")),
                "order": index,
            })
        return {"todos": todos}

    def _next_progress_events(event_type: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        if event_type == "tool_call" and data.get("name") == "todo_write":
            return []
        if event_type != "tool_result" or data.get("name") != "todo_write":
            return []

        todo_items = _extract_todo_items_from_tool_result(data)

        progress_events: list[dict[str, Any]] = []
        for index, item in enumerate(todo_items):
            task_id = str(item.get("id") or "").strip() or f"todo-{index}"
            label = str(item.get("content") or task_id)
            status = _normalize_task_status(item.get("status"))
            prev_status = todo_status_by_id.get(task_id)
            if prev_status is not None:
                if TASK_STATUS_RANK[status] < TASK_STATUS_RANK[prev_status]:
                    continue
                if status == prev_status:
                    continue
            todo_status_by_id[task_id] = status
            order = todo_order_by_id.setdefault(task_id, len(todo_order_by_id))
            progress_events.append({
                "task_id": task_id,
                "label": label,
                "status": status,
                "order": order,
            })
        return progress_events

    yield (
        "execution_started",
        {
            "run_id": exec_run.run_id,
            "session_id": str(session_id),
            "scope": ExecutionScope.CHAT_TURN.value,
        },
        response_content,
    )

    try:
        async for event in agent.run_stream(
            message,
            session_id,
            user_id=user_id,
            attachments=attachments,
            project_roots=project_roots,
            authorized_roots=authorized_roots,
            skip_append_user=skip_append_user,
            persisted_user_message_id=persisted_user_message_id,
            agent_task_id=agent_task_id,
            execution_run_id=exec_run.run_id,
            runtime_profile=runtime_profile,
            checkpoint_id=checkpoint_id,
        ):
            elapsed = time.monotonic() - _stream_start
            if elapsed > conversation_timeout_sec:
                logger.warning(
                    "conversation_timeout",
                    session_id=str(session_id),
                    elapsed_sec=int(elapsed),
                    limit_sec=conversation_timeout_sec,
                )
                if hasattr(agent, "abort"):
                    agent.abort()
                yield (
                    "error",
                    attach_run_id(
                        {"error": f"Conversation exceeded {conversation_timeout_sec}s time limit"},
                        exec_run.run_id,
                    ),
                    response_content,
                )
                return
            if event.type == "token":
                token = event.data.get("token", "")
                response_content += token
                yield event.type, attach_run_id(event.data, exec_run.run_id), response_content
            elif event.type == "complete":
                if not response_content:
                    response_content = event.data.get("text", "")
                try:
                    from leagent.main import get_service_manager
                    from leagent.services.event.manager import EventType

                    sm = get_service_manager()
                    event_manager = getattr(sm, "event", None)
                    if event_manager is not None:
                        await event_manager.publish_agent_lifecycle(
                            EventType.AGENT_MESSAGE,
                            session_id=str(session_id),
                            run_id=exec_run.run_id,
                            data={
                                "reason": event.data.get("reason"),
                                "text_len": len(response_content),
                            },
                        )
                except Exception:
                    pass
                yield event.type, attach_run_id(event.data, exec_run.run_id), response_content
            elif event.type in (
                "thinking",
                "tool_call",
                "tool_call_delta",
                "tool_result",
                "error",
                "workspace_attachments",
                "user_input_request",
                "nested_agent_preview",
            ):
                yield event.type, attach_run_id(event.data, exec_run.run_id), response_content
                for progress_event in _next_progress_events(event.type, event.data):
                    progress_event["run_id"] = exec_run.run_id
                    yield "task_progress", progress_event, response_content
                if event.type == "tool_result":
                    snapshot = _session_todos_snapshot(event.data)
                    if snapshot is not None:
                        snapshot["run_id"] = exec_run.run_id
                        yield "session_todos", snapshot, response_content
                if event.type == "tool_result" and event.data.get("success"):
                    inner = event.data.get("data")
                    tname = event.data.get("name")
                    if tname == "chat_workflow_emit" and isinstance(inner, dict) and inner.get("workflow"):
                        yield (
                            "workflow",
                            {
                                "spec": inner["workflow"],
                                "digest": inner.get("digest"),
                                "partial": False,
                                "run_id": exec_run.run_id,
                            },
                            response_content,
                        )
                    elif tname == "chat_workflow_embed_emit" and isinstance(inner, dict) and inner.get("flow_data"):
                        yield (
                            "workflow",
                            {
                                "embed": {
                                    "data": inner["flow_data"],
                                    "digest": inner.get("digest"),
                                    "title": inner.get("title"),
                                    "summary": inner.get("summary"),
                                    "flow_id": inner.get("flow_id"),
                                },
                                "partial": False,
                                "run_id": exec_run.run_id,
                            },
                            response_content,
                        )
    except asyncio.CancelledError:
        logger.warning("agent_stream_cancelled session_id=%s", session_id)
        yield "error", {"error": "Stream cancelled", "run_id": exec_run.run_id}, response_content
    except Exception as exc:
        logger.exception("agent_stream_error session_id=%s", session_id)
        yield "error", {"error": str(exc), "run_id": exec_run.run_id}, response_content
    finally:
        end_execution_unless_blocked(exec_run.run_id)
