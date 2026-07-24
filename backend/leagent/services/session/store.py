"""Database-backed persistence for :class:`SessionState`.

**Single source of truth (SSOT).** The durable session state is the
``session_state_v1`` JSON blob stored on ``chat_sessions.session_metadata``.
:meth:`TieredSessionStore.load` materialises from that blob first and only
rehydrates from the ``messages`` table when the blob is absent (legacy rows).

The ``messages`` table is a **projection** for UI history queries, not the
authoritative transcript:

* User and assistant rows are written exactly once by
  ``ChatService.add_message`` (from the HTTP/stream handler) — the store never
  re-inserts them, eliminating the historical double-write.
* Only tool/system projection rows (which ``ChatService`` does not own) are
  written here, and only when missing (keyed on the stable message UUID).

When a database is configured, every read/write goes straight to it. An earlier
revision kept a process-local LRU in front of the database, which broke
multi-worker deployments: a turn handled by worker A would not be visible to
worker B, so a follow-up question in the same session could lose all prior
context. Session state reads are cheap single-row lookups, so the LRU wasn't
worth that correctness hazard.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import String, cast, text as sa_text
from sqlmodel import select

from leagent.db.models.base import naive_utc_for_db_column
from leagent.db.sqlite_compat import (
    load_chat_session_by_id,
    parse_uuid_stored,
    session_dialect_name,
    sqlite_parent_id_text,
)
from leagent.db.models.message import ChatSession, Message, MessageRole
from leagent.services.session.state import (
    SessionMessage,
    SessionState,
    SessionUsage,
)
from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from leagent.config.settings import Settings
    from leagent.db.service import DatabaseService

logger = get_logger(__name__)


def _as_utc_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _as_utc_naive_for_db(dt: datetime | None) -> datetime | None:
    """UTC as naive datetime for ``DateTime`` columns without time zone."""
    return naive_utc_for_db_column(dt)


def _normalize_chat_session_timestamps(chat: ChatSession) -> None:
    """Coerce `ChatSession` ORM fields to naive UTC (matches :class:`TimestampMixin`)."""
    if chat.created_at is not None:
        c = _as_utc_naive_for_db(chat.created_at)
        if c is not None:
            chat.created_at = c
    if chat.updated_at is not None:
        u = _as_utc_naive_for_db(chat.updated_at)
        if u is not None:
            chat.updated_at = u
    if chat.last_message_at is not None:
        lm = _as_utc_naive_for_db(chat.last_message_at)
        if lm is not None:
            chat.last_message_at = lm


_SESSION_METADATA_KEY = "session_state_v1"


def _role_to_enum(role: str) -> MessageRole:
    try:
        return MessageRole(role)
    except ValueError:
        return MessageRole.USER


class TieredSessionStore:
    """Database-backed read/write store for :class:`SessionState`.

    Named ``Tiered`` for historical/API-compatibility reasons (callers import
    this class name). Runtime deployments with a database always use the
    database as the single tier; a small in-memory fallback remains only for
    database-less tests/local callers.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        cache: Any | None = None,
        database: DatabaseService | None,
    ) -> None:
        self._settings = settings
        self._database = database
        self._memory_fallback: dict[UUID, SessionState] = {} if database is None else {}

    # -- public API -----------------------------------------------------

    async def load(self, session_id: UUID) -> SessionState | None:
        if self._database is None:
            return self._memory_fallback.get(session_id)
        return await self._load_from_database(session_id)

    async def save(self, state: SessionState) -> None:
        if self._database is None:
            self._memory_fallback[state.session_id] = state
            return
        await self._save_to_database(state)

    async def delete(self, session_id: UUID) -> None:
        if self._database is None:
            self._memory_fallback.pop(session_id, None)
        return None

    # -- database (SQLite / Postgres) -----------------------------------

    async def _load_from_database(self, session_id: UUID) -> SessionState | None:
        if self._database is None:
            return None
        try:
            async with self._database.session() as db:
                chat = await load_chat_session_by_id(
                    db, session_id, owner_user_id=None
                )
                if chat is None:
                    return None
                state = self._materialise_from_chat_session(chat)
                if state is None:
                    state = await self._rehydrate_from_messages(db, chat)
                return state
        except Exception as exc:  # noqa: BLE001
            logger.warning("session_store_database_load_failed: %s", exc)
            return None

    def _materialise_from_chat_session(
        self, chat: ChatSession
    ) -> SessionState | None:
        """Read the stashed JSON blob from ``chat_sessions.session_metadata``."""
        raw = chat.session_metadata
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        snapshot = data.get(_SESSION_METADATA_KEY) if isinstance(data, dict) else None
        if not snapshot:
            return None
        try:
            return SessionState.from_dict(snapshot)
        except Exception as exc:  # noqa: BLE001
            logger.warning("session_store_snapshot_decode_failed: %s", exc)
            return None

    async def _rehydrate_from_messages(
        self,
        db: Any,
        chat: ChatSession,
    ) -> SessionState:
        """Fallback: rebuild the transcript from the ``messages`` table."""
        if session_dialect_name(db) == "sqlite":
            s_txt = await sqlite_parent_id_text(db, "chat_sessions", chat.id)
            sid_eq = cast(Message.session_id, String) == s_txt
        else:
            sid_eq = Message.session_id == chat.id
        result = await db.exec(
            select(Message).where(sid_eq).order_by(Message.created_at.asc(), Message.id.asc())
        )
        rows = list(result.all())

        messages: list[SessionMessage] = []
        for row in rows:
            tool_calls: list[dict[str, Any]] | None = None
            if row.tool_calls:
                try:
                    tool_calls = json.loads(row.tool_calls)
                except (TypeError, ValueError):
                    tool_calls = None
            attachment_ids: list[str] = []
            if row.attachments:
                try:
                    attachment_ids = [str(a) for a in json.loads(row.attachments) or []]
                except (TypeError, ValueError):
                    attachment_ids = []
            reasoning_content: str | None = None
            if row.extensions:
                try:
                    ext = json.loads(row.extensions)
                except (TypeError, ValueError):
                    ext = None
                if isinstance(ext, dict):
                    rc = ext.get("reasoning_content")
                    if isinstance(rc, str) and rc.strip():
                        reasoning_content = rc
            messages.append(
                SessionMessage(
                    id=row.id,
                    role=row.role.value if hasattr(row.role, "value") else str(row.role),
                    content=row.content,
                    created_at=_as_utc_aware(row.created_at) or datetime.now(timezone.utc),
                    tool_calls=tool_calls,
                    tool_call_id=row.tool_call_id,
                    attachment_ids=attachment_ids,
                    model=row.model,
                    reasoning_content=reasoning_content,
                )
            )

        usage = SessionUsage(
            input_tokens=sum((r.input_tokens or 0) for r in rows),
            output_tokens=sum((r.output_tokens or 0) for r in rows),
            total_tokens=sum((r.total_tokens or 0) for r in rows),
            turns=sum(1 for r in rows if r.role == MessageRole.ASSISTANT),
        )

        return SessionState(
            session_id=chat.id,
            user_id=chat.user_id,
            workspace_id=chat.workspace_id,
            flow_id=chat.flow_id,
            messages=messages,
            attachments=[],
            file_state=[],
            usage=usage,
            created_at=_as_utc_aware(chat.created_at) or datetime.now(timezone.utc),
            updated_at=_as_utc_aware(chat.last_message_at or chat.updated_at)
            or datetime.now(timezone.utc),
        )

    async def _save_to_database(self, state: SessionState) -> None:
        if self._database is None:
            return
        now_db = _as_utc_naive_for_db(datetime.now(timezone.utc))
        last_at = _as_utc_naive_for_db(_as_utc_aware(state.updated_at)) or now_db
        try:
            async with self._database.session() as db:
                chat = await load_chat_session_by_id(
                    db, state.session_id, owner_user_id=None
                )
                if chat is None:
                    # ``chat_sessions.user_id`` is NOT NULL. Channel / background
                    # turns occasionally omit it; fall back to the local owner
                    # rather than failing the whole save with IntegrityError.
                    owner_id = state.user_id
                    if owner_id is None:
                        from leagent.services.auth.service import LOCAL_USER_ID

                        owner_id = LOCAL_USER_ID
                        state.user_id = owner_id
                    chat = ChatSession(
                        id=state.session_id,
                        user_id=owner_id,
                        flow_id=state.flow_id,
                        workspace_id=state.workspace_id,
                        message_count=len(state.messages),
                        last_message_at=last_at,
                    )
                    db.add(chat)
                else:
                    _normalize_chat_session_timestamps(chat)

                chat.message_count = len(state.messages)
                chat.last_message_at = last_at
                chat.session_metadata = json.dumps(
                    {_SESSION_METADATA_KEY: state.to_dict()},
                    ensure_ascii=False,
                )
                chat.updated_at = now_db

                # Persist only messages that don't already exist. We rely on
                # the message's primary key (UUID) to avoid duplicates —
                # ``SessionMessage.id`` is stable per message.
                if session_dialect_name(db) == "sqlite":
                    s_txt = await sqlite_parent_id_text(db, "chat_sessions", state.session_id)
                    sid_eq = cast(Message.session_id, String) == s_txt
                else:
                    sid_eq = Message.session_id == state.session_id
                existing_ids = await db.exec(select(Message.id).where(sid_eq))
                # ``exec(select(Model.id))`` may yield scalars (UUID) or
                # one-column Row tuples depending on SQLAlchemy/SQLModel version.
                existing = set()
                for r in existing_ids.all():
                    raw_id = r if isinstance(r, (UUID, str)) else r[0]
                    existing.add(parse_uuid_stored(str(raw_id)))

                for msg in state.messages:
                    mid = parse_uuid_stored(str(msg.id))
                    if mid in existing:
                        continue
                    role_enum = _role_to_enum(msg.role)
                    # User and assistant rows are persisted by :class:`ChatService`
                    # (``add_message`` in the HTTP/stream handler) before the agent
                    # runs.  Re-inserting them here would create duplicates whenever
                    # the controller assigns a new UUID due to index drift after
                    # trim / stub-injection.  The full transcript (including these
                    # roles) is already durable in the ``session_state_v1`` JSON
                    # blob written above; the ``messages`` table mirrors are for UI
                    # history queries only.
                    if role_enum in (MessageRole.ASSISTANT, MessageRole.USER):
                        continue
                    db.add(
                        Message(
                            id=msg.id,
                            session_id=state.session_id,
                            flow_id=state.flow_id,
                            user_id=state.user_id,
                            workspace_id=state.workspace_id,
                            role=_role_to_enum(msg.role),
                            content=msg.content,
                            model=msg.model,
                            tool_calls=(
                                json.dumps(msg.tool_calls) if msg.tool_calls else None
                            ),
                            tool_call_id=msg.tool_call_id,
                            attachments=(
                                json.dumps(msg.attachment_ids)
                                if msg.attachment_ids
                                else None
                            ),
                            created_at=_as_utc_naive_for_db(
                                _as_utc_aware(msg.created_at)
                            )
                            or now_db,
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("session_store_database_save_failed: %s", exc)

    async def list_sessions_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 50,
    ) -> list[SessionState]:
        """Return the most recently updated sessions for a user."""
        if self._database is None:
            return []
        try:
            async with self._database.session() as db:
                if session_dialect_name(db) == "sqlite":
                    u_txt = await sqlite_parent_id_text(db, "users", user_id)
                    r = await db.execute(
                        sa_text(
                            """
                            SELECT id FROM chat_sessions
                            WHERE CAST(user_id AS TEXT) = :u AND is_active = 1
                            ORDER BY (last_message_at IS NULL), last_message_at DESC,
                                     updated_at DESC
                            LIMIT :lim
                            """
                        ),
                        {"u": u_txt, "lim": limit},
                    )
                    id_rows = r.all()
                    ids = [parse_uuid_stored(str(row[0])) for row in id_rows]
                    if not ids:
                        rows = []
                    else:
                        res = await db.exec(
                            select(ChatSession).where(ChatSession.id.in_(ids))  # type: ignore[arg-type]
                        )
                        chats = list(res.all())
                        rank = {cid: i for i, cid in enumerate(ids)}
                        chats.sort(key=lambda c: rank.get(c.id, 999))
                        rows = chats
                else:
                    result = await db.exec(
                        select(ChatSession)
                        .where(ChatSession.user_id == user_id)
                        .where(ChatSession.is_active == True)  # noqa: E712
                        .order_by(ChatSession.last_message_at.desc().nulls_last())
                        .limit(limit)
                    )
                    rows = list(result.all())
        except Exception as exc:  # noqa: BLE001
            logger.warning("session_store_list_failed: %s", exc)
            return []

        states: list[SessionState] = []
        for chat in rows:
            materialised = self._materialise_from_chat_session(chat)
            if materialised is None:
                materialised = SessionState(
                    session_id=chat.id,
                    user_id=chat.user_id,
                    workspace_id=chat.workspace_id,
                    flow_id=chat.flow_id,
                    created_at=_as_utc_aware(chat.created_at) or datetime.now(timezone.utc),
                    updated_at=_as_utc_aware(chat.last_message_at or chat.updated_at)
                    or datetime.now(timezone.utc),
                )
            states.append(materialised)
        return states
