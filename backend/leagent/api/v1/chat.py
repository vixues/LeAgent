"""Chat API endpoints with SSE streaming and WebSocket support.

All persistence flows through :class:`ChatService` — endpoints never
open raw DB sessions for chat tables.  Agent orchestration uses
:func:`build_agent_controller` from ``chat_deps``.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import AsyncIterator  # noqa: TC003
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID, uuid4

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sse_starlette.sse import EventSourceResponse

from leagent.api.v1.chat_deps import ChatSvc, build_agent_controller
from leagent.apps.gateway.infrastructure.ws_fanout import (
    DistributedConnectionManager,
)
from leagent.schema.api import PaginatedResponse
from leagent.services.auth import CurrentUserId  # noqa: TC001
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.chat.service import ChatService
from leagent.services.database.models.message import (
    MessageRead,
    MessageRole,
    SessionCreate,
    SessionRead,
    chat_session_to_read,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


def _tokens_from_stream_usage(token_usage: dict[str, Any] | None) -> tuple[int | None, int | None]:
    """Extract persisted DB token columns from agent ``token_usage`` (SSE / completion metadata)."""
    if not isinstance(token_usage, dict) or not token_usage:
        return None, None

    def _as_int(v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return _as_int(token_usage.get("prompt_tokens")), _as_int(token_usage.get("completion_tokens"))


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------


class ChatCompletionMessage(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="default", description="Model to use for completion")
    messages: list[ChatCompletionMessage]
    session_id: UUID | None = None
    stream: bool = Field(default=True, description="Whether to stream the response")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionMessage
    finish_reason: str | None = None


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


class SessionAttachmentsResponse(BaseModel):
    """Session-scoped files (user uploads and agent-registered outputs)."""

    session_id: UUID
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class AuthorizedPathEntry(BaseModel):
    """One user-granted directory for tool filesystem access in this chat session."""

    path: str
    label: str | None = None


class AuthorizedPathsResponse(BaseModel):
    session_id: UUID
    paths: list[AuthorizedPathEntry] = Field(default_factory=list)


class AuthorizedPathCreateBody(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)
    label: str | None = Field(default=None, max_length=200)


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[dict[str, Any]]


class SendMessageRequest(BaseModel):
    """User turn: non-empty text and/or persisted attachment ids."""

    content: str = Field(default="", max_length=100000)
    role: MessageRole = MessageRole.USER
    stream: bool = True
    model: str | None = None
    attachments: list[str] | None = None

    @model_validator(mode="after")
    def require_text_or_attachments(self) -> SendMessageRequest:
        text = (self.content or "").strip()
        has_att = bool(self.attachments)
        if not text and not has_att:
            raise ValueError("content cannot be empty unless attachments are provided")
        return self


class SessionUpdateRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    metadata_patch: dict[str, Any] | None = Field(
        default=None,
        description="Shallow-merged into chat_sessions.session_metadata (merge_session_metadata).",
    )


class ChatWorkflowStepRunRequest(BaseModel):
    """Run one step from a persisted chat workflow card."""

    message_id: UUID
    workflow_digest: str = Field(..., min_length=16, max_length=128)
    user_input: str = Field(default="", max_length=50_000)


class ChatWorkflowTemplateRead(BaseModel):
    """Built-in chat workflow card for demos and regression testing."""

    id: str
    title: str
    description: str = ""
    spec: dict[str, Any]
    digest: str


class MaterializedTemplateRow(BaseModel):
    template_id: str
    message_id: UUID


class MaterializeWorkflowTemplatesResponse(BaseModel):
    session_id: UUID
    templates: list[MaterializedTemplateRow]


class AgentMemoryEpisodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    user_id: str | None = None
    summary: str
    tags: list[str] = Field(default_factory=list)
    importance: float = 0.0
    token_count: int | None = None
    recall_count: int = 0
    last_recalled_at: datetime | None = None
    created_at: datetime | None = None


class AgentMemoryFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    value: str
    confidence: float = 0.8
    source: str | None = None
    workspace_id: str | None = None
    created_at: datetime | None = None


class AgentMemoryProcedureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    signature: str
    description: str
    run_count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    last_outcome: str | None = None
    last_run_at: datetime | None = None
    created_at: datetime | None = None


class AgentMemorySnapshotRead(BaseModel):
    enabled: bool
    episodes: list[AgentMemoryEpisodeRead]
    facts: list[AgentMemoryFactRead]
    procedures: list[AgentMemoryProcedureRead]


class PromptLayerRead(BaseModel):
    name: str
    body: str
    tokens: int = 0
    truncated: bool = False


class PromptPreviewRead(BaseModel):
    """On-demand assembled system prompt (debug / inspector)."""

    query_used: str
    system_text: str
    total_chars: int
    stable_hash: str
    full_hash: str
    variant_key: str
    layers: list[PromptLayerRead]
    approx_transcript_tokens: int = 0
    approx_context_tokens: int = 0


class StreamEvent(BaseModel):
    event: str
    data: dict[str, Any]


TASK_STATUS_RANK: dict[str, int] = {
    "pending": 0,
    "in_progress": 1,
    "completed": 2,
    "failed": 2,
}


# ---------------------------------------------------------------------------
# Shared agent-event helpers
# ---------------------------------------------------------------------------


def _format_openai_chunk(
    completion_id: str, created: int, model: str, delta: dict[str, Any], finish_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "event": "message",
        "data": json.dumps({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }),
    }


def _format_frontend_event(event_type: str, data: Any) -> dict[str, Any]:
    return {
        "event": "message",
        "data": json.dumps({"type": event_type, "data": data}),
    }


def _companion_sse_events(etype: str, edata: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Extra frontend SSE events derived from tool results (canvas / generative UI)."""
    out: list[tuple[str, dict[str, Any]]] = []
    if etype != "tool_result" or not isinstance(edata, dict):
        return out

    td_any = edata.get("data")
    if isinstance(td_any, dict):
        _artifact_id = td_any.get("artifact_id")
        if _artifact_id:
            artifact_payload: dict[str, Any] = {
                "artifact_id": str(_artifact_id),
                "origin_tool": str(edata.get("name") or ""),
                "syntax_valid": td_any.get("syntax_valid"),
                "kind": td_any.get("kind"),
                "language": td_any.get("language"),
                "target_path": td_any.get("target_path"),
                "diagnostics": td_any.get("syntax_diagnostics"),
                "source_length": td_any.get("source_length"),
                "error_type": td_any.get("error_type"),
            }
            artifact_payload = {k: v for k, v in artifact_payload.items() if v is not None}
            out.append(("code_artifact", artifact_payload))

    if not edata.get("success"):
        return out
    name = str(edata.get("name") or "")
    td = edata.get("data")
    if not isinstance(td, dict):
        return out
    tool_call_id = str(edata.get("tool_call_id") or "")
    if name == "canvas_publish" and td.get("preview_path"):
        cid = str(td.get("canvas_id", ""))
        rev = int(td.get("revision") or 0)
        out.append(
            (
                "canvas",
                {
                    "id": f"{cid}-{rev}" if cid and rev else str(uuid4()),
                    "title": str(td.get("title") or "Canvas"),
                    "type": "html",
                    "preview_path": str(td["preview_path"]),
                    "canvas_id": cid,
                    "revision": rev,
                    "content_type": str(td.get("content_type") or "html"),
                    "trust": str(td.get("trust") or "hosted"),
                    "open_in_panel": bool(td.get("open_in_panel", True)),
                    **({"tool_call_id": tool_call_id} if tool_call_id else {}),
                },
            )
        )
    if name == "emit_ui_tree" and isinstance(td.get("payload"), dict):
        payload = dict(td["payload"])
        if tool_call_id:
            payload["tool_call_id"] = tool_call_id
        out.append(("ui_tree", payload))
    if name == "emit_ui_patch" and isinstance(td.get("payload"), dict):
        patch_payload = dict(td["payload"])
        if tool_call_id:
            patch_payload["tool_call_id"] = tool_call_id
        out.append(("ui_patch", patch_payload))
    if name == "emit_pet_bubble":
        text = str(td.get("text") or "").strip()
        if text:
            bubble: dict[str, Any] = {"text": text[:120]}
            em = td.get("emoji")
            if em is not None:
                es = str(em).strip()
                if es:
                    bubble["emoji"] = es[:16]
            out.append(("pet_bubble", bubble))

    return out


