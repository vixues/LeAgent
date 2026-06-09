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
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)


# Monotonic rank used to suppress out-of-order todo status regressions in the
# derived task-progress stream (a task never moves backwards).
TASK_STATUS_RANK: dict[str, int] = {
    "pending": 0,
    "in_progress": 1,
    "completed": 2,
    "failed": 2,
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
) -> AsyncIterator[tuple[str, dict[str, Any], str]]:
    """Iterate agent events. Yields ``(event_type, event_data, accumulated_text)``."""
    response_content = ""
    todo_status_by_id: dict[str, str] = {}
    todo_order_by_id: dict[str, int] = {}
    _stream_start = time.monotonic()

    def _normalize_task_status(raw: str | None) -> str:
        value = (raw or "").strip().lower()
        if value in {"in_progress", "running"}:
            return "in_progress"
        if value in {"completed", "success", "done"}:
            return "completed"
        if value in {"failed", "error"}:
            return "failed"
        return "pending"

    def _next_progress_events(event_type: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        if event_type == "tool_call" and data.get("name") == "todo_write":
            return [{
                "task_id": data.get("id") or f"todo-write-{uuid4().hex}",
                "label": "Updating task list",
                "status": "in_progress",
            }]
        if event_type != "tool_result" or data.get("name") != "todo_write":
            return []

        payload_data = data.get("data")
        todo_items: list[dict[str, Any]] = []
        if isinstance(payload_data, dict) and isinstance(payload_data.get("todos"), list):
            todo_items = [item for item in payload_data["todos"] if isinstance(item, dict)]
        else:
            raw_content = data.get("content")
            if isinstance(raw_content, str) and raw_content.strip():
                try:
                    parsed = json.loads(raw_content)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, dict) and isinstance(parsed.get("todos"), list):
                    todo_items = [item for item in parsed["todos"] if isinstance(item, dict)]

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
                    {"error": f"Conversation exceeded {conversation_timeout_sec}s time limit"},
                    response_content,
                )
                return
            if event.type == "token":
                token = event.data.get("token", "")
                response_content += token
                yield event.type, event.data, response_content
            elif event.type == "complete":
                if not response_content:
                    response_content = event.data.get("text", "")
                yield event.type, event.data, response_content
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
                yield event.type, event.data, response_content
                for progress_event in _next_progress_events(event.type, event.data):
                    yield "task_progress", progress_event, response_content
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
                            },
                            response_content,
                        )
    except asyncio.CancelledError:
        logger.warning("agent_stream_cancelled session_id=%s", session_id)
        yield "error", {"error": "Stream cancelled"}, response_content
    except Exception as exc:
        logger.exception("agent_stream_error session_id=%s", session_id)
        yield "error", {"error": str(exc)}, response_content
