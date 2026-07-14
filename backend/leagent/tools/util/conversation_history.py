"""Extract chat conversation history for work summaries and follow-ups.

Agents use this read-only tool to pull durable chat transcripts (sessions +
messages) owned by the current user, typically before drafting a weekly report
or reconciling completed / in-progress work.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.context import resolve_effective_user_id

logger = structlog.get_logger(__name__)

_DEFAULT_ROLES = ("user", "assistant")
_MAX_SESSION_SCAN = 200
_DEFAULT_MAX_SESSIONS = 20
_DEFAULT_MAX_MESSAGES_PER_SESSION = 80
_DEFAULT_MAX_CHARS_PER_MESSAGE = 1_500
_DEFAULT_TOTAL_CHARS = 60_000


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize DB/naive timestamps to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_datetime(value: Any, *, end_of_day: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(
                f"Invalid datetime '{value}'. Use ISO-8601 or YYYY-MM-DD."
            ) from exc
        if end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59)
    return _as_utc(parsed)


def _iso(dt: datetime | None) -> str | None:
    utc = _as_utc(dt)
    return utc.isoformat() if utc is not None else None


def _truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[: max(0, max_chars - 1)] + "…", True


def _content_matches(content: str, query: str | None) -> bool:
    if not query:
        return True
    return query.casefold() in content.casefold()


def _resolve_window(params: dict[str, Any]) -> tuple[datetime, datetime]:
    until = _parse_iso_datetime(params.get("until"), end_of_day=True) or datetime.now(
        timezone.utc
    )
    since = _parse_iso_datetime(params.get("since"))
    if since is None:
        days_raw = params.get("days", 7)
        try:
            days = int(days_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("days must be an integer") from exc
        if days < 1 or days > 365:
            raise ValueError("days must be between 1 and 365")
        since = until - timedelta(days=days)
    if since > until:
        raise ValueError("since must be <= until")
    return since, until


def _in_window(ts: datetime | None, since: datetime, until: datetime) -> bool:
    utc = _as_utc(ts)
    if utc is None:
        return False
    return since <= utc <= until


class ConversationHistoryTool(BaseTool):
    """List sessions and extract conversation transcripts for the current user."""

    name = "conversation_history"
    description = (
        "Extract the current user's chat history for work summaries and follow-ups. "
        "Use operation=list to browse sessions in a time window, operation=get to "
        "load one session's transcript, or operation=extract (recommended for weekly "
        "reports) to pull user/assistant turns across recent sessions. Always call "
        "this before summarizing completed work, in-progress tasks, or follow-ups "
        "from prior chats — do not invent history."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    is_read_only = True
    is_concurrency_safe = True
    aliases = [
        "chat_history",
        "extract_conversation",
        "list_chat_sessions",
        "get_chat_history",
    ]
    search_hint = (
        "conversation chat history extract sessions messages weekly work summary "
        "report transcript"
    )
    interrupt_behavior = "cancel"
    max_result_size_chars = 120_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "extract")
        return f"Extracting conversation history ({op})"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["list", "get", "extract"],
                    "description": (
                        "list: session metadata in a time window; "
                        "get: messages for one session_id (defaults to current); "
                        "extract: cross-session transcripts for work summaries "
                        "(default)."
                    ),
                    "default": "extract",
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "Target session for operation=get. Defaults to the "
                        "current chat session when omitted."
                    ),
                },
                "days": {
                    "type": "integer",
                    "description": (
                        "Look-back window in days when since is omitted "
                        "(default 7, max 365). Used by list/extract."
                    ),
                    "minimum": 1,
                    "maximum": 365,
                    "default": 7,
                },
                "since": {
                    "type": "string",
                    "description": "Inclusive start time (ISO-8601 or YYYY-MM-DD).",
                },
                "until": {
                    "type": "string",
                    "description": (
                        "Inclusive end time (ISO-8601 or YYYY-MM-DD). Defaults to now."
                    ),
                },
                "query": {
                    "type": "string",
                    "description": (
                        "Optional case-insensitive substring filter on message content."
                    ),
                },
                "roles": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["user", "assistant", "system", "tool"],
                    },
                    "description": (
                        "Message roles to include. Default: user and assistant "
                        "(excludes tool/system noise)."
                    ),
                    "default": list(_DEFAULT_ROLES),
                },
                "include_current": {
                    "type": "boolean",
                    "description": (
                        "For list/extract: include the current session "
                        "(default true)."
                    ),
                    "default": True,
                },
                "max_sessions": {
                    "type": "integer",
                    "description": "Max sessions for list/extract (default 20).",
                    "minimum": 1,
                    "maximum": 100,
                    "default": _DEFAULT_MAX_SESSIONS,
                },
                "max_messages_per_session": {
                    "type": "integer",
                    "description": (
                        "Max messages per session for get/extract (default 80)."
                    ),
                    "minimum": 1,
                    "maximum": 500,
                    "default": _DEFAULT_MAX_MESSAGES_PER_SESSION,
                },
                "max_chars_per_message": {
                    "type": "integer",
                    "description": (
                        "Truncate each message body to this many characters "
                        f"(default {_DEFAULT_MAX_CHARS_PER_MESSAGE})."
                    ),
                    "minimum": 100,
                    "maximum": 20_000,
                    "default": _DEFAULT_MAX_CHARS_PER_MESSAGE,
                },
            },
            "required": [],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            operation = str(params.get("operation") or "extract").strip().lower()
            if operation not in {"list", "get", "extract"}:
                return {
                    "error": (
                        f"Unsupported operation '{operation}'. "
                        "Use list, get, or extract."
                    )
                }

            from leagent.main import get_service_manager

            sm = get_service_manager()
            chat = getattr(sm, "chat", None)
            session_manager = getattr(sm, "session_manager", None)
            if chat is None and session_manager is None:
                return {"error": "Chat/session services unavailable"}

            user_id = resolve_effective_user_id(
                context.user_id, session_id=context.session_id
            )
            if user_id is None:
                return {"error": "user_id is required to read conversation history"}

            roles = _normalize_roles(params.get("roles"))
            query = params.get("query")
            query_str = str(query).strip() if query else None
            max_chars = int(
                params.get("max_chars_per_message") or _DEFAULT_MAX_CHARS_PER_MESSAGE
            )
            max_messages = int(
                params.get("max_messages_per_session")
                or _DEFAULT_MAX_MESSAGES_PER_SESSION
            )

            if operation == "get":
                return await self._op_get(
                    chat=chat,
                    session_manager=session_manager,
                    context=context,
                    user_id=user_id,
                    session_id_raw=params.get("session_id"),
                    roles=roles,
                    query=query_str,
                    max_messages=max_messages,
                    max_chars=max_chars,
                    since=_parse_iso_datetime(params.get("since")),
                    until=_parse_iso_datetime(params.get("until"), end_of_day=True),
                )

            since, until = _resolve_window(params)
            include_current = params.get("include_current", True)
            if not isinstance(include_current, bool):
                return {"error": "include_current must be a boolean when provided"}
            max_sessions = int(params.get("max_sessions") or _DEFAULT_MAX_SESSIONS)

            sessions = await self._list_sessions_in_window(
                chat=chat,
                session_manager=session_manager,
                user_id=user_id,
                since=since,
                until=until,
                current_session_id=context.session_id,
                include_current=include_current,
                max_sessions=max_sessions,
            )

            if operation == "list":
                return {
                    "operation": "list",
                    "window": {"since": _iso(since), "until": _iso(until)},
                    "sessions": [
                        {
                            "session_id": str(s["id"]),
                            "name": s.get("name"),
                            "message_count": s.get("message_count", 0),
                            "last_message_at": _iso(s.get("last_message_at")),
                            "updated_at": _iso(s.get("updated_at")),
                            "created_at": _iso(s.get("created_at")),
                            "is_current": s.get("is_current", False),
                        }
                        for s in sessions
                    ],
                    "count": len(sessions),
                    "hint": (
                        "Pick session_id values and call conversation_history "
                        "with operation=get, or use operation=extract to pull "
                        "transcripts in one step."
                    ),
                }

            return await self._op_extract(
                chat=chat,
                session_manager=session_manager,
                user_id=user_id,
                sessions=sessions,
                since=since,
                until=until,
                roles=roles,
                query=query_str,
                max_messages=max_messages,
                max_chars=max_chars,
            )
        except ValueError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            logger.error("conversation_history_failed", error=str(exc))
            return {"error": str(exc)}

    async def _op_get(
        self,
        *,
        chat: Any,
        session_manager: Any,
        context: ToolContext,
        user_id: UUID,
        session_id_raw: Any,
        roles: set[str],
        query: str | None,
        max_messages: int,
        max_chars: int,
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, Any]:
        sid_text = str(session_id_raw or context.session_id or "").strip()
        if not sid_text:
            return {
                "error": (
                    "session_id is required for operation=get when not running "
                    "inside a chat session"
                )
            }
        try:
            session_id = UUID(sid_text)
        except ValueError:
            return {"error": f"Invalid session_id: {sid_text}"}

        meta = await self._load_session_meta(
            chat=chat,
            session_manager=session_manager,
            session_id=session_id,
            user_id=user_id,
        )
        if meta is None:
            return {"error": f"Session not found or not owned by user: {session_id}"}

        messages, truncated, source = await self._load_messages(
            chat=chat,
            session_manager=session_manager,
            session_id=session_id,
            roles=roles,
            query=query,
            max_messages=max_messages,
            max_chars=max_chars,
            since=since,
            until=until,
        )
        return {
            "operation": "get",
            "session": {
                "session_id": str(session_id),
                "name": meta.get("name"),
                "message_count": meta.get("message_count"),
                "last_message_at": _iso(meta.get("last_message_at")),
            },
            "messages": messages,
            "count": len(messages),
            "truncated": truncated,
            "source": source,
        }

    async def _op_extract(
        self,
        *,
        chat: Any,
        session_manager: Any,
        user_id: UUID,
        sessions: list[dict[str, Any]],
        since: datetime,
        until: datetime,
        roles: set[str],
        query: str | None,
        max_messages: int,
        max_chars: int,
    ) -> dict[str, Any]:
        bundles: list[dict[str, Any]] = []
        total_messages = 0
        any_truncated = False
        total_chars = 0
        budget_hit = False

        for meta in sessions:
            if budget_hit:
                any_truncated = True
                break
            session_id = meta["id"]
            messages, truncated, source = await self._load_messages(
                chat=chat,
                session_manager=session_manager,
                session_id=session_id,
                roles=roles,
                query=query,
                max_messages=max_messages,
                max_chars=max_chars,
                since=since,
                until=until,
            )
            if truncated:
                any_truncated = True
            if not messages:
                continue

            kept: list[dict[str, Any]] = []
            for msg in messages:
                body = str(msg.get("content") or "")
                if total_chars + len(body) > _DEFAULT_TOTAL_CHARS:
                    any_truncated = True
                    budget_hit = True
                    break
                kept.append(msg)
                total_chars += len(body)

            if not kept:
                continue

            bundles.append(
                {
                    "session_id": str(session_id),
                    "name": meta.get("name"),
                    "is_current": meta.get("is_current", False),
                    "last_message_at": _iso(meta.get("last_message_at")),
                    "message_count": len(kept),
                    "messages": kept,
                    "source": source,
                }
            )
            total_messages += len(kept)

        return {
            "operation": "extract",
            "window": {"since": _iso(since), "until": _iso(until)},
            "sessions": bundles,
            "stats": {
                "session_count": len(bundles),
                "message_count": total_messages,
                "truncated": any_truncated,
                "roles": sorted(roles),
                "query": query,
            },
            "hint": (
                "Summarize completed items, in-progress work, follow-ups, and "
                "key conclusions. Prefer GenUI for a scannable weekly report. "
                "Cite session names/ids when useful; do not invent missing history."
            ),
        }

    async def _list_sessions_in_window(
        self,
        *,
        chat: Any,
        session_manager: Any,
        user_id: UUID,
        since: datetime,
        until: datetime,
        current_session_id: str | None,
        include_current: bool,
        max_sessions: int,
    ) -> list[dict[str, Any]]:
        current_uuid: UUID | None = None
        if current_session_id:
            try:
                current_uuid = UUID(str(current_session_id))
            except ValueError:
                current_uuid = None

        rows: list[dict[str, Any]] = []
        if chat is not None and hasattr(chat, "list_sessions"):
            offset = 0
            while len(rows) < max_sessions and offset < _MAX_SESSION_SCAN:
                batch = await chat.list_sessions(
                    user_id,
                    active_only=True,
                    offset=offset,
                    limit=min(50, _MAX_SESSION_SCAN - offset),
                )
                if not batch:
                    break
                for s in batch:
                    ts = _as_utc(getattr(s, "last_message_at", None)) or _as_utc(
                        getattr(s, "updated_at", None)
                    )
                    sid = getattr(s, "id")
                    is_current = current_uuid is not None and sid == current_uuid
                    if is_current and not include_current:
                        continue
                    if not is_current and not _in_window(ts, since, until):
                        # Sessions are ordered by updated_at DESC; once we leave
                        # the window and have at least one match, further pages
                        # are unlikely to re-enter it. Still scan a full page.
                        if ts is not None and ts < since and rows:
                            continue
                        if ts is not None and ts < since:
                            continue
                        if ts is not None and ts > until:
                            continue
                    rows.append(
                        {
                            "id": sid,
                            "name": getattr(s, "name", None),
                            "message_count": getattr(s, "message_count", 0),
                            "last_message_at": getattr(s, "last_message_at", None),
                            "updated_at": getattr(s, "updated_at", None),
                            "created_at": getattr(s, "created_at", None),
                            "is_current": is_current,
                        }
                    )
                    if len(rows) >= max_sessions:
                        break
                if len(batch) < 50:
                    break
                offset += len(batch)
        elif session_manager is not None and hasattr(session_manager, "store"):
            states = await session_manager.store.list_sessions_for_user(
                user_id, limit=_MAX_SESSION_SCAN
            )
            for state in states:
                ts = None
                if state.messages:
                    ts = _as_utc(state.messages[-1].created_at)
                is_current = current_uuid is not None and state.session_id == current_uuid
                if is_current and not include_current:
                    continue
                if not is_current and not _in_window(ts, since, until):
                    continue
                rows.append(
                    {
                        "id": state.session_id,
                        "name": (state.metadata or {}).get("name"),
                        "message_count": len(state.messages),
                        "last_message_at": ts,
                        "updated_at": ts,
                        "created_at": None,
                        "is_current": is_current,
                    }
                )
                if len(rows) >= max_sessions:
                    break

        rows.sort(
            key=lambda r: _as_utc(r.get("last_message_at") or r.get("updated_at"))
            or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return rows[:max_sessions]

    async def _load_session_meta(
        self,
        *,
        chat: Any,
        session_manager: Any,
        session_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any] | None:
        if chat is not None and hasattr(chat, "get_session"):
            session = await chat.get_session(session_id, user_id=user_id)
            if session is None:
                return None
            return {
                "name": getattr(session, "name", None),
                "message_count": getattr(session, "message_count", None),
                "last_message_at": getattr(session, "last_message_at", None),
            }
        if session_manager is not None:
            state = await session_manager.load(session_id)
            if state is None:
                return None
            if state.user_id is not None and state.user_id != user_id:
                return None
            last = state.messages[-1].created_at if state.messages else None
            return {
                "name": (state.metadata or {}).get("name"),
                "message_count": len(state.messages),
                "last_message_at": last,
            }
        return None

    async def _load_messages(
        self,
        *,
        chat: Any,
        session_manager: Any,
        session_id: UUID,
        roles: set[str],
        query: str | None,
        max_messages: int,
        max_chars: int,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[list[dict[str, Any]], bool, str]:
        """Return (messages, truncated, source)."""
        # Prefer SessionManager (SSOT) when present.
        if session_manager is not None:
            state = await session_manager.load(session_id)
            if state is not None:
                out: list[dict[str, Any]] = []
                truncated = False
                for msg in state.messages:
                    role = str(msg.role or "").lower()
                    if role not in roles:
                        continue
                    created = _as_utc(msg.created_at)
                    if since is not None and (created is None or created < since):
                        continue
                    if until is not None and (created is None or created > until):
                        continue
                    content = msg.content or ""
                    if not _content_matches(content, query):
                        continue
                    body, was_cut = _truncate(content, max_chars)
                    truncated = truncated or was_cut
                    out.append(
                        {
                            "role": role,
                            "content": body,
                            "created_at": _iso(created),
                            "message_id": str(msg.id) if getattr(msg, "id", None) else None,
                        }
                    )
                if len(out) > max_messages:
                    out = out[-max_messages:]
                    truncated = True
                return out, truncated, "session_manager"

        if chat is None or not hasattr(chat, "get_messages_paginated"):
            return [], False, "none"

        page_size = min(100, max_messages)
        items, _total = await chat.get_messages_paginated(
            session_id,
            page=1,
            page_size=page_size,
            before=until,
            after=since,
            order="asc",
        )
        out = []
        truncated = False
        for msg in items:
            role_val = getattr(msg, "role", None)
            role = (
                role_val.value
                if hasattr(role_val, "value")
                else str(role_val or "")
            ).lower()
            if role not in roles:
                continue
            content = getattr(msg, "content", "") or ""
            if not _content_matches(content, query):
                continue
            body, was_cut = _truncate(content, max_chars)
            truncated = truncated or was_cut
            out.append(
                {
                    "role": role,
                    "content": body,
                    "created_at": _iso(getattr(msg, "created_at", None)),
                    "message_id": str(getattr(msg, "id", "")) or None,
                }
            )
        if len(out) > max_messages:
            out = out[-max_messages:]
            truncated = True
        return out, truncated, "chat_service"


def _normalize_roles(raw: Any) -> set[str]:
    if raw is None:
        return set(_DEFAULT_ROLES)
    if not isinstance(raw, list) or not raw:
        raise ValueError("roles must be a non-empty array when provided")
    allowed = {"user", "assistant", "system", "tool"}
    roles = {str(r).strip().lower() for r in raw}
    unknown = roles - allowed
    if unknown:
        raise ValueError(f"Unsupported roles: {sorted(unknown)}")
    return roles