def _openai_tool_call_from_stream_edata(edata: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize SSE ``tool_call`` payload to OpenAI-shaped dict for ``Message.tool_calls`` JSON."""
    tid = str(edata.get("id") or "").strip()
    if not tid:
        return None
    name = str(edata.get("name") or "")
    args = edata.get("arguments", {})
    if isinstance(args, dict):
        arg_str = json.dumps(args, ensure_ascii=False)
    else:
        arg_str = str(args or "")
    return {
        "id": tid,
        "type": "function",
        "function": {"name": name, "arguments": arg_str},
    }


def _merge_message_extensions_json(
    workflow_json: str | None,
    *,
    thinking: str | None = None,
    task_progress: list[dict[str, Any]] | None = None,
    gen_ui: dict[str, Any] | None = None,
    pet_bubble: dict[str, Any] | None = None,
) -> str | None:
    """Merge workflow/embed JSON with UI replay fields (thinking, task_progress, gen_ui, pet_bubble)."""
    merged: dict[str, Any] = {}
    if workflow_json:
        try:
            parsed = json.loads(workflow_json)
            if isinstance(parsed, dict):
                merged.update(parsed)
        except (json.JSONDecodeError, TypeError):
            pass
    if thinking and str(thinking).strip():
        merged["thinking"] = str(thinking).strip()
    if task_progress:
        merged["task_progress"] = task_progress
    if gen_ui:
        merged["gen_ui"] = gen_ui
    if pet_bubble:
        merged["pet_bubble"] = pet_bubble
    return json.dumps(merged, ensure_ascii=False) if merged else None


def _merge_stream_thinking_for_persist(prev: str | None, raw_thought: str) -> str | None:
    """Fold successive ``thinking`` stream fragments for DB persistence.

    Cumulative fragments (each new string starts with the previous full text)
    replace the stored value; discrete fragments append with newlines.
    """
    if not isinstance(raw_thought, str) or not raw_thought.strip():
        return prev
    t = raw_thought.strip()
    base = (prev or "").strip()
    if not base:
        return t
    if t.startswith(base):
        return t
    return f"{base}\n{t}"


def _parse_tool_replies_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        tid = item.get("tool_call_id") or item.get("tool_use_id") or item.get("id")
        content = item.get("content")
        if tid is not None and content is not None:
            out.append({"tool_call_id": str(tid), "content": str(content)})
    return out


async def _run_agent_stream(
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


# ---------------------------------------------------------------------------
# File attachment helpers
# ---------------------------------------------------------------------------


async def _attach_chat_files(
    user_id: UUID,
    session_id: UUID,
    files: list[UploadFile],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
    """Persist uploads via :class:`SessionManager.attach_files`."""
    from leagent.main import get_service_manager

    attachments_out: list[dict[str, Any]] = []
    stored_paths: list[str] = []
    errors: list[dict[str, str]] = []

    if not files:
        return attachments_out, stored_paths, errors

    try:
        sm = get_service_manager()
    except Exception:  # noqa: BLE001
        sm = None

    if sm is None or sm.session_manager is None:
        for upload in files:
            errors.append({
                "file": upload.filename or "unnamed",
                "error": "Session manager unavailable; file rejected",
            })
        return attachments_out, stored_paths, errors

    try:
        persisted = await sm.session_manager.attach_files(
            session_id, files, user_id=user_id,
        )
    except ValueError as exc:
        errors.append({"file": "(batch)", "error": str(exc)})
        return attachments_out, stored_paths, errors
    except Exception as exc:  # noqa: BLE001
        logger.warning("session_attach_files_failed: %s", exc)
        errors.append({"file": "(batch)", "error": str(exc)})
        return attachments_out, stored_paths, errors

    for att in persisted:
        if att.storage_path:
            stored_paths.append(att.storage_path)
        row: dict[str, Any] = {
            "id": str(att.id),
            "filename": att.filename,
            "kind": att.kind,
            "content_type": att.content_type,
            "size": att.size,
            "preview_url": att.preview_url,
            "download_url": att.download_url,
        }
        lp = _attachment_local_path_for_sse(att.storage_path)
        if lp:
            row["local_path"] = lp
        attachments_out.append(row)
    return attachments_out, stored_paths, errors


async def _resolve_folder_context(
    user_id: UUID,
    db: DatabaseService,
    folder_id: str | None = None,
    file_ids_csv: str | None = None,
) -> list[tuple[str, str, str | None]]:
    """Fetch File rows by folder_id / explicit file_ids (user-scoped)."""
    from sqlmodel import select as sel

    from leagent.services.database.models.file import File as FileModel

    results: list[tuple[str, str, str | None]] = []
    raw_ids: list[UUID] = []
    if file_ids_csv:
        for part in file_ids_csv.split(","):
            part = part.strip()
            if part:
                with suppress(ValueError):
                    raw_ids.append(UUID(part))

    async with db.session() as session:
        if folder_id:
            try:
                fid = UUID(folder_id)
            except ValueError:
                fid = None
            if fid:
                stmt = sel(FileModel).where(
                    FileModel.folder_id == fid,
                    FileModel.user_id == user_id,
                    FileModel.is_deleted == False,  # noqa: E712
                )
                rows = (await session.exec(stmt)).all()
                for f in rows:
                    preview = (f.extracted_text or "")[:1500] if f.extracted_text else None
                    results.append((f.storage_path, f.original_name, preview))

        if raw_ids:
            stmt = sel(FileModel).where(
                FileModel.id.in_(raw_ids),
                FileModel.user_id == user_id,
                FileModel.is_deleted == False,  # noqa: E712
            )
            rows = (await session.exec(stmt)).all()
            for f in rows:
                preview = (f.extracted_text or "")[:1500] if f.extracted_text else None
                results.append((f.storage_path, f.original_name, preview))

    return results


def _context_item_paths(
    context_items: list[tuple[str, str, str | None]],
) -> list[str]:
    return [path for path, _name, _preview in context_items]


async def _resolve_folder_context_note(
    user_id: UUID,
    db: DatabaseService,
    folder_id: str | None,
    *,
    attached_file_count: int,
) -> str | None:
    """Return a short prompt note naming the selected UI folder."""
    if not folder_id or not str(folder_id).strip():
        return None
    try:
        fid = UUID(str(folder_id))
    except ValueError:
        return None

    from sqlmodel import select

    from leagent.services.database.models import Folder

    async with db.session() as session:
        folder = (
            await session.exec(
                select(Folder).where(
                    Folder.id == fid,
                    Folder.user_id == user_id,
                    Folder.is_deleted == False,  # noqa: E712
                ),
            )
        ).first()
        if not folder:
            return None

        names = [folder.name]
        parent_id = folder.parent_id
        seen = {folder.id}
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            parent = (
                await session.exec(
                    select(Folder).where(
                        Folder.id == parent_id,
                        Folder.user_id == user_id,
                        Folder.is_deleted == False,  # noqa: E712
                    ),
                )
            ).first()
            if not parent:
                break
            names.insert(0, parent.name)
            parent_id = parent.parent_id

    folder_path = " / ".join(name for name in names if name)
    lines = [
        "\n\nSelected folder context:",
        f"- Folder: {folder_path or str(fid)}",
        f"- Folder ID: {fid}",
        f"- Attached files from this folder: {attached_file_count}",
        "When the user says \"this folder\", interpret it as this selected folder.",
    ]
    return "\n".join(lines)


async def _resolve_project_folder_path(
    user_id: UUID,
    db: DatabaseService,
    project_folder_id: str | None,
) -> str | None:
    """Resolve a folder id to its on-disk ``project_path`` (or None).

    Returns ``None`` silently when the id is empty / malformed, the
    folder doesn't exist, the caller doesn't own it, or project mode
    is off — chat should not 4xx for an invalid project pointer; the
    LLM just runs without project context and tools will refuse on
    their own if asked to touch a forbidden path.
    """
    if not project_folder_id or not str(project_folder_id).strip():
        return None
    try:
        fid = UUID(str(project_folder_id))
    except ValueError:
        return None

    from leagent.services.database.models import Folder
    from leagent.services.database.sqlite_compat import load_entity_by_id
    from leagent.services.coding_projects import (
        ProjectPathSafetyError,
        resolve_owned_project_folder,
    )

    async with db.session() as session:
        folder = await load_entity_by_id(session, Folder, fid, parent_table="folders")
        if not folder or folder.is_deleted or folder.user_id != user_id:
            return None
        try:
            resolved = resolve_owned_project_folder(folder, user_id)
        except ProjectPathSafetyError as exc:
            logger.info(
                "chat_project_folder_rejected",
                folder_id=str(fid),
                error=str(exc),
            )
            return None
    return str(resolved)


def _dedupe_resolved_paths(paths: list[str]) -> list[str]:
    """Return de-duplicated absolute paths while preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not raw:
            continue
        try:
            resolved = str(Path(raw).expanduser().resolve())
        except Exception:  # noqa: BLE001
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def _attachment_local_path_for_sse(storage_path: str | None) -> str | None:
    """Absolute path for UI when running in desktop/local single-machine mode."""
    if not storage_path or not str(storage_path).strip():
        return None
    try:
        from leagent.config.settings import get_settings

        if not get_settings().is_single_machine_profile:
            return None
        return str(Path(storage_path).expanduser().resolve(strict=False))
    except Exception:  # noqa: BLE001
        return str(storage_path).strip()


async def _authorized_root_paths_for_session(
    chat_svc: ChatService,
    session_id: UUID,
    user_id: UUID,
) -> list[str] | None:
    """Resolved directory paths from session ``authorized_roots`` metadata."""
    items = await chat_svc.list_authorized_roots(session_id, user_id=user_id)
    paths: list[str] = []
    for it in items:
        if isinstance(it, dict):
            p = it.get("path")
            if isinstance(p, str) and p.strip():
                paths.append(p.strip())
    deduped = _dedupe_resolved_paths(paths)
    return deduped if deduped else None


async def _resolve_request_attachment_paths(
    session_id: UUID,
    attachment_refs: list[str] | None,
) -> list[str]:
    """Resolve mixed attachment refs (id/path/name) to concrete storage paths."""
    if not attachment_refs:
        return []

    from leagent.main import get_service_manager

    try:
        sm = get_service_manager()
    except Exception:  # noqa: BLE001
        sm = None

    if sm is None or sm.session_manager is None:
        return _dedupe_resolved_paths(attachment_refs)

    try:
        session_attachments = await sm.session_manager.list_attachments(session_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("resolve_request_attachment_paths_failed: %s", exc)
        return _dedupe_resolved_paths(attachment_refs)

    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    by_basename: dict[str, str] = {}
    for att in session_attachments:
        if not att.storage_path:
            continue
        spath = str(Path(att.storage_path).expanduser().resolve())
        by_id[str(att.id)] = spath
        if att.filename:
            by_name[att.filename.casefold()] = spath
        by_basename[Path(spath).name.casefold()] = spath

    resolved: list[str] = []
    passthrough: list[str] = []
    for ref in attachment_refs:
        if not ref:
            continue
        key = str(ref).strip()
        if not key:
            continue
        mapped = (
            by_id.get(key)
            or by_name.get(key.casefold())
            or by_basename.get(Path(key).name.casefold())
        )
        if mapped:
            resolved.append(mapped)
        else:
            passthrough.append(key)

    return _dedupe_resolved_paths(resolved + passthrough)


_KNOWLEDGE_LINE_RE = re.compile(r"@knowledge:([^\n]+)", re.UNICODE)
_UUID_36_RE = re.compile(r"^[0-9a-fA-F-]{36}$", re.IGNORECASE)


def _parse_knowledge_line_payload(raw: str) -> tuple[UUID | None, str | None]:
    """Return (file_id, original_name) from text after @knowledge: (one line).

    If ``#<uuid>`` is present, the name is the segment before the last ``#`` and
    the tail must be a valid UUID; otherwise the whole string is a display name.
    """
    s = raw.strip()
    if not s:
        return None, None
    if "#" in s:
        name, tail = s.rsplit("#", 1)
        tid = tail.strip()
        if _UUID_36_RE.match(tid):
            with suppress(ValueError):
                return UUID(tid), (name.strip() or None)
    return None, s or None


async def _resolve_knowledge_message_paths(
    user_id: UUID,
    db: DatabaseService,
    message: str,
) -> list[str]:
    """Resolve ``@knowledge:…`` mentions in *message* to indexed document storage paths.

    When ``#<file_uuid>`` is omitted, matches :attr:`File.original_name` for the
    user (``is_deleted == False``); if multiple rows match, the newest is used
    and a warning is logged.
    """
    from sqlmodel import col, select

    from leagent.services.database.models.file import File as FileModel

    refs: list[tuple[UUID | None, str | None]] = []
    for m in _KNOWLEDGE_LINE_RE.finditer(message or ""):
        file_id, name = _parse_knowledge_line_payload(m.group(1) or "")
        if file_id is not None or (name and name.strip()):
            refs.append((file_id, name))
    if not refs:
        return []

    out: list[str] = []
    async with db.session() as session:
        for file_id, name in refs:
            row = None
            if file_id is not None:
                stmt = select(FileModel).where(
                    FileModel.id == file_id,
                    FileModel.user_id == user_id,
                    FileModel.is_deleted == False,  # noqa: E712
                )
                row = (await session.exec(stmt)).first()
            elif name:
                stmt = (
                    select(FileModel)
                    .where(
                        FileModel.user_id == user_id,
                        FileModel.is_deleted == False,  # noqa: E712
                        FileModel.original_name == name,
                    )
                    .order_by(col(FileModel.created_at).desc())
                )
                rows = list((await session.exec(stmt)).all())
                if len(rows) > 1:
                    logger.warning(
                        "knowledge_ref_ambiguous_name: user_id=%s name=%r count=%s",
                        user_id,
                        name,
                        len(rows),
                    )
                row = rows[0] if rows else None
            if row and row.storage_path:
                with suppress(OSError, RuntimeError, ValueError):
                    out.append(str(Path(row.storage_path).expanduser().resolve()))
    return out


def _merge_agent_attachment_paths(
    base: list[str] | None,
    extra: list[str],
) -> list[str] | None:
    combined = (base or []) + extra
    if not combined:
        return None
    return _dedupe_resolved_paths(combined) or None


# ---------------------------------------------------------------------------
# Frontend-compatible streaming endpoint (/chat/stream)
# ---------------------------------------------------------------------------


@router.post("/stream")
async def chat_stream_endpoint(
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    message: str = Form(default=""),
    session_id: str | None = Form(default=None),
    files: list[UploadFile] = File(default=[]),
    history: str | None = Form(default=None),
    folder_id: str | None = Form(default=None),
    file_ids: str | None = Form(default=None),
    tool_replies: str | None = Form(default=None),
    project_folder_id: str | None = Form(default=None),
    model_mode: str | None = Form(default=None),
    model_provider: str | None = Form(default=None),
    model_name: str | None = Form(default=None),
):
    """Frontend-compatible streaming endpoint.

    Accepts FormData (message, session_id, files, history, folder_id,
    file_ids, project_folder_id) and produces SSE events in the format
    expected by the frontend ``useChat`` hook.

    ``project_folder_id`` binds this turn to a ``Folder`` that has
    ``is_project=True`` so the resolved ``project_path`` is folded
    into ``tool_extra['project_roots']`` for every tool call. The
    coding agent and ``project_*`` tools use this transparently.
    """
    incoming_file_parts = [f for f in (files or []) if f is not None]
    has_text = bool(message and message.strip())
    has_folder = bool(folder_id and str(folder_id).strip())
    has_file_ids = bool(file_ids and str(file_ids).strip())
    parsed_tool_replies = _parse_tool_replies_json(tool_replies)
    has_tool_replies = bool(parsed_tool_replies)
    if not (has_text or incoming_file_parts or has_folder or has_file_ids or has_tool_replies):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Send a non-empty message, attach files, add folder/knowledge context, "
                "or submit tool_replies to continue after ask_user."
            ),
        )

    parsed_session_id: UUID | None = None
    if session_id:
        with suppress(ValueError):
            parsed_session_id = UUID(session_id)

    if not parsed_session_id:
        new_session = await chat_svc.create_session(
            user_id,
            name=f"Chat {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        )
        parsed_session_id = new_session.id

    # ---- Ingest uploaded files via SessionManager ----
    attachment_paths: list[str] = []
    persisted_file_ids: list[str] = []
    session_attachment_payloads: list[dict[str, Any]] = []
    ingest_errors: list[dict[str, str]] = []
    # True when the client sent at least one multipart file part (even if ingest
    # later fails). Used so SSE always emits `attachments` and the UI can drop
    # optimistic placeholder rows instead of showing files that never landed on disk.
    had_upload_attempt = bool(incoming_file_parts)

    if incoming_file_parts:
        session_attachment_payloads, uploaded_paths, ingest_errors = await _attach_chat_files(
            user_id, parsed_session_id, incoming_file_parts,
        )
        persisted_file_ids = [a["id"] for a in session_attachment_payloads]
        attachment_paths.extend(uploaded_paths)

    context_items = await _resolve_folder_context(user_id, db, folder_id, file_ids)
    attachment_paths.extend(_context_item_paths(context_items))
    attachment_paths.extend(await _resolve_knowledge_message_paths(user_id, db, message))
    selected_folder_context_note = await _resolve_folder_context_note(
        user_id,
        db,
        folder_id,
        attached_file_count=len(context_items),
    )

    project_path_for_turn = await _resolve_project_folder_path(
        user_id, db, project_folder_id,
    )
    if project_path_for_turn:
        # Persist on the session so reloads / resume keep the binding
        # without the client re-sending it on every request.
        with suppress(Exception):
            await chat_svc.merge_session_metadata(
                parsed_session_id,
                user_id=user_id,
                patch={
                    "project_folder_id": str(project_folder_id),
                    "project_path": project_path_for_turn,
                },
            )
    else:
        # No project_folder_id on this request: try to recover one
        # the session was bound to in a previous turn so the user
        # doesn't have to keep selecting it in the chip.
        with suppress(Exception):
            existing = await chat_svc.get_session(parsed_session_id, user_id=user_id)
            if existing and existing.session_metadata:
                try:
                    meta = json.loads(existing.session_metadata)
                except (TypeError, ValueError):
                    meta = {}
                fallback_id = meta.get("project_folder_id") if isinstance(meta, dict) else None
                if fallback_id:
                    project_path_for_turn = await _resolve_project_folder_path(
                        user_id, db, fallback_id,
                    )

    # -- "continue" command: resume an interrupted conversation --
    _continue_keywords = {"continue", "继续", "続ける", "fortsetzen", "continuar"}
    _is_continue = (message or "").strip().lower() in _continue_keywords
    _resumable_state: dict[str, Any] | None = None
    if _is_continue and parsed_session_id:
        try:
            existing_sess = await chat_svc.get_session(parsed_session_id, user_id=user_id)
            if existing_sess and existing_sess.session_metadata:
                _meta = json.loads(existing_sess.session_metadata)
                if isinstance(_meta, dict) and isinstance(_meta.get("resumable_state"), dict):
                    _resumable_state = _meta["resumable_state"]
                    original_msg = _resumable_state.get("user_message", "")
                    partial = _resumable_state.get("partial_response", "")
                    if original_msg:
                        message = original_msg
                        if partial:
                            message = (
                                f"{original_msg}\n\n"
                                f"[System: The previous response was interrupted. "
                                f"Partial response so far: {partial[:500]}... "
                                f"Please continue from where you left off.]"
                            )
                    # Clear resumable state
                    _meta.pop("resumable_state", None)
                    await chat_svc.merge_session_metadata(
                        parsed_session_id, user_id=user_id, patch={"resumable_state": None},
                    )
        except Exception:  # noqa: BLE001
            logger.debug("continue_resume_lookup_failed", exc_info=True)

    message_for_agent = (
        f"{message}{selected_folder_context_note}"
        if selected_folder_context_note
        else message
    )

    selected_model_provider = (model_provider or "").strip() or None
    selected_model_name = (model_name or "").strip() or None
    if selected_model_provider or selected_model_name:
        if not (selected_model_provider and selected_model_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both model_provider and model_name are required when selecting a model.",
            )
        try:
            from leagent.llm.provider_config import enabled_model_names, get_provider_config_service

            provider_config = get_provider_config_service().get_provider(selected_model_provider)
            allowed_models = enabled_model_names(provider_config.models) if provider_config else []
        except Exception as exc:  # noqa: BLE001
            logger.debug("selected_model_validation_failed", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected model is not available.",
            ) from exc
        if (
            provider_config is None
            or not provider_config.enabled
            or selected_model_name not in allowed_models
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected model is not enabled.",
            )

    stream_user_message_id: UUID | None = None

    if has_tool_replies:
        from leagent.main import get_service_manager

        sm = get_service_manager()
        for tr in parsed_tool_replies:
            replaced_session = False
            if sm is not None and getattr(sm, "session_manager", None) is not None:
                replaced_session = await sm.session_manager.replace_pending_tool_reply(
                    parsed_session_id,
                    tool_call_id=tr["tool_call_id"],
                    content=tr["content"],
                )
            if not replaced_session and sm is not None and getattr(sm, "session_manager", None) is not None:
                await sm.session_manager.append_tool_result(
                    parsed_session_id,
                    tool_call_id=tr["tool_call_id"],
                    content=tr["content"],
                )

            replaced_db = await chat_svc.replace_tool_message_if_pending(
                parsed_session_id,
                tr["tool_call_id"],
                tr["content"],
                user_id=user_id,
            )
            if not replaced_db:
                await chat_svc.add_message(
                    parsed_session_id,
                    MessageRole.TOOL,
                    tr["content"],
                    user_id=user_id,
                    tool_call_id=tr["tool_call_id"],
                )
    else:
        user_row = await chat_svc.add_message(
            parsed_session_id,
            MessageRole.USER,
            message,
            user_id=user_id,
            attachments=persisted_file_ids if persisted_file_ids else None,
        )
        stream_user_message_id = user_row.id

    partial_assistant_tool_calls: list[dict[str, Any]] | None = None

    async def frontend_sse_generator() -> AsyncIterator[dict[str, Any]]:
        nonlocal partial_assistant_tool_calls
        if had_upload_attempt:
            yield _format_frontend_event("attachments", {
                "session_id": str(parsed_session_id),
                "attachments": session_attachment_payloads,
            })

        for err in ingest_errors:
            yield _format_frontend_event("error", {"message": f"File '{err['file']}': {err['error']}"})

        response_content = ""
        last_extensions_json: str | None = None
        agent = build_agent_controller()
        if agent is not None and selected_model_provider and selected_model_name:
            agent.config.model_provider = selected_model_provider
            agent.config.model_name = selected_model_name
        from leagent.services.chat.pet_personality import apply_pet_personality_to_agent
        await apply_pet_personality_to_agent(agent, db, user_id)
        assistant_row: Any | None = None

        accum_tool_calls_by_id: dict[str, dict[str, Any]] = {}
        stream_thinking_for_db: str | None = None
        task_progress_by_id: dict[str, dict[str, Any]] = {}
        gen_ui_snapshot: dict[str, Any] | None = None
        pet_bubble_snapshot: dict[str, Any] | None = None
        last_complete_event: dict[str, Any] | None = None
        workspace_attachment_ids: list[str] = []

        def remember_workspace_attachments(payload: Any) -> None:
            if not isinstance(payload, dict):
                return
            raw_attachments = payload.get("attachments")
            if not isinstance(raw_attachments, list):
                return
            for item in raw_attachments:
                if not isinstance(item, dict):
                    continue
                raw_id = item.get("id")
                if raw_id is None:
                    continue
                attachment_id = str(raw_id).strip()
                if attachment_id and attachment_id not in workspace_attachment_ids:
                    workspace_attachment_ids.append(attachment_id)

        def schedule_auto_title(
            ar: Any | None = None,
            *,
            require_assistant_message: bool = True,
        ) -> None:
            """Run title LLM off the SSE critical path so [DONE] is not delayed."""
            if require_assistant_message and ar is None:
                return
            if stream_user_message_id is None:
                return
            try:
                from leagent.main import get_service_manager
                from leagent.services.chat.auto_title import maybe_auto_title_session

                sm = get_service_manager()
                llm = sm.llm_service if sm else None
                if not llm:
                    return
                sid = parsed_session_id
                uid = user_id
                utext = message
                atext = response_content or ""

                async def _auto_title_background() -> None:
                    try:
                        await asyncio.wait_for(
                            maybe_auto_title_session(
                                chat_svc,
                                llm,
                                sid,
                                uid,
                                user_text=utext,
                                assistant_text=atext,
                                require_assistant_message=require_assistant_message,
                            ),
                            timeout=20.0,
                        )
                    except TimeoutError:
                        logger.debug("chat auto-title timed out for session %s", sid)
                    except Exception:
                        logger.debug("chat auto-title skipped", exc_info=True)

                asyncio.create_task(_auto_title_background())
            except Exception:
                logger.debug("chat auto-title schedule skipped", exc_info=True)

        if not has_tool_replies and stream_user_message_id is not None:
            schedule_auto_title(require_assistant_message=False)

        # Per-request reasoning effort from frontend ModelSelector.
        _effort_token = None
        if model_mode and model_mode in ("reasoning", "max"):
            try:
                from leagent.llm.providers.deepseek import set_reasoning_effort_override
                effort_value = "max" if model_mode == "max" else "high"
                _effort_token = set_reasoning_effort_override(effort_value)
            except Exception:
                pass

        try:
            if agent is not None:
                agent_attachments = _dedupe_resolved_paths(attachment_paths) or None
                session_auth_roots = await _authorized_root_paths_for_session(
                    chat_svc, parsed_session_id, user_id,
                )
                _conv_timeout = 600
                try:
                    from leagent.config.settings import get_settings as _gs
                    _conv_timeout = _gs().agent.conversation_timeout_sec
                except Exception:  # noqa: BLE001
                    pass
                agent_task_id = uuid4()
                yield _format_frontend_event(
                    "agent_task",
                    {"task_id": str(agent_task_id), "session_id": str(parsed_session_id)},
                )
                async for etype, edata, acc_text in _run_agent_stream(
                    agent,
                    message_for_agent,
                    parsed_session_id,
                    user_id,
                    attachments=agent_attachments,
                    project_roots=[project_path_for_turn] if project_path_for_turn else None,
                    authorized_roots=session_auth_roots,
                    skip_append_user=has_tool_replies,
                    persisted_user_message_id=stream_user_message_id,
                    conversation_timeout_sec=_conv_timeout,
                    agent_task_id=agent_task_id,
                ):
                    response_content = acc_text
                    if etype == "token":
                        yield _format_frontend_event("content", edata.get("token", ""))
                    elif etype == "thinking":
                        thought = edata.get("thought", "") if isinstance(edata, dict) else ""
                        if isinstance(thought, str) and thought.strip():
                            stream_thinking_for_db = _merge_stream_thinking_for_persist(
                                stream_thinking_for_db,
                                thought,
                            )
                        yield _format_frontend_event("thinking", thought)
                    elif etype == "tool_call_delta":
                        yield _format_frontend_event("tool_call_delta", edata)
                    elif etype == "nested_agent_preview":
                        yield _format_frontend_event("nested_agent_preview", edata)
                    elif etype in ("tool_call", "tool_result"):
                        if etype == "tool_call" and isinstance(edata, dict):
                            tc_oai = _openai_tool_call_from_stream_edata(edata)
                            if tc_oai:
                                accum_tool_calls_by_id[tc_oai["id"]] = tc_oai
                        yield _format_frontend_event(etype, edata)
                        if isinstance(edata, dict):
                            for sub_type, sub_data in _companion_sse_events(etype, edata):
                                if sub_type == "ui_tree" and isinstance(sub_data, dict):
                                    gen_ui_snapshot = sub_data
                                if sub_type == "pet_bubble" and isinstance(sub_data, dict):
                                    pet_bubble_snapshot = dict(sub_data)
                                yield _format_frontend_event(sub_type, sub_data)
                    elif etype == "workspace_attachments":
                        remember_workspace_attachments(edata)
                        yield _format_frontend_event(etype, edata)
                    elif etype == "task_progress":
                        if isinstance(edata, dict):
                            tid = edata.get("task_id")
                            if tid is not None:
                                task_progress_by_id[str(tid)] = dict(edata)
                        yield _format_frontend_event("task_progress", edata)
                    elif etype == "user_input_request":
                        yield _format_frontend_event("user_input_request", edata)
                    elif etype == "workflow":
                        yield _format_frontend_event("workflow", edata)
                        if isinstance(edata, dict):
                            spec = edata.get("spec")
                            embed = edata.get("embed")
                            if isinstance(embed, dict) and isinstance(embed.get("data"), dict):
                                from leagent.chat_workflow.workflow_embed import build_extensions_payload

                                last_extensions_json = json.dumps(
                                    build_extensions_payload(
                                        flow_data=embed["data"],
                                        digest=str(embed.get("digest") or ""),
                                        flow_id=str(embed["flow_id"]) if embed.get("flow_id") else None,
                                        title=str(embed.get("title") or "") or None,
                                        summary=str(embed.get("summary") or "") or None,
                                    ),
                                    ensure_ascii=False,
                                )
                            elif isinstance(spec, dict):
                                last_extensions_json = json.dumps({
                                    "chat_workflow": spec,
                                    "chat_workflow_digest": edata.get("digest"),
                                })
                    elif etype == "complete":
                        last_complete_event = edata if isinstance(edata, dict) else {}
                        md = edata.get("metadata") or {}
                        if edata.get("partial") and md.get("awaiting_user_input"):
                            partial_assistant_tool_calls = md.get("assistant_tool_calls")
                        if not response_content:
                            response_content = edata.get("text", "") or response_content
                            if response_content:
                                yield _format_frontend_event("content", response_content)
                    elif etype == "error":
                        yield _format_frontend_event("error", {"message": edata.get("error", "Unknown error")})
            else:
                yield _format_frontend_event("error", {
                    "message": "No LLM provider configured. Please configure a model in Settings.",
                })

            # Emit context usage statistics for the chat UI before completion signal.
            _usage_payload = (last_complete_event or {}).get("token_usage")
            if isinstance(_usage_payload, dict) and _usage_payload:
                yield _format_frontend_event("context_usage", _usage_payload)

            # Tell the client token streaming is finished before DB persistence so the UI
            # can hide the caret and show actions without waiting on add_message latency.
            yield _format_frontend_event("assistant_complete", {})

            md_fin = (last_complete_event or {}).get("metadata") or {}
            reasoning_fin = md_fin.get("reasoning_content")
            thinking_merged = (stream_thinking_for_db or "").strip()
            if reasoning_fin and str(reasoning_fin).strip():
                rc = str(reasoning_fin).strip()
                thinking_merged = f"{thinking_merged}\n{rc}".strip() if thinking_merged else rc

            def _tp_sort_key(x: dict[str, Any]) -> tuple[float, str]:
                o = x.get("order")
                try:
                    oi = float(o) if o is not None else 1e9
                except (TypeError, ValueError):
                    oi = 1e9
                return (oi, str(x.get("label") or ""))

            task_progress_list = sorted(task_progress_by_id.values(), key=_tp_sort_key)

            merged_extensions = _merge_message_extensions_json(
                last_extensions_json,
                thinking=thinking_merged or None,
                task_progress=task_progress_list or None,
                gen_ui=gen_ui_snapshot,
                pet_bubble=pet_bubble_snapshot,
            )

            tc_for_db: list[dict[str, Any]] | None = partial_assistant_tool_calls
            if tc_for_db is None:
                md_tc = md_fin.get("assistant_tool_calls")
                if isinstance(md_tc, list) and md_tc:
                    tc_for_db = md_tc
            if tc_for_db is None and accum_tool_calls_by_id:
                tc_for_db = list(accum_tool_calls_by_id.values())

            _tu_main = (
                (last_complete_event or {}).get("token_usage")
                if isinstance(last_complete_event, dict)
                else None
            )
            _persist_in, _persist_out = _tokens_from_stream_usage(
                _tu_main if isinstance(_tu_main, dict) else None,
            )
            _output_for_db = (
                _persist_out
                if _persist_out is not None
                else (len((response_content or "").split()) or None)
            )

            if response_content or merged_extensions or tc_for_db or workspace_attachment_ids:
                assistant_row = await chat_svc.add_message(
                    parsed_session_id,
                    MessageRole.ASSISTANT,
                    response_content or "",
                    user_id=user_id,
                    model="default",
                    input_tokens=_persist_in,
                    output_tokens=_output_for_db,
                    extensions=merged_extensions,
                    tool_calls=tc_for_db,
                    attachments=workspace_attachment_ids or None,
                )
                schedule_auto_title(assistant_row)
        except asyncio.CancelledError:
            logger.warning("chat_stream_cancelled session=%s", parsed_session_id)
            yield _format_frontend_event("error", {"message": "Stream cancelled by server"})
        except Exception as e:
            logger.exception("Error in /chat/stream: %s", e)
            yield _format_frontend_event("error", {"message": str(e)})
        finally:
            # Reset per-request reasoning effort override.
            if _effort_token is not None:
                try:
                    from leagent.llm.providers.deepseek import reset_reasoning_effort_override
                    reset_reasoning_effort_override(_effort_token)
                except Exception:
                    pass

            # Persist partial response on any exit path
            if (response_content or workspace_attachment_ids) and assistant_row is None:
                try:
                    task_progress_list_fin = sorted(
                        task_progress_by_id.values(),
                        key=lambda x: (float(x.get("order", 1e9)), str(x.get("label", ""))),
                    )
                    merged_ext_fin = _merge_message_extensions_json(
                        last_extensions_json,
                        thinking=stream_thinking_for_db or None,
                        task_progress=task_progress_list_fin or None,
                        gen_ui=gen_ui_snapshot,
                        pet_bubble=pet_bubble_snapshot,
                    )
                    _tu_fin = (
                        (last_complete_event or {}).get("token_usage")
                        if isinstance(last_complete_event, dict)
                        else None
                    )
                    _pin_fin, _pout_fin = _tokens_from_stream_usage(
                        _tu_fin if isinstance(_tu_fin, dict) else None,
                    )
                    assistant_row = await chat_svc.add_message(
                        parsed_session_id,
                        MessageRole.ASSISTANT,
                        response_content or "",
                        user_id=user_id,
                        model="default",
                        input_tokens=_pin_fin,
                        output_tokens=_pout_fin,
                        extensions=merged_ext_fin,
                        attachments=workspace_attachment_ids or None,
                    )
                except Exception:
                    logger.debug("partial_assistant_persist_failed", exc_info=True)
                else:
                    schedule_auto_title(assistant_row)

            yield _format_frontend_event("assistant_complete", {})

            ids_payload: dict[str, str] = {}
            if stream_user_message_id is not None:
                ids_payload["user_message_id"] = str(stream_user_message_id)
            if assistant_row is not None:
                ids_payload["assistant_message_id"] = str(assistant_row.id)
            if ids_payload:
                yield _format_frontend_event("message_ids", ids_payload)
            yield {"event": "message", "data": "[DONE]"}

    _sse_stream_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return EventSourceResponse(
        frontend_sse_generator(),
        media_type="text/event-stream",
        headers=_sse_stream_headers,
        ping=15,
    )


# ---------------------------------------------------------------------------
# Chat Completions Endpoints (OpenAI-compatible)
# ---------------------------------------------------------------------------


async def _generate_openai_sse(
    request: ChatCompletionRequest,
    session_id: UUID,
    user_id: UUID,
    chat_svc: ChatSvc,
    *,
    attachments: list[str] | None = None,
    persisted_user_message_id: UUID | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Generate OpenAI-compatible SSE chunks."""

    completion_id = f"chatcmpl-{uuid4().hex[:24]}"
    created = int(time.time())
    model = request.model
    start_time = time.time()
    output_tokens = 0

    try:
        yield _format_openai_chunk(completion_id, created, model, {"role": "assistant", "content": ""})

        response_content = ""
        last_extensions_json: str | None = None
        agent = build_agent_controller()

        if agent is not None:
            from leagent.services.chat.pet_personality import apply_pet_personality_to_agent
            try:
                await apply_pet_personality_to_agent(agent, get_database_service(), user_id)
            except Exception:
                logger.debug("openai_sse_apply_pet_personality_failed", exc_info=True)
            last_user_msg = next(
                (m.content for m in reversed(request.messages) if m.role == MessageRole.USER), "",
            )
            openai_auth_roots = await _authorized_root_paths_for_session(
                chat_svc, session_id, user_id,
            )
            openai_agent_task_id = uuid4()
            async for etype, edata, acc_text in _run_agent_stream(
                agent, last_user_msg, session_id, user_id,
                attachments=attachments,
                authorized_roots=openai_auth_roots,
                persisted_user_message_id=persisted_user_message_id,
                agent_task_id=openai_agent_task_id,
            ):
                response_content = acc_text
                if etype == "token":
                    token = edata.get("token", "")
                    output_tokens += 1
                    yield _format_openai_chunk(completion_id, created, model, {"content": token})
                elif etype == "thinking":
                    yield {"event": "thinking", "data": json.dumps({"thought": edata.get("thought", "")})}
                elif etype == "tool_call_delta":
                    yield {"event": "tool_call_delta", "data": json.dumps(edata)}
                elif etype == "nested_agent_preview":
                    yield {"event": "nested_agent_preview", "data": json.dumps(edata)}
                elif etype in ("tool_call", "tool_result"):
                    yield {"event": etype, "data": json.dumps(edata)}
                elif etype == "workflow":
                    yield {"event": "workflow", "data": json.dumps(edata)}
                    if isinstance(edata, dict):
                        spec = edata.get("spec")
                        embed = edata.get("embed")
                        if isinstance(embed, dict) and isinstance(embed.get("data"), dict):
                            from leagent.chat_workflow.workflow_embed import build_extensions_payload

                            last_extensions_json = json.dumps(
                                build_extensions_payload(
                                    flow_data=embed["data"],
                                    digest=str(embed.get("digest") or ""),
                                    flow_id=str(embed["flow_id"]) if embed.get("flow_id") else None,
                                    title=str(embed.get("title") or "") or None,
                                    summary=str(embed.get("summary") or "") or None,
                                ),
                                ensure_ascii=False,
                            )
                        elif isinstance(spec, dict):
                            last_extensions_json = json.dumps({
                                "chat_workflow": spec,
                                "chat_workflow_digest": edata.get("digest"),
                            })
                elif etype == "complete" and response_content and output_tokens == 0:
                    yield _format_openai_chunk(completion_id, created, model, {"content": response_content})
                elif etype == "error":
                    yield {"event": "error", "data": json.dumps({"error": edata.get("error", "Unknown error"), "type": "agent_error"})}
        else:
            yield {"event": "error", "data": json.dumps({
                "error": "No LLM provider configured",
                "type": "configuration_error",
            })}

        yield _format_openai_chunk(completion_id, created, model, {}, finish_reason="stop")
        yield {"event": "message", "data": "[DONE]"}

        latency_ms = int((time.time() - start_time) * 1000)
        if response_content or last_extensions_json:
            await chat_svc.add_message(
                session_id,
                MessageRole.ASSISTANT,
                response_content or "",
                user_id=user_id,
                model=model,
                output_tokens=output_tokens or None,
                latency_ms=latency_ms,
                extensions=last_extensions_json,
            )

    except Exception as e:
        logger.exception("Error in SSE stream: %s", e)
        yield {"event": "error", "data": json.dumps({"error": str(e), "type": "stream_error"})}


@router.post("/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    db: Annotated[DatabaseService, Depends(get_database_service)],
):
    """Create a chat completion (OpenAI-compatible). Streaming or non-streaming."""
    if not request.messages:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Messages list cannot be empty",
        )

    session_id = request.session_id
    if not session_id:
        new_session = await chat_svc.create_session(
            user_id,
            name=f"Chat {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        )
        session_id = new_session.id

    last_user_message = next(
        (m for m in reversed(request.messages) if m.role == MessageRole.USER), None,
    )
    persisted_openai_user_id: UUID | None = None
    if last_user_message:
        um_row = await chat_svc.add_message(
            session_id, MessageRole.USER, last_user_message.content, user_id=user_id,
        )
        persisted_openai_user_id = um_row.id

    last_user_text = (
        last_user_message.content
        if last_user_message
        else ""
    )
    knowledge_paths = await _resolve_knowledge_message_paths(user_id, db, last_user_text)
    merged_attachments = _merge_agent_attachment_paths(None, knowledge_paths)

    if request.stream:
        return EventSourceResponse(
            _generate_openai_sse(
                request,
                session_id,
                user_id,
                chat_svc,
                attachments=merged_attachments,
                persisted_user_message_id=persisted_openai_user_id,
            ),
            media_type="text/event-stream",
        )

    completion_id = f"chatcmpl-{uuid4().hex[:24]}"
    created = int(time.time())

    agent = build_agent_controller()
    if agent is not None:
        from leagent.services.chat.pet_personality import apply_pet_personality_to_agent
        await apply_pet_personality_to_agent(agent, db, user_id)
        last_user_msg = next(
            (m.content for m in reversed(request.messages) if m.role == MessageRole.USER), "",
        )
        completion_auth_roots = await _authorized_root_paths_for_session(
            chat_svc, session_id, user_id,
        )
        agent_response = await agent.run(
            last_user_msg,
            session_id,
            user_id=user_id,
            attachments=merged_attachments,
            authorized_roots=completion_auth_roots,
            persisted_user_message_id=persisted_openai_user_id,
            agent_task_id=uuid4(),
        )
        response_content = agent_response.text
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No LLM provider configured. Please configure a model in Settings.",
        )

    await chat_svc.add_message(
        session_id,
        MessageRole.ASSISTANT,
        response_content,
        user_id=user_id,
        model=request.model,
        output_tokens=len(response_content.split()),
    )

    return ChatCompletionResponse(
        id=completion_id,
        created=created,
        model=request.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionMessage(role=MessageRole.ASSISTANT, content=response_content),
                finish_reason="stop",
            )
        ],
        usage=ChatCompletionUsage(
            prompt_tokens=sum(len(m.content.split()) for m in request.messages),
            completion_tokens=len(response_content.split()),
            total_tokens=sum(len(m.content.split()) for m in request.messages) + len(response_content.split()),
        ),
    )


# ---------------------------------------------------------------------------
# Session Management Endpoints
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: SessionCreate,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> SessionRead:
    """Create a new chat session."""
    session = await chat_svc.create_session(
        user_id,
        name=data.name or f"New Chat {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
        flow_id=data.flow_id,
    )
    logger.info("Created chat session %s for user %s", session.id, user_id)
    return chat_session_to_read(session)


@router.get("/sessions", response_model=PaginatedResponse[SessionRead])
async def list_sessions(
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    is_active: bool | None = Query(default=None),
    flow_id: UUID | None = Query(default=None),
) -> PaginatedResponse[SessionRead]:
    """List chat sessions for the current user."""
    active_only = is_active if is_active is not None else True
    offset = (page - 1) * page_size
    sessions = await chat_svc.list_sessions(
        user_id, active_only=active_only, offset=offset, limit=page_size,
    )
    total = len(sessions)
    return PaginatedResponse[SessionRead](
        items=sessions,
        total=total,
        page=page,
        page_size=page_size,
        has_next=len(sessions) == page_size,
        has_prev=page > 1,
    )


@router.get("/sessions/{session_id}", response_model=SessionRead)
async def get_session(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> SessionRead:
    """Get a specific chat session."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return chat_session_to_read(session)


@router.get("/sessions/{session_id}/attachments", response_model=SessionAttachmentsResponse)
async def list_session_attachments(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> SessionAttachmentsResponse:
    """List all files attached to the session (uploads + tool workspace ingest)."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    from leagent.main import get_service_manager

    sm = get_service_manager()
    if sm.session_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session manager unavailable",
        )

    raw = await sm.session_manager.list_attachments(session_id, user_id=user_id)
    attachments: list[dict[str, Any]] = []
    for att in raw:
        row = att.to_dict()
        row["name"] = row.get("filename") or ""
        sp = row.get("storage_path")
        if isinstance(sp, str):
            lp = _attachment_local_path_for_sse(sp)
            if lp:
                row["local_path"] = lp
        attachments.append(row)

    return SessionAttachmentsResponse(session_id=session_id, attachments=attachments)


@router.get(
    "/sessions/{session_id}/authorized-paths",
    response_model=AuthorizedPathsResponse,
)
async def list_session_authorized_paths(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> AuthorizedPathsResponse:
    """List directories the user granted for tool access in this chat session."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    raw = await chat_svc.list_authorized_roots(session_id, user_id=user_id)
    paths = [AuthorizedPathEntry(path=str(x["path"]), label=x.get("label")) for x in raw]
    return AuthorizedPathsResponse(session_id=session_id, paths=paths)


@router.post(
    "/sessions/{session_id}/authorized-paths",
    response_model=AuthorizedPathsResponse,
)
async def add_session_authorized_path(
    session_id: UUID,
    body: AuthorizedPathCreateBody,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> AuthorizedPathsResponse:
    """Grant an absolute directory for this session (validated like project paths)."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    try:
        updated = await chat_svc.add_authorized_root(
            session_id, user_id, path=body.path, label=body.label,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    paths = [AuthorizedPathEntry(path=str(x["path"]), label=x.get("label")) for x in updated]
    return AuthorizedPathsResponse(session_id=session_id, paths=paths)


@router.delete(
    "/sessions/{session_id}/authorized-paths",
    response_model=AuthorizedPathsResponse,
)
async def remove_session_authorized_path(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    path: str = Query(..., min_length=1, max_length=4096),
) -> AuthorizedPathsResponse:
    """Revoke a previously granted directory (match on stored path string)."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    updated = await chat_svc.remove_authorized_root(session_id, user_id, path=path)
    paths = [AuthorizedPathEntry(path=str(x["path"]), label=x.get("label")) for x in updated]
    return AuthorizedPathsResponse(session_id=session_id, paths=paths)


# ---------------------------------------------------------------------------
# Local directory browser (single-machine deployment)
# ---------------------------------------------------------------------------


class _DirEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


class _BrowseResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[_DirEntry]
    quick_access: list[_DirEntry]


def _quick_access_dirs() -> list[_DirEntry]:
    """Well-known directories for the current OS user."""
    home = Path.home()
    candidates = [
        ("Home", home),
        ("Desktop", home / "Desktop"),
        ("Documents", home / "Documents"),
        ("Downloads", home / "Downloads"),
    ]
    out: list[_DirEntry] = []
    for label, p in candidates:
        try:
            resolved = p.resolve(strict=True)
            if resolved.is_dir():
                out.append(_DirEntry(name=label, path=str(resolved), is_dir=True))
        except (OSError, RuntimeError):
            continue
    return out


@router.get("/browse-directories", response_model=_BrowseResponse)
async def browse_directories(
    user_id: CurrentUserId,
    path: str | None = Query(None, max_length=4096),
) -> _BrowseResponse:
    """List subdirectories and files at *path* on the local machine.

    Used by the folder-grant modal to let users navigate the filesystem
    visually instead of typing absolute paths by hand.  Returns only
    names and ``is_dir`` — no file contents are exposed.
    """
    quick = _quick_access_dirs()

    if not path:
        root = Path.home()
    else:
        root = Path(path).expanduser()

    try:
        root = root.resolve(strict=True)
    except (FileNotFoundError, OSError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory not found: {path}",
        )

    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Not a directory: {path}",
        )

    entries: list[_DirEntry] = []
    try:
        for child in sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if child.name.startswith("."):
                continue
            entries.append(
                _DirEntry(name=child.name, path=str(child), is_dir=child.is_dir())
            )
    except PermissionError:
        pass

    parent_str: str | None = None
    if root.parent != root:
        parent_str = str(root.parent)

    return _BrowseResponse(
        path=str(root),
        parent=parent_str,
        entries=entries,
        quick_access=quick,
    )


async def _compose_prompt_preview(
    *,
    session_id: UUID,
    user_id: UUID,
    chat_svc: ChatService,
    query_override: str | None,
) -> PromptPreviewRead:
    """Rebuild the system prompt the agent would see for this session (best-effort)."""
    from leagent.context import ContextManager
    from leagent.main import get_service_manager
    from leagent.prompts import get_prompt_builder
    from leagent.tools.registry import get_registry

    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    owner_id = session.user_id
    if owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session has no owner",
        )

    sm = get_service_manager()
    if sm.session_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session manager unavailable",
        )

    raw_query = (query_override or "").strip()
    if not raw_query:
        items, _ = await chat_svc.get_messages_paginated(session_id, page=1, page_size=500)
        for m in reversed(items):
            if m.role == MessageRole.USER:
                raw_query = (m.content or "").strip()
                break

    query_display = raw_query
    effective_query = raw_query.strip() or " "

    pb = get_prompt_builder()
    ctx = ContextManager(
        cwd=".",
        settings=sm.settings,
        tools=get_registry(),
        permission_context=None,
        skills_manager=None,
        agent_memory=sm.agent_memory,
        session_manager=sm.session_manager,
        working_scratchpad=None,
        prompt_registry=pb.registry,
        session_id=session_id,
        user_id=owner_id,
        variant="default_agent",
        template_variant="default",
    )
    try:
        turn = await ctx.prepare_turn(
            effective_query,
            task_id=uuid4(),
        )
    except Exception as exc:
        logger.warning("prompt_preview_failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to assemble prompt preview",
        ) from exc

    bp = turn.built_prompt
    layers = [
        PromptLayerRead(
            name=layer.name,
            body=layer.body,
            tokens=layer.tokens,
            truncated=layer.truncated,
        )
        for layer in bp.layers
    ]

    approx_transcript_tokens = 0
    try:
        from leagent.memory.compact import _approximate_tokens

        async with sm.session_manager.locked(session_id) as st:
            approx_transcript_tokens = _approximate_tokens(st.llm_messages())
    except Exception as exc:
        logger.warning("prompt_preview_transcript_tokens_failed: %s", exc, exc_info=True)

    layer_token_sum = sum(layer.tokens for layer in bp.layers)
    approx_context_tokens = layer_token_sum + approx_transcript_tokens

    return PromptPreviewRead(
        query_used=query_display,
        system_text=bp.system_text,
        total_chars=bp.total_chars,
        stable_hash=bp.stable_hash,
        full_hash=bp.full_hash,
        variant_key=bp.variant_key,
        layers=layers,
        approx_transcript_tokens=approx_transcript_tokens,
        approx_context_tokens=approx_context_tokens,
    )


@router.get(
    "/sessions/{session_id}/agent-memory",
    response_model=AgentMemorySnapshotRead,
)
async def get_session_agent_memory(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    limit: int = Query(default=50, ge=1, le=100),
) -> AgentMemorySnapshotRead:
    """Read-only snapshot of cognitive agent memory for the session owner."""
    from leagent.main import get_service_manager

    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    sm = get_service_manager()
    mem = sm.agent_memory
    if mem is None:
        return AgentMemorySnapshotRead(
            enabled=False,
            episodes=[],
            facts=[],
            procedures=[],
        )

    owner_id = session.user_id
    if owner_id is None:
        return AgentMemorySnapshotRead(
            enabled=True,
            episodes=[],
            facts=[],
            procedures=[],
        )

    episodes, facts, procedures = await asyncio.gather(
        mem.episodic.list_recent(session_id=session_id, limit=limit),
        mem.semantic.list_for_user(owner_id, limit=limit),
        mem.procedural.list_recent_for_user(user_id=owner_id, limit=limit),
    )

    episode_reads = [
        AgentMemoryEpisodeRead(
            id=str(ep.id),
            session_id=str(ep.session_id),
            user_id=str(ep.user_id) if ep.user_id else None,
            summary=ep.summary,
            tags=list(ep.tags),
            importance=ep.importance,
            token_count=ep.token_count,
            recall_count=ep.recall_count,
            last_recalled_at=ep.last_recalled_at,
            created_at=ep.created_at,
        )
        for ep in episodes
    ]
    fact_reads = [
        AgentMemoryFactRead(
            id=str(f.id),
            key=f.key,
            value=f.value,
            confidence=f.confidence,
            source=f.source,
            workspace_id=str(f.workspace_id) if f.workspace_id else None,
            created_at=f.created_at,
        )
        for f in facts
    ]
    procedure_reads = [
        AgentMemoryProcedureRead(
            id=str(p.id),
            name=p.name,
            signature=p.signature,
            description=p.description,
            run_count=p.run_count,
            success_count=p.success_count,
            success_rate=p.success_rate,
            last_outcome=p.last_outcome,
            last_run_at=p.last_run_at,
            created_at=p.created_at,
        )
        for p in procedures
    ]

    return AgentMemorySnapshotRead(
        enabled=True,
        episodes=episode_reads,
        facts=fact_reads,
        procedures=procedure_reads,
    )


@router.get(
    "/sessions/{session_id}/prompt-preview",
    response_model=PromptPreviewRead,
)
async def get_session_prompt_preview(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    query: str | None = Query(
        default=None,
        max_length=100_000,
        description="Override preview query; defaults to latest user message in session.",
    ),
) -> PromptPreviewRead:
    """Assemble the current system prompt (same pipeline as the agent)."""
    return await _compose_prompt_preview(
        session_id=session_id,
        user_id=user_id,
        chat_svc=chat_svc,
        query_override=query,
    )


class SessionCancelResponse(BaseModel):
    session_id: str
    cancelled: bool
    processes_killed: int = 0
    message: str


class AgentTaskItem(BaseModel):
    task_id: str
    session_id: str
    started_at: str
    updated_at: str
    phase: str
    tool_name: str | None = None
    status: str = "running"


class AgentTasksListResponse(BaseModel):
    session_id: str
    tasks: list[AgentTaskItem]
    scope_note: str = (
        "This process only. Multiple gateway workers each maintain an independent task list."
    )


class CompactContextRequest(BaseModel):
    force_llm: bool = False


class CompactContextResponse(BaseModel):
    applied: bool
    approx_tokens_before: int
    approx_tokens_after: int
    stages_applied: list[str]
    #: Hypothetical row reduction if the same compression were written to the transcript.
    removed_messages: int
    llm_autocompact_applied: bool


@router.post("/sessions/{session_id}/compact-context", response_model=CompactContextResponse)
async def compact_session_context(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    body: CompactContextRequest | None = None,
) -> CompactContextResponse:
    """Dry-run transcript compression for token metrics only.

    Does **not** mutate :class:`~leagent.services.session.state.SessionState`
    messages or database rows — full chat history stays intact.

    The same micro → progressive → optional summariser stack (minus this
    endpoint's ``force_llm`` path) runs on **each** model call inside
    :func:`leagent.agent.query._query_loop` (progressive + ``QueryDeps`` micro /
    autocompact) on a transient copy of the thread only.
    """
    from leagent.context.session_compression import run_session_compression_pipeline
    from leagent.main import get_service_manager

    sm = get_service_manager()
    session_manager = sm.session_manager
    llm = sm.llm_service
    settings = sm.settings

    if session_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session manager unavailable",
        )

    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    force_llm = body.force_llm if body else False
    before_count = 0
    async with session_manager.locked(session_id) as state:
        before_count = len(state.messages)
        llm_msgs = state.llm_messages()
        pipeline_result = await run_session_compression_pipeline(
            llm_msgs,
            settings=settings,
            llm=llm,
            force_llm=force_llm,
        )

    after_count = len(pipeline_result.messages)
    applied = pipeline_result.approx_tokens_before > pipeline_result.approx_tokens_after or (
        after_count != before_count
    )
    return CompactContextResponse(
        applied=applied,
        approx_tokens_before=pipeline_result.approx_tokens_before,
        approx_tokens_after=pipeline_result.approx_tokens_after,
        stages_applied=pipeline_result.stages_applied,
        removed_messages=max(0, before_count - after_count),
        llm_autocompact_applied=pipeline_result.llm_autocompact_applied,
    )


