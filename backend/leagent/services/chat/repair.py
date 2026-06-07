"""One-time repair utility to deduplicate user message rows.

The dual-writer bug (ChatService + TieredSessionStore) caused duplicate
rows in the ``messages`` table — same ``(session_id, role, content)``
but different UUIDs.  This module provides :func:`deduplicate_user_messages`
which keeps the oldest row per ``(session_id, content)`` for user messages
and deletes the rest, then reconciles ``chat_sessions.message_count``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, text
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from leagent.services.database.models.message import (
    ChatSession,
    Message,
    MessageRole,
)

logger = logging.getLogger(__name__)


async def deduplicate_user_messages(
    db_session: AsyncSession,
    *,
    session_id: UUID | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Remove duplicate USER rows, keeping the earliest per (session_id, content).

    Args:
        db_session: An active SQLAlchemy async session (caller manages commit/rollback).
        session_id: Limit repair to a single chat session.  ``None`` = all sessions.
        dry_run: When ``True``, compute what *would* be deleted but do not mutate.

    Returns:
        A summary dict: ``{"sessions_affected", "duplicates_found", "rows_deleted",
        "message_counts_updated", "details"}``.
    """
    session_filter = (
        col(Message.session_id) == session_id if session_id else True
    )

    # Find (session_id, content) groups with more than one USER row.
    dup_query = (
        select(
            Message.session_id,
            Message.content,
            func.count(Message.id).label("cnt"),
        )
        .where(Message.role == MessageRole.USER, session_filter)
        .group_by(Message.session_id, Message.content)
        .having(func.count(Message.id) > 1)
    )

    dup_result = await db_session.execute(dup_query)
    dup_groups = dup_result.all()

    if not dup_groups:
        return {
            "sessions_affected": 0,
            "duplicates_found": 0,
            "rows_deleted": 0,
            "message_counts_updated": 0,
            "details": [],
        }

    total_deleted = 0
    affected_sessions: set[UUID] = set()
    details: list[dict[str, Any]] = []

    for row in dup_groups:
        sid = row.session_id
        content = row.content
        group_count = row.cnt

        # Fetch all IDs ordered by created_at to keep the oldest.
        ids_query = (
            select(Message.id)
            .where(
                Message.session_id == sid,
                Message.role == MessageRole.USER,
                Message.content == content,
            )
            .order_by(col(Message.created_at).asc(), col(Message.id).asc())
        )
        ids_result = await db_session.execute(ids_query)
        all_ids = [r[0] for r in ids_result.all()]

        keep_id = all_ids[0]
        delete_ids = all_ids[1:]

        if delete_ids and not dry_run:
            await db_session.execute(
                delete(Message).where(col(Message.id).in_(delete_ids))
            )

        total_deleted += len(delete_ids)
        affected_sessions.add(sid)
        details.append({
            "session_id": str(sid),
            "content_preview": (content or "")[:80],
            "total_rows": group_count,
            "kept_id": str(keep_id),
            "deleted_count": len(delete_ids),
        })
        logger.info(
            "dedup_user_messages: session=%s kept=%s deleted=%d content=%s",
            sid,
            keep_id,
            len(delete_ids),
            (content or "")[:60],
        )

    # Reconcile message_count on affected sessions.
    counts_updated = 0
    for sid in affected_sessions:
        if dry_run:
            continue
        actual_count_result = await db_session.execute(
            select(func.count(Message.id)).where(Message.session_id == sid)
        )
        actual_count = actual_count_result.scalar_one()

        cs_result = await db_session.execute(
            select(ChatSession).where(col(ChatSession.id) == sid)
        )
        chat_session = cs_result.scalar_one_or_none()
        if chat_session and chat_session.message_count != actual_count:
            logger.info(
                "dedup_user_messages: session=%s message_count %d -> %d",
                sid,
                chat_session.message_count,
                actual_count,
            )
            chat_session.message_count = actual_count
            db_session.add(chat_session)
            counts_updated += 1

    return {
        "sessions_affected": len(affected_sessions),
        "duplicates_found": sum(d["deleted_count"] for d in details),
        "rows_deleted": total_deleted if not dry_run else 0,
        "message_counts_updated": counts_updated,
        "details": details,
    }
