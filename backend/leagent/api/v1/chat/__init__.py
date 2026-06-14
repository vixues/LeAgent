"""Chat API endpoints with SSE streaming and WebSocket support.

All persistence flows through :class:`ChatService` — endpoints never
open raw DB sessions for chat tables.  Agent orchestration uses
:func:`build_agent_controller` from ``chat_deps``.
"""

from __future__ import annotations

import asyncio
import json
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
from sse_starlette.sse import EventSourceResponse

from leagent.api.v1.chat_deps import ChatSvc, build_agent_controller
from leagent.apps.gateway.infrastructure.ws_fanout import (
    DistributedConnectionManager,
)
from leagent.schema.api import PaginatedResponse
from leagent.services.auth import CurrentUserId  # noqa: TC001
from leagent.db import DatabaseService, get_database_service
from leagent.services.chat.service import ChatService
from leagent.db.models.message import (
    MessageRead,
    MessageRole,
    SessionCreate,
    SessionRead,
    chat_session_to_read,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request/Response Models — defined in ``leagent.api.schemas.chat`` and
# re-exported here for backward compatibility.
# ---------------------------------------------------------------------------

from leagent.api.schemas.chat import (  # noqa: E402
    AgentMemoryEpisodeRead,
    AgentMemoryFactRead,
    AgentMemoryProcedureRead,
    AgentMemorySnapshotRead,
    AgentTaskItem,
    AgentTasksListResponse,
    AuthorizedPathCreateBody,
    AuthorizedPathEntry,
    AuthorizedPathsResponse,
    BrowseResponse as _BrowseResponse,
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionUsage,
    ChatWorkflowStepRunRequest,
    SessionExecutionRead,
    ChatWorkflowTemplateRead,
    CompactContextRequest,
    CompactContextResponse,
    DailyGreetingsResponse,
    DirEntry as _DirEntry,
    MaterializedTemplateRow,
    MaterializeWorkflowTemplatesResponse,
    MessageFeedbackBody,
    PromptLayerRead,
    PromptPreviewRead,
    SendMessageRequest,
    SessionAttachmentsResponse,
    ResumeCheckpointRequest,
    ResumeCheckpointResponse,
    SessionCancelResponse,
    SessionTodoStatusPatchRequest,
    SessionUpdateRequest,
)

# Business-logic helpers live in ``helpers.py``; re-exported for callers/tests.
# Cohesive, independently-reusable submodules replace the former ``helpers.py``
# junk drawer. The route-handler body and existing tests reference the legacy
# leading-underscore names, so we alias the public functions on import. New code
# should import the public names directly from their submodule, e.g.
# ``from leagent.api.v1.chat.sse import format_openai_chunk``.
from leagent.api.v1.chat.agent_stream import (  # noqa: E402,F401
    TASK_STATUS_RANK,
    run_agent_stream as _run_agent_stream,
)
from leagent.api.v1.chat.attachments import (  # noqa: E402,F401
    attach_chat_files as _attach_chat_files,
    merge_agent_attachment_paths as _merge_agent_attachment_paths,
    resolve_request_attachment_paths as _resolve_request_attachment_paths,
)
from leagent.api.v1.chat.context_sources import (  # noqa: E402,F401
    authorized_root_paths_for_session as _authorized_root_paths_for_session,
    context_item_paths as _context_item_paths,
    parse_knowledge_line_payload as _parse_knowledge_line_payload,
    resolve_folder_context as _resolve_folder_context,
    resolve_folder_context_note as _resolve_folder_context_note,
    resolve_knowledge_message_paths as _resolve_knowledge_message_paths,
    resolve_project_folder_path as _resolve_project_folder_path,
)
from leagent.api.v1.chat.message_persistence import (  # noqa: E402,F401
    merge_message_extensions_json as _merge_message_extensions_json,
    merge_stream_thinking_for_persist as _merge_stream_thinking_for_persist,
    parse_tool_replies_json as _parse_tool_replies_json,
)
from leagent.api.v1.chat.paths import (  # noqa: E402,F401
    attachment_local_path_for_sse as _attachment_local_path_for_sse,
    dedupe_resolved_paths as _dedupe_resolved_paths,
)
from leagent.api.v1.chat.sse import (  # noqa: E402,F401
    companion_sse_events as _companion_sse_events,
    format_frontend_event as _format_frontend_event,
    format_openai_chunk as _format_openai_chunk,
    openai_tool_call_from_stream_edata as _openai_tool_call_from_stream_edata,
    tokens_from_stream_usage as _tokens_from_stream_usage,
)


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
        yield _format_frontend_event("stream_start", {
            "session_id": str(parsed_session_id),
        })
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
                title_model_provider = selected_model_provider
                title_model_name = selected_model_name
                logger.debug(
                    "chat auto-title scheduled session=%s provider=%s model=%s",
                    sid,
                    title_model_provider,
                    title_model_name,
                )

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
                                model_provider=title_model_provider,
                                model_name=title_model_name,
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
                    elif etype == "session_todos":
                        yield _format_frontend_event("session_todos", edata)
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
                        _err_payload: dict[str, Any] = {
                            "message": edata.get("error", "Unknown error"),
                        }
                        _err_reason = edata.get("terminal_reason")
                        if _err_reason:
                            _err_payload["terminal_reason"] = _err_reason
                        yield _format_frontend_event("error", _err_payload)
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
            # Include terminal_reason + checkpoint_id so the frontend can show
            # differentiated end-of-turn UI (e.g. "turn limit reached") and a
            # checkpoint-based resume button.
            _complete_payload: dict[str, Any] = {}
            if last_complete_event:
                _tr = last_complete_event.get("terminal_reason")
                if _tr:
                    _complete_payload["terminal_reason"] = _tr
                _cpid = last_complete_event.get("checkpoint_id")
                if _cpid:
                    _complete_payload["checkpoint_id"] = _cpid
            yield _format_frontend_event("assistant_complete", _complete_payload)

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


@router.post("/sessions/{session_id}/resume-checkpoint", response_model=ResumeCheckpointResponse)
async def resume_checkpoint(
    session_id: UUID,
    body: ResumeCheckpointRequest,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> ResumeCheckpointResponse:
    """Accept a checkpoint-based resume request for a paused agent turn.

    The frontend sends the ``checkpoint_id`` it received on the
    ``assistant_complete`` SSE event together with the user's follow-up
    ``prompt``. This endpoint validates the checkpoint exists, then
    triggers a new streaming turn on the same session (via the normal
    ``/stream`` path with ``skip_append_user`` and the stored
    checkpoint's history). For now this is a "prepare + acknowledge"
    handshake; the actual streaming happens when the client posts to
    ``/stream`` with the ``checkpoint_id`` field.
    """
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    try:
        from leagent.sdk.kernel.checkpoint import build_checkpoint_store
        from leagent.services.service_manager import get_service_manager
        sm = get_service_manager()
        store = build_checkpoint_store(getattr(sm, "database_service", None))
        if store is None:
            from leagent.sdk.kernel.checkpoint import InMemoryCheckpointStore
            store = InMemoryCheckpointStore()
        cp = await store.load(body.checkpoint_id)
    except Exception:  # noqa: BLE001
        cp = None

    if cp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Checkpoint {body.checkpoint_id!r} not found",
        )

    return ResumeCheckpointResponse(
        session_id=str(session_id),
        checkpoint_id=body.checkpoint_id,
        accepted=True,
        message="Checkpoint validated; proceed with /stream using checkpoint_id",
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


@router.patch(
    "/sessions/{session_id}/todos/{todo_id}",
    response_model=SessionRead,
)
async def patch_session_todo_status(
    session_id: UUID,
    todo_id: str,
    body: SessionTodoStatusPatchRequest,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> SessionRead:
    """Update one session-scoped agent todo status (manual UI interaction)."""
    existing = await chat_svc.get_session(session_id, user_id=user_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    from leagent.main import get_service_manager

    try:
        sm = get_service_manager()
    except Exception:  # noqa: BLE001
        sm = None

    if sm is None or sm.session_manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session manager unavailable",
        )

    try:
        await sm.session_manager.update_todo_status(session_id, todo_id, body.status)
    except ValueError as exc:
        detail = str(exc)
        if "not found" in detail.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc

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
    from leagent.chat_workflow.arguments import (
        coerce_workflow_step_arguments,
        validate_workflow_step_paths,
    )
    from leagent.chat_workflow.schema import (
        ValidationError as ChatWorkflowValidationError,
        chat_workflow_digest,
        parse_chat_workflow_spec,
        resolve_argument_templates,
    )
    from leagent.main import get_service_manager
    from leagent.tools.base import ToolPermissionContext
    from leagent.tools.context import build_tool_context
    from leagent.tools.executor import get_executor
    from leagent.tools.registry import get_registry
    from leagent.file.attachment_context import tool_extra_for_chat_session

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
    resolved = coerce_workflow_step_arguments(step.action.tool_id, resolved, tool_ctx, registry=registry)
    path_error = validate_workflow_step_paths(
        step.action.tool_id, resolved, tool_ctx, registry=registry,
    )
    if path_error:
        runs: dict[str, Any] = ext.get("chat_workflow_step_runs")
        if not isinstance(runs, dict):
            runs = {}
        runs[step_id] = {"status": "error", "error": path_error}
        await chat_svc.merge_message_extensions(
            session_id,
            body.message_id,
            user_id=user_id,
            patch={"chat_workflow_step_runs": runs},
        )
        return {
            "success": False,
            "data": None,
            "error": path_error,
            "duration_ms": 0,
        }

    from leagent.chat_workflow.runner import run_chat_workflow_step_via_engine
    from leagent.runtime.execution_registry import get_execution_run_registry

    parent_run_id = body.parent_run_id
    if not parent_run_id:
        active = get_execution_run_registry().get_active_chat_turn(str(session_id))
        if active is not None:
            parent_run_id = active.run_id

    outcome = await run_chat_workflow_step_via_engine(
        spec=spec,
        step_id=step_id,
        resolved_args=resolved,
        tool_ctx=tool_ctx,
        service_manager=sm,
        user_id=str(user_id),
        session_id=str(session_id),
        parent_run_id=parent_run_id,
    )
    result = outcome.tool_result

    from datetime import datetime, timezone

    runs: dict[str, Any] = ext.get("chat_workflow_step_runs")
    if not isinstance(runs, dict):
        runs = {}
    step_entry: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if outcome.prompt_id:
        step_entry["status"] = "running"
    else:
        step_entry["status"] = "success" if result.success else "error"
        step_entry["completed_at"] = datetime.now(timezone.utc).isoformat()
    if outcome.prompt_id:
        step_entry["prompt_id"] = outcome.prompt_id
    if outcome.run_id:
        step_entry["run_id"] = outcome.run_id
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
        "prompt_id": outcome.prompt_id,
        "run_id": outcome.run_id,
    }


@router.get("/sessions/{session_id}/executions", response_model=list[SessionExecutionRead])
async def list_session_executions(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> list[SessionExecutionRead]:
    """Return active in-process execution runs for a chat session."""
    await chat_svc.get_session(session_id, user_id=user_id)
    from leagent.runtime.execution_registry import get_execution_run_registry

    runs = get_execution_run_registry().list_for_session(str(session_id))
    return [
        SessionExecutionRead(
            run_id=r.run_id,
            scope=r.scope.value,
            parent_run_id=r.parent_run_id,
            prompt_id=r.prompt_id,
            status="blocked" if r.pause_token else "running",
            pause_token=r.pause_token.to_dict() if r.pause_token else None,
        )
        for r in runs
    ]


@router.get("/workflow-templates", response_model=list[ChatWorkflowTemplateRead])
async def list_chat_workflow_templates(
    _user_id: CurrentUserId,
) -> list[ChatWorkflowTemplateRead]:
    """Return curated, server-validated chat workflow templates."""
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
            **({"playbook_id": item["playbook_id"]} if item.get("playbook_id") else {}),
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


def _resolve_ws_token(websocket: WebSocket) -> str | None:
    """Resolve the WS auth token.

    Prefers header-based transports that don't leak into access/proxy logs:
    ``Authorization: Bearer`` then ``Sec-WebSocket-Protocol`` (``bearer,<token>``),
    falling back to the legacy ``?token=`` query parameter for compatibility.
    """
    auth = websocket.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
        if tok:
            return tok
    proto = websocket.headers.get("sec-websocket-protocol") or ""
    if proto:
        parts = [p.strip() for p in proto.split(",") if p.strip()]
        if len(parts) >= 2 and parts[0].lower() in {"bearer", "authorization"}:
            return parts[1]
    return websocket.query_params.get("token")


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: UUID,
    chat_svc: ChatSvc,
    db: Annotated[DatabaseService, Depends(get_database_service)],
):
    """WebSocket endpoint for real-time chat."""
    token_str = _resolve_ws_token(websocket)
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


# Chat-service health is intentionally NOT exposed here. Health/liveness/
# readiness are consolidated on the dedicated ``/api/v1/health`` router and the
# root ``GET /health`` probe (see ``api/v1/health.py``).