@router.get("/sessions/{session_id}/agent-tasks", response_model=AgentTasksListResponse)
async def list_session_agent_tasks(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> AgentTasksListResponse:
    """List in-flight agent runs for this session (monitoring; in-process scope only)."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    from leagent.agent.controller import AgentController

    records = AgentController.list_agent_tasks_for_session(session_id)
    items = [
        AgentTaskItem(
            task_id=str(r.task_id),
            session_id=str(r.session_id),
            started_at=r.started_at.isoformat() + "Z",
            updated_at=r.updated_at.isoformat() + "Z",
            phase=r.phase,
            tool_name=r.tool_name,
            status=r.status,
        )
        for r in records
    ]
    return AgentTasksListResponse(session_id=str(session_id), tasks=items)


@router.post("/sessions/{session_id}/cancel", response_model=SessionCancelResponse)
async def cancel_session(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> SessionCancelResponse:
    """Cancel a running agent session, killing all backend tasks and subprocesses."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    from leagent.agent.controller import AgentController

    cancelled = AgentController.cancel_session(session_id)

    procs_killed = 0
    try:
        from leagent.services.execution.engine import get_execution_engine
        engine = get_execution_engine()
        procs_killed = await engine.cancel_session(str(session_id))
    except Exception:  # noqa: BLE001
        pass

    if cancelled:
        msg = "Session cancelled"
        if procs_killed:
            msg += f", {procs_killed} subprocess(es) killed"
    elif procs_killed:
        msg = f"No in-process agent task on this worker; killed {procs_killed} subprocess(es)"
    else:
        msg = "No active agent task for this session"

    return SessionCancelResponse(
        session_id=str(session_id),
        cancelled=cancelled,
        processes_killed=procs_killed,
        message=msg,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> None:
    """Delete a chat session and all its messages."""
    deleted = await chat_svc.delete_session(session_id, user_id, soft=False)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    logger.info("Deleted chat session %s for user %s", session_id, user_id)


@router.patch("/sessions/{session_id}", response_model=SessionRead)
async def update_session(
    session_id: UUID,
    body: SessionUpdateRequest,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> SessionRead:
    """Update a chat session (name, active flag, and/or session metadata patch)."""
    existing = await chat_svc.get_session(session_id, user_id=user_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if body.metadata_patch:
        sanitized = await chat_svc.sanitize_metadata_patch(session_id, body.metadata_patch)
        if sanitized:
            merged = await chat_svc.merge_session_metadata(
                session_id, user_id, patch=sanitized,
            )
            if merged is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if body.name is not None or body.is_active is not None:
        updated = await chat_svc.update_session(
            session_id, user_id, name=body.name, is_active=body.is_active,
        )
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    final = await chat_svc.get_session(session_id, user_id=user_id)
    if not final:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return chat_session_to_read(final)


# ---------------------------------------------------------------------------
# Message Endpoints
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}/messages", response_model=PaginatedResponse[MessageRead])
async def get_session_messages(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    role: MessageRole | None = Query(default=None),
    before: datetime | None = Query(default=None),
    after: datetime | None = Query(default=None),
    order: str = Query(default="asc", pattern="^(asc|desc)$"),
) -> PaginatedResponse[MessageRead]:
    """Get messages for a session with pagination and filtering."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    items, total = await chat_svc.get_messages_paginated(
        session_id,
        page=page,
        page_size=page_size,
        role=role,
        before=before,
        after=after,
        order=order,
    )
    return PaginatedResponse[MessageRead](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
        has_prev=page > 1,
    )


class MessageFeedbackBody(BaseModel):
    """Thumbs feedback: ``5`` = like, ``1`` = dislike, ``null`` = clear."""

    model_config = ConfigDict(extra="forbid")
    rating: int | None


@router.patch("/sessions/{session_id}/messages/{message_id}/feedback")
async def patch_message_feedback(
    session_id: UUID,
    message_id: UUID,
    body: MessageFeedbackBody,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> dict[str, Any]:
    """Set or clear assistant message rating; feedback informs memory formation policy."""
    ok = await chat_svc.patch_assistant_message_rating(
        session_id,
        message_id,
        user_id=user_id,
        rating=body.rating,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if body.rating is None:
        return {"ok": True, "procedure_promoted": False}

    from leagent.main import get_service_manager

    sm = get_service_manager()
    mem = sm.agent_memory if sm is not None else None

    is_like = body.rating == 5

    if is_like:
        from leagent.memory.procedure_promotion import record_procedure_for_liked_assistant

        enable_memory = mem is not None
        ok2, err, promoted, memory_status = await record_procedure_for_liked_assistant(
            chat_svc=chat_svc,
            agent_memory=mem,
            enable_memory=enable_memory,
            session_id=session_id,
            assistant_message_id=message_id,
            user_id=user_id,
        )
        if not ok2:
            return {
                "ok": True,
                "procedure_promoted": False,
                "procedure_error": err,
                "procedure_memory_status": memory_status,
                "memory_degraded": bool(memory_status.get("degraded")),
            }
        return {
            "ok": True,
            "procedure_promoted": promoted,
            "procedure_memory_status": memory_status,
            "memory_degraded": bool(memory_status.get("degraded")),
        }

    if mem is not None:
        try:
            decision = await mem.observe_feedback(
                is_like=False,
                has_tools=False,
                existing_importance=0.3,
            )
            return {
                "ok": True,
                "procedure_promoted": False,
                "formation_decision": {
                    "importance": decision.importance,
                    "provenance": decision.provenance,
                    "suppress": decision.suppress,
                },
            }
        except Exception:
            pass

    return {"ok": True, "procedure_promoted": False}


@router.post("/sessions/{session_id}/workflow-steps/{step_id}/run")
async def run_chat_workflow_step(
    session_id: UUID,
    step_id: str,
    body: ChatWorkflowStepRunRequest,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> dict[str, Any]:
    """Execute a single workflow step tool call after digest verification."""
    from leagent.chat_workflow.schema import (
        ValidationError as ChatWorkflowValidationError,
        chat_workflow_digest,
        parse_chat_workflow_spec,
        resolve_argument_templates,
    )
    from leagent.main import get_service_manager
    from leagent.tools.context import build_tool_context
    from leagent.tools.executor import get_executor
    from leagent.tools.registry import get_registry
    from leagent.tools.session_attachment_context import tool_extra_for_chat_session

    msg = await chat_svc.get_session_message(session_id, body.message_id, user_id=user_id)
    if not msg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if msg.role != MessageRole.ASSISTANT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workflow steps apply only to assistant messages",
        )
    if not msg.extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message has no workflow data",
        )

    try:
        ext = json.loads(msg.extensions)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid extensions JSON",
        ) from None

    raw_spec = ext.get("chat_workflow")
    if not isinstance(raw_spec, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No chat_workflow in message extensions",
        )

    registry = get_registry()
    try:
        spec = parse_chat_workflow_spec(raw_spec, registry=registry)
    except ChatWorkflowValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    digest_stored = ext.get("chat_workflow_digest")
    if isinstance(digest_stored, str) and len(digest_stored) >= 32:
        digest_ok = digest_stored.lower() == body.workflow_digest.strip().lower()
    else:
        digest_ok = chat_workflow_digest(spec).lower() == body.workflow_digest.strip().lower()
    if not digest_ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="workflow_digest does not match stored workflow",
        )

    step = next((s for s in spec.steps if s.id == step_id), None)
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step not found")

    sm = None
    with suppress(Exception):
        sm = get_service_manager()

    tool_ctx = build_tool_context(
        service_manager=sm,
        user_id=str(user_id),
        session_id=str(session_id),
    )
    if sm is not None and getattr(sm, "session_manager", None) is not None:
        extra_paths: list[str] | None = None
        raw_ui = (body.user_input or "").strip()
        if raw_ui:
            resolved_refs = await _resolve_request_attachment_paths(session_id, [raw_ui])
            extra_paths = resolved_refs or None
        att_extra = await tool_extra_for_chat_session(
            sm.session_manager,
            session_id,
            extra_paths=extra_paths,
        )
        tool_ctx.extra.update(att_extra)

    resolved = resolve_argument_templates(
        step.action.arguments,
        session_id=str(session_id),
        user_id=str(user_id),
        user_input=body.user_input or "",
    )

    executor = get_executor()
    if sm is not None:
        executor.set_service_manager(sm)

    result = await executor.run_tool(step.action.tool_id, resolved, tool_ctx)

    runs: dict[str, Any] = ext.get("chat_workflow_step_runs")
    if not isinstance(runs, dict):
        runs = {}
    step_entry: dict[str, Any] = {
        "status": "success" if result.success else "error",
    }
    if not result.success and result.error:
        step_entry["error"] = str(result.error)
    runs[step_id] = step_entry
    await chat_svc.merge_message_extensions(
        session_id,
        body.message_id,
        user_id=user_id,
        patch={"chat_workflow_step_runs": runs},
    )

    return {
        "success": result.success,
        "data": result.data,
        "error": result.error,
        "duration_ms": result.duration_ms,
    }


@router.get("/workflow-templates", response_model=list[ChatWorkflowTemplateRead])
async def list_chat_workflow_templates(
    _user_id: CurrentUserId,
) -> list[ChatWorkflowTemplateRead]:
    """Return curated, server-validated chat workflow templates (read-only tools only)."""
    from leagent.chat_workflow.templates import build_chat_workflow_template_catalog
    from leagent.tools.registry import get_registry

    catalog = build_chat_workflow_template_catalog(get_registry())
    return [ChatWorkflowTemplateRead(**row) for row in catalog]


@router.post("/workflow-templates/materialize", response_model=MaterializeWorkflowTemplatesResponse)
async def materialize_chat_workflow_templates(
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> MaterializeWorkflowTemplatesResponse:
    """Create a chat session with one assistant message per built-in template (runnable cards)."""
    from leagent.chat_workflow.templates import build_chat_workflow_template_catalog
    from leagent.tools.registry import get_registry

    session = await chat_svc.create_session(
        user_id,
        name="Chat workflow templates (test lab)",
    )
    catalog = build_chat_workflow_template_catalog(get_registry())
    rows: list[MaterializedTemplateRow] = []
    for item in catalog:
        ext = json.dumps({
            "chat_workflow": item["spec"],
            "chat_workflow_digest": item["digest"],
        })
        msg = await chat_svc.add_message(
            session.id,
            MessageRole.ASSISTANT,
            f"## {item['title']}\n\n{item.get('description', '')}",
            user_id=user_id,
            extensions=ext,
        )
        rows.append(MaterializedTemplateRow(template_id=item["id"], message_id=msg.id))
    return MaterializeWorkflowTemplatesResponse(session_id=session.id, templates=rows)


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: UUID,
    request: SendMessageRequest,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    db: Annotated[DatabaseService, Depends(get_database_service)],
):
    """Send a message in a session and get a response."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if not session.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not active")

    user_row = await chat_svc.add_message(
        session_id,
        request.role,
        request.content,
        user_id=user_id,
        attachments=request.attachments,
    )

    if request.stream:
        resolved_request_attachments = await _resolve_request_attachment_paths(
            session_id,
            request.attachments,
        )
        k_paths = await _resolve_knowledge_message_paths(user_id, db, request.content)
        merged_request_attachments = _merge_agent_attachment_paths(
            resolved_request_attachments, k_paths,
        )
        completion_request = ChatCompletionRequest(
            model=request.model or "default",
            messages=[ChatCompletionMessage(role=MessageRole.USER, content=request.content)],
            session_id=session_id,
            stream=True,
        )
        return EventSourceResponse(
            _generate_openai_sse(
                completion_request,
                session_id,
                user_id,
                chat_svc,
                attachments=merged_request_attachments,
                persisted_user_message_id=user_row.id,
            ),
            media_type="text/event-stream",
        )

    agent = build_agent_controller()
    if agent is not None:
        from leagent.services.chat.pet_personality import apply_pet_personality_to_agent
        await apply_pet_personality_to_agent(agent, db, user_id)
        resolved_request_attachments = await _resolve_request_attachment_paths(
            session_id,
            request.attachments,
        )
        k_paths = await _resolve_knowledge_message_paths(user_id, db, request.content)
        merged_request_attachments = _merge_agent_attachment_paths(
            resolved_request_attachments, k_paths,
        )
        msg_auth_roots = await _authorized_root_paths_for_session(
            chat_svc, session_id, user_id,
        )
        agent_response = await agent.run(
            request.content,
            session_id,
            user_id=user_id,
            attachments=merged_request_attachments,
            authorized_roots=msg_auth_roots,
            persisted_user_message_id=user_row.id,
        )
        response_content = agent_response.text
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No LLM provider configured. Please configure a model in Settings.",
        )

    assistant_message = await chat_svc.add_message(
        session_id,
        MessageRole.ASSISTANT,
        response_content,
        user_id=user_id,
        model=request.model or "default",
        output_tokens=len(response_content.split()),
    )
    return MessageRead.model_validate(assistant_message)


@router.post("/sessions/{session_id}/messages/upload")
async def send_message_with_attachments(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
    content: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
    stream: bool = Form(default=True),
    model: str | None = Form(default=None),
):
    """Send a message with file attachments."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    persisted_file_ids: list[str] = []
    if files:
        session_attachment_payloads, _uploaded_paths, _ingest_errors = await _attach_chat_files(
            user_id, session_id, files,
        )
        persisted_file_ids = [a["id"] for a in session_attachment_payloads]
        for err in _ingest_errors:
            logger.warning(
                "upload_attachment_error session=%s file=%s: %s",
                session_id, err["file"], err["error"],
            )

    if not (content or "").strip() and not persisted_file_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message text or at least one uploaded file is required.",
        )

    request = SendMessageRequest(
        content=content,
        stream=stream,
        model=model,
        attachments=persisted_file_ids if persisted_file_ids else None,
    )
    return await send_message(session_id, request, user_id, chat_svc)


# ---------------------------------------------------------------------------
# WebSocket Endpoint
# ---------------------------------------------------------------------------


class ConnectionManager(DistributedConnectionManager):
    def __init__(self) -> None:
        super().__init__()

    def attach_redis(self, redis: Any) -> None:
        pass

    @property
    def active_connections(self) -> dict[UUID, list[Any]]:  # type: ignore[override]
        return self._local


manager = ConnectionManager()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: UUID,
    chat_svc: ChatSvc,
    db: Annotated[DatabaseService, Depends(get_database_service)],
):
    """WebSocket endpoint for real-time chat."""
    token_str = websocket.query_params.get("token")
    if not token_str:
        await websocket.close(code=4001, reason="Authentication required")
        return

    from leagent.services.auth import get_auth_service

    auth_service = get_auth_service()
    user_id = auth_service.verify_access_token(token_str)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        await websocket.close(code=4003, reason="Session not found or access denied")
        return

    await manager.connect(websocket, session_id)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "ping":
                await manager.send_personal_message({"type": "pong"}, websocket)
                continue

            if msg_type == "message":
                content = data.get("content", "")
                model = data.get("model", "default")

                if not content:
                    await manager.send_personal_message(
                        {"type": "error", "error": "Empty message content"}, websocket,
                    )
                    continue

                user_message = await chat_svc.add_message(
                    session_id, MessageRole.USER, content, user_id=user_id,
                )

                await manager.send_personal_message(
                    {"type": "message_received", "message_id": str(user_message.id)},
                    websocket,
                )

                response_content = ""
                agent = build_agent_controller()

                if agent is not None:
                    from leagent.services.chat.pet_personality import apply_pet_personality_to_agent
                    await apply_pet_personality_to_agent(agent, db, user_id)
                    k_paths = await _resolve_knowledge_message_paths(user_id, db, content)
                    ws_attachments = _merge_agent_attachment_paths(None, k_paths)
                    ws_auth_roots = await _authorized_root_paths_for_session(
                        chat_svc, session_id, user_id,
                    )
                    ws_agent_task_id = uuid4()
                    await manager.send_personal_message(
                        {
                            "type": "agent_task",
                            "task_id": str(ws_agent_task_id),
                            "session_id": str(session_id),
                        },
                        websocket,
                    )
                    async for etype, edata, acc_text in _run_agent_stream(
                        agent,
                        content,
                        session_id,
                        user_id,
                        attachments=ws_attachments,
                        authorized_roots=ws_auth_roots,
                        persisted_user_message_id=user_message.id,
                        agent_task_id=ws_agent_task_id,
                    ):
                        response_content = acc_text
                        if etype == "token":
                            await manager.send_personal_message(
                                {"type": "stream", "content": edata.get("token", "")}, websocket,
                            )
                        elif etype in (
                            "thinking",
                            "tool_call",
                            "tool_call_delta",
                            "tool_result",
                            "nested_agent_preview",
                        ):
                            await manager.send_personal_message(
                                {"type": etype, **edata}, websocket,
                            )
                        elif etype == "error":
                            await manager.send_personal_message(
                                {"type": "error", "error": edata.get("error", "")}, websocket,
                            )
                else:
                    await manager.send_personal_message(
                        {"type": "error", "error": "No LLM provider configured"},
                        websocket,
                    )

                if response_content:
                    assistant_message = await chat_svc.add_message(
                        session_id,
                        MessageRole.ASSISTANT,
                        response_content,
                        user_id=user_id,
                        model=model,
                        output_tokens=len(response_content.split()),
                    )
                    await manager.send_personal_message(
                        {
                            "type": "complete",
                            "message_id": str(assistant_message.id),
                            "content": response_content,
                        },
                        websocket,
                    )

    except WebSocketDisconnect:
        manager.disconnect(websocket, session_id)
    except Exception as e:
        logger.exception("WebSocket error for session %s: %s", session_id, e)
        manager.disconnect(websocket, session_id)


# ---------------------------------------------------------------------------
# Daily empty-state greetings (LLM-generated, cached per locale / UTC day)
# ---------------------------------------------------------------------------


class DailyGreetingsResponse(BaseModel):
    """Ten rotating welcome lines for the empty chat hero + pet bubble acknowledgments."""

    date: str = Field(..., description="UTC calendar day (YYYY-MM-DD) this set is valid for")
    greetings: list[str] = Field(..., min_length=1, max_length=16)
    pet_bubbles: list[str] = Field(
        default_factory=list,
        min_length=0,
        max_length=16,
        description="Short post-reply pet speech-bubble lines (refreshed daily).",
    )


@router.get("/daily-greetings", response_model=DailyGreetingsResponse)
async def get_daily_greetings(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    locale: str = Query(
        default="en-US",
        description='UI locale tag (e.g. "zh-CN", "en-US"); controls output language.',
    ),
) -> DailyGreetingsResponse:
    from leagent.main import get_service_manager
    from leagent.services.chat.daily_greetings import (
        get_daily_greetings_for_locale,
        get_daily_pet_bubble_greetings,
    )
    from leagent.services.chat.pet_personality import get_active_pet_personality

    sm = get_service_manager()
    personality = await get_active_pet_personality(db, user_id)
    (day, lines), (_, pet_lines) = await asyncio.gather(
        get_daily_greetings_for_locale(sm.llm_service, locale),
        get_daily_pet_bubble_greetings(sm.llm_service, locale, personality=personality),
    )
    return DailyGreetingsResponse(date=day, greetings=lines, pet_bubbles=pet_lines)


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for the chat service."""
    return {"status": "healthy", "service": "chat"}
