"""Chat persistence repository (sessions + messages)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlmodel import select

from leagent.db.models.message import ChatSession, Message

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService


class ChatRepository(Protocol):
    """Protocol for chat session/message persistence."""

    async def get_session(self, session_id: UUID) -> ChatSession | None:
        """Return a chat session by id."""
        ...

    async def get_session_for_user(
        self, session_id: UUID, user_id: UUID
    ) -> ChatSession | None:
        """Return a chat session owned by *user_id*."""
        ...

    async def list_sessions_for_user(
        self, user_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[ChatSession]:
        """Return active chat sessions owned by *user_id*."""
        ...

    async def list_messages(
        self, session_id: UUID, *, limit: int = 200
    ) -> list[Message]:
        """Return messages for *session_id* in chronological order."""
        ...


class DbChatRepository:
    """``DatabaseService``-backed :class:`ChatRepository`."""

    def __init__(self, db: "DatabaseService") -> None:
        self._db = db

    async def get_session(self, session_id: UUID) -> ChatSession | None:
        async with self._db.session() as session:
            return await session.get(ChatSession, session_id)

    async def get_session_for_user(
        self, session_id: UUID, user_id: UUID
    ) -> ChatSession | None:
        async with self._db.session() as session:
            row = await session.get(ChatSession, session_id)
            if row is None or row.user_id != user_id:
                return None
            return row

    async def list_sessions_for_user(
        self, user_id: UUID, *, offset: int = 0, limit: int = 50
    ) -> list[ChatSession]:
        async with self._db.session() as session:
            result = await session.exec(
                select(ChatSession)
                .where(ChatSession.user_id == user_id)
                .where(ChatSession.is_active == True)  # noqa: E712
                .order_by(ChatSession.last_message_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.all())

    async def list_messages(
        self, session_id: UUID, *, limit: int = 200
    ) -> list[Message]:
        async with self._db.session() as session:
            result = await session.exec(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at, Message.id)
                .limit(limit)
            )
            return list(result.all())
