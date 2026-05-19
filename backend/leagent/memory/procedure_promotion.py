"""Write procedural memory only after the user likes an assistant message.

Calls :meth:`AgentMemory.record_procedure`, which delegates to
:class:`~leagent.memory.procedural.ProceduralStore` — the same stack as
historical ``TaskHistoryHook`` writes: upsert ``agent_procedures`` (SQL
database :class:`~leagent.services.database.models.agent_memory.AgentProcedure`)
plus embedding upsert to Milvus ``agent_memory_procedures`` (see
``procedural.COLLECTION_NAME``). Milvus failures are handled inside the store;
the database remains the source of truth for text, signature, and counters.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from leagent.memory.agent_memory import AgentMemory
from leagent.memory.procedural import build_signature
from leagent.memory.types import Procedure
from leagent.services.chat.service import ChatService
from leagent.services.database.models.message import MessageRole, MessageStatus

logger = logging.getLogger(__name__)

PROCEDURAL_PROMOTED_KEY = "procedural_memory_promoted_at"


def _tool_names_from_persisted_calls(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    names: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
            continue
        fn = item.get("function")
        if isinstance(fn, dict):
            fn_name = fn.get("name")
            if isinstance(fn_name, str) and fn_name.strip():
                names.append(fn_name.strip())
    return names


def _infer_task_type(tool_names: set[str]) -> str:
    if any("pdf" in t or "word" in t or "excel" in t for t in tool_names):
        return "document_processing"
    if any("web" in t or "scrape" in t for t in tool_names):
        return "web_automation"
    if any("data" in t or "validate" in t for t in tool_names):
        return "data_processing"
    if any("report" in t or "generate" in t for t in tool_names):
        return "generation"
    return "general"


def _extensions_dict(extensions: str | None) -> dict[str, Any]:
    if not extensions:
        return {}
    try:
        parsed = json.loads(extensions)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def record_procedure_for_liked_assistant(
    *,
    chat_svc: ChatService,
    agent_memory: AgentMemory | None,
    enable_memory: bool,
    session_id: UUID,
    assistant_message_id: UUID,
    user_id: UUID,
) -> tuple[bool, str | None, bool, dict[str, Any]]:
    """Persist a :class:`Procedure` for a liked assistant turn (idempotent).

    Returns ``(ok, error_detail, wrote_procedure, status)``. *wrote_procedure*
    is ``True`` only when a new :meth:`AgentMemory.record_procedure` ran.
    """
    if not enable_memory or agent_memory is None:
        return True, None, False, {"degraded": True, "reason": "memory_disabled"}

    msg = await chat_svc.get_session_message(session_id, assistant_message_id, user_id=user_id)
    if msg is None:
        return False, "message_not_found", False, {"degraded": False}

    ext = _extensions_dict(msg.extensions)
    if ext.get(PROCEDURAL_PROMOTED_KEY):
        return True, None, False, {"degraded": False, "reason": "already_promoted"}

    tool_chain = _tool_names_from_persisted_calls(msg.tool_calls)
    if not tool_chain:
        return True, None, False, {"degraded": False, "reason": "no_tool_calls"}

    user_row = None
    if msg.parent_id:
        parent = await chat_svc.get_session_message(session_id, msg.parent_id, user_id=user_id)
        if parent is not None and parent.role == MessageRole.USER:
            user_row = parent
    if user_row is None:
        user_row = await chat_svc.find_previous_user_message(
            session_id,
            before_created_at=msg.created_at,
            user_id=user_id,
        )
    intent = (user_row.content[:200] if user_row and user_row.content else "").strip() or (
        "(no user text)"
    )
    output_summary = (msg.content or "")[:200] or "No output"
    tool_names = set(tool_chain)
    task_kind = _infer_task_type(tool_names)
    tools_line = ", ".join(tool_chain) if tool_chain else "(no tools)"
    description = (
        f"[{task_kind}] {intent}\n→ {output_summary}\nTools: {tools_line}"
    )[:4000]

    procedure = Procedure(
        name=f"{task_kind} run",
        signature=build_signature(intent, tool_chain),
        description=description,
        user_id=user_id,
        workspace_id=None,
    )

    success = msg.status == MessageStatus.COMPLETED and not (msg.error or "").strip()
    duration_ms = msg.latency_ms

    try:
        await agent_memory.record_procedure(
            procedure,
            outcome=output_summary,
            success=bool(success),
            error=msg.error,
            duration_ms=duration_ms,
        )
        status = agent_memory.procedure_write_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("procedure_promotion_failed: %s", exc)
        return False, "record_procedure_failed", False, {"degraded": True, "error": str(exc)}
    if status.get("pg_written") is False:
        return False, "record_procedure_failed", False, status

    ts = datetime.now(timezone.utc).isoformat()
    await chat_svc.merge_message_extensions(
        session_id,
        assistant_message_id,
        user_id=user_id,
        patch={PROCEDURAL_PROMOTED_KEY: ts},
    )
    return True, None, True, status
