"""Chat-side handling for tool approval replies (Codex-style approvals).

When a turn pauses with an ``approval_request`` (see
``leagent.agent.query._approval_pause_terminal``), the user's Allow/Deny
answer arrives through the normal ``tool_replies`` channel. This module:

* detects that a reply answers a pending approval,
* records the grant in the runtime :class:`ApprovalStore`,
* rewrites the reply content into the structured guidance the model
  needs to re-issue (or abandon) the gated call, and
* writes a durable ``approval_decisions`` audit row.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from leagent.tools.approval import (
    PendingApproval,
    approval_reply_content,
    get_approval_store,
    parse_approval_decision,
)

logger = structlog.get_logger(__name__)


def transform_approval_reply(
    session_id: UUID | None,
    tool_reply: dict[str, Any],
) -> tuple[str, PendingApproval | None, str | None]:
    """Return ``(content, pending, decision)`` for a tool reply.

    If the reply answers the session's pending approval request, the
    content is replaced with model-facing guidance and the grant is
    recorded. Otherwise the original content passes through unchanged.
    """
    content = str(tool_reply.get("content") or "")
    call_id = str(tool_reply.get("tool_call_id") or "")
    if session_id is None or not call_id:
        return content, None, None

    store = get_approval_store()
    pending = store.get_pending(str(session_id))
    if pending is None or pending.tool_call_id != call_id:
        return content, None, None

    decision = parse_approval_decision(content)
    if decision is None:
        # Ambiguous free-text answer to an approval card: treat as deny
        # (fail-safe) but keep the user's words visible to the model.
        logger.warning(
            "approval_reply_unparsed", session_id=str(session_id), content=content[:100],
        )
        decision = "deny"

    store.pop_pending(str(session_id), tool_call_id=call_id)
    if decision == "allow_session":
        store.grant(str(session_id), pending.tool_name, scope="session")
    elif decision == "allow_once":
        store.grant(str(session_id), pending.tool_name, scope="once")

    logger.info(
        "approval_decision",
        session_id=str(session_id),
        tool=pending.tool_name,
        decision=decision,
    )
    return approval_reply_content(decision, pending.tool_name), pending, decision


async def audit_approval_decision(
    *,
    session_id: UUID | None,
    user_id: Any,
    pending: PendingApproval,
    decision: str,
    decided_by: str = "user",
) -> None:
    """Persist the decision to ``approval_decisions`` (best effort)."""
    try:
        from leagent.main import get_service_manager

        sm = get_service_manager()
        db = getattr(sm, "database_service", None) if sm else None
        if db is None:
            return
        from leagent.db.models.approval_decision import ApprovalDecisionLog

        row = ApprovalDecisionLog(
            session_id=str(session_id) if session_id else None,
            user_id=str(user_id) if user_id else None,
            tool_call_id=pending.tool_call_id,
            tool_name=pending.tool_name,
            params_digest=pending.params_digest,
            params_summary=(pending.detail or None),
            reason=(pending.reason or None)[:1000] if pending.reason else None,
            decision=decision,
            scope="session" if decision == "allow_session" else "once",
            decided_by=decided_by,
        )
        async with db.session() as s:
            s.add(row)
            await s.commit()
    except Exception:  # noqa: BLE001
        logger.warning("approval_audit_write_failed", exc_info=True)
