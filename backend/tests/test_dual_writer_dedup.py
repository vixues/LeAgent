"""Tests for the dual-writer duplicate-prevention fix.

Validates that ``TieredSessionStore._save_to_database()`` no longer inserts
duplicate USER rows after ``ChatService.add_message()`` has already persisted
them, and that the repair utility correctly cleans up existing duplicates.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

import leagent.db.models  # noqa: F401 — register metadata
from leagent.config.settings import get_settings
from leagent.db.models.message import (
    ChatSession,
    Message,
    MessageRole,
)
from leagent.services.session.manager import SessionManager
from leagent.services.session.state import SessionMessage, SessionState
from leagent.services.session.store import TieredSessionStore
from leagent.services.chat.repair import deduplicate_user_messages


# ---------------------------------------------------------------------------
# In-memory SQLite database helper (matches test_session_manager.py)
# ---------------------------------------------------------------------------

class _InMemoryDatabase:
    def __init__(self) -> None:
        self._engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", echo=False, future=True,
        )
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )
        self._ready = False

    async def start(self) -> None:
        if self._ready:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        self._ready = True

    async def dispose(self) -> None:
        await self._engine.dispose()

    def session(self):  # noqa: ANN201
        return _SessionCtx(self._session_factory)


class _SessionCtx:
    def __init__(self, factory) -> None:  # noqa: ANN001
        self._factory = factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> AsyncSession:
        self._session = self._factory()
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        assert self._session is not None
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def settings():
    s = get_settings()
    s.session.in_memory_lru_size = 4
    return s


@pytest.fixture()
async def database() -> _InMemoryDatabase:
    db = _InMemoryDatabase()
    await db.start()
    yield db
    await db.dispose()


@pytest.fixture()
async def manager(settings, database) -> SessionManager:  # noqa: ANN001
    return SessionManager(settings, cache=None, database=database)


# ---------------------------------------------------------------------------
# Helper to count user rows in messages table
# ---------------------------------------------------------------------------

async def _count_user_rows(database: _InMemoryDatabase, session_id: UUID) -> int:
    async with database.session() as db:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id, Message.role == MessageRole.USER)
        )
        return len(result.all())


async def _all_messages(database: _InMemoryDatabase, session_id: UUID) -> list[Message]:
    async with database.session() as db:
        result = await db.execute(
            select(Message).where(Message.session_id == session_id)
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDualWriterNoDuplicate:
    """The core regression test: ChatService writes a USER row, then the
    TieredSessionStore save (triggered by controller) does NOT create a
    second one, even when the snapshot holds the message with a different UUID.
    """

    async def test_store_skips_user_rows_after_chat_service(
        self, database: _InMemoryDatabase, settings,
    ) -> None:
        session_id = uuid4()
        user_id = uuid4()
        user_msg_id_chat_service = uuid4()

        # 1) Simulate ChatService.add_message(USER) — insert directly.
        async with database.session() as db:
            db.add(ChatSession(
                id=session_id,
                user_id=user_id,
                message_count=1,
            ))
            db.add(Message(
                id=user_msg_id_chat_service,
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.USER,
                content="Hello from user",
            ))

        assert await _count_user_rows(database, session_id) == 1

        # 2) Build a SessionState snapshot that contains the same logical
        #    user message but with a DIFFERENT UUID (as the old controller
        #    would produce after index drift).
        state = SessionState(session_id=session_id, user_id=user_id)
        state.append_message(SessionMessage(
            id=uuid4(),  # different UUID!
            role="user",
            content="Hello from user",
        ))
        state.append_message(SessionMessage(
            role="assistant",
            content="Hi there!",
        ))

        # 3) Run the store's save — this should NOT insert a new user row.
        store = TieredSessionStore(settings, cache=None, database=database)
        await store._save_to_database(state)

        # Verify: still exactly 1 user row.
        assert await _count_user_rows(database, session_id) == 1

    async def test_store_still_inserts_tool_rows(
        self, database: _InMemoryDatabase, settings,
    ) -> None:
        """Tool messages should still be persisted by the store."""
        session_id = uuid4()
        user_id = uuid4()

        async with database.session() as db:
            db.add(ChatSession(
                id=session_id,
                user_id=user_id,
                message_count=0,
            ))

        state = SessionState(session_id=session_id, user_id=user_id)
        state.append_message(SessionMessage(role="user", content="run tool"))
        state.append_message(SessionMessage(
            role="assistant",
            content="calling tool",
            tool_calls=[{"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{}"}}],
        ))
        state.append_message(SessionMessage(
            role="tool",
            content="tool output",
            tool_call_id="call_1",
        ))

        store = TieredSessionStore(settings, cache=None, database=database)
        await store._save_to_database(state)

        msgs = await _all_messages(database, session_id)
        roles = [m.role for m in msgs]
        assert MessageRole.TOOL in roles
        assert MessageRole.USER not in roles
        assert MessageRole.ASSISTANT not in roles


@pytest.mark.asyncio
class TestRepairUtility:
    """Tests for :func:`deduplicate_user_messages`."""

    async def test_removes_duplicate_user_rows(
        self, database: _InMemoryDatabase,
    ) -> None:
        session_id = uuid4()
        user_id = uuid4()

        # Seed: 1 session, 3 copies of the same user message.
        async with database.session() as db:
            db.add(ChatSession(
                id=session_id,
                user_id=user_id,
                message_count=5,
            ))
            db.add(Message(
                id=uuid4(),
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.USER,
                content="duplicate content",
            ))
            db.add(Message(
                id=uuid4(),
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.USER,
                content="duplicate content",
            ))
            db.add(Message(
                id=uuid4(),
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.USER,
                content="duplicate content",
            ))
            db.add(Message(
                id=uuid4(),
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.ASSISTANT,
                content="assistant reply",
            ))
            db.add(Message(
                id=uuid4(),
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.USER,
                content="unique user msg",
            ))

        assert await _count_user_rows(database, session_id) == 4

        async with database.session() as db:
            result = await deduplicate_user_messages(db, session_id=session_id)

        assert result["duplicates_found"] == 2
        assert result["rows_deleted"] == 2
        assert result["sessions_affected"] == 1

        assert await _count_user_rows(database, session_id) == 2

    async def test_dry_run_does_not_delete(
        self, database: _InMemoryDatabase,
    ) -> None:
        session_id = uuid4()
        user_id = uuid4()

        async with database.session() as db:
            db.add(ChatSession(
                id=session_id,
                user_id=user_id,
                message_count=2,
            ))
            db.add(Message(
                id=uuid4(),
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.USER,
                content="dup",
            ))
            db.add(Message(
                id=uuid4(),
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.USER,
                content="dup",
            ))

        async with database.session() as db:
            result = await deduplicate_user_messages(
                db, session_id=session_id, dry_run=True,
            )

        assert result["duplicates_found"] == 1
        assert result["rows_deleted"] == 0
        assert await _count_user_rows(database, session_id) == 2

    async def test_no_duplicates_returns_zero(
        self, database: _InMemoryDatabase,
    ) -> None:
        session_id = uuid4()
        user_id = uuid4()

        async with database.session() as db:
            db.add(ChatSession(
                id=session_id,
                user_id=user_id,
                message_count=1,
            ))
            db.add(Message(
                id=uuid4(),
                session_id=session_id,
                user_id=user_id,
                role=MessageRole.USER,
                content="only once",
            ))

        async with database.session() as db:
            result = await deduplicate_user_messages(db, session_id=session_id)

        assert result["duplicates_found"] == 0
        assert result["rows_deleted"] == 0
