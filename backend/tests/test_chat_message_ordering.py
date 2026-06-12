"""Tests for chat message chronological ordering (persistence + reads)."""

from __future__ import annotations

from uuid import uuid4

from typing import AsyncIterator

import pytest
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

import leagent.db.models  # noqa: F401 — register metadata
from leagent.config.settings import get_settings
from leagent.db.models.message import ChatSession, Message, MessageRole
from leagent.services.chat.service import ChatService
from leagent.services.session.store import TieredSessionStore


class _InMemoryDatabase:
    def __init__(self) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        self._engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            future=True,
        )
        self._session_factory = sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
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


@pytest.fixture
async def chat_svc() -> AsyncIterator[tuple[ChatService, UUID, UUID]]:
    db = _InMemoryDatabase()
    await db.start()
    settings = get_settings()
    svc = ChatService(settings, db_service=db, cache_service=None)
    user_id = uuid4()
    session_id = uuid4()
    async with db.session() as session:
        session.add(
            ChatSession(
                id=session_id,
                user_id=user_id,
                name="order-test",
            )
        )
        await session.commit()
    yield svc, session_id, user_id
    await db.dispose()


@pytest.mark.asyncio
async def test_add_message_created_at_is_monotonic_within_session(
    chat_svc: tuple[ChatService, UUID, UUID],
) -> None:
    svc, session_id, user_id = chat_svc
    user_row = await svc.add_message(
        session_id,
        MessageRole.USER,
        "hello",
        user_id=user_id,
    )
    asst_row = await svc.add_message(
        session_id,
        MessageRole.ASSISTANT,
        "hi",
        user_id=user_id,
    )
    assert user_row.created_at < asst_row.created_at


@pytest.mark.asyncio
async def test_get_messages_paginated_returns_user_before_assistant(
    chat_svc: tuple[ChatService, UUID, UUID],
) -> None:
    svc, session_id, user_id = chat_svc
    await svc.add_message(session_id, MessageRole.USER, "Q", user_id=user_id)
    await svc.add_message(session_id, MessageRole.ASSISTANT, "A", user_id=user_id)

    items, total = await svc.get_messages_paginated(session_id, order="asc")
    assert total == 2
    assert [m.role for m in items] == [MessageRole.USER, MessageRole.ASSISTANT]


@pytest.mark.asyncio
async def test_rehydrate_from_messages_preserves_insert_order(
    chat_svc: tuple[ChatService, UUID, UUID],
) -> None:
    svc, session_id, user_id = chat_svc
    db = svc._db
    assert db is not None

    await svc.add_message(session_id, MessageRole.USER, "one", user_id=user_id)
    await svc.add_message(session_id, MessageRole.ASSISTANT, "two", user_id=user_id)
    await svc.add_message(session_id, MessageRole.USER, "three", user_id=user_id)

    async with db.session() as session:
        chat = (await session.exec(select(ChatSession).where(ChatSession.id == session_id))).one()
        store = TieredSessionStore(get_settings(), database=db, cache=None)
        state = await store._rehydrate_from_messages(session, chat)

    assert [m.content for m in state.messages] == ["one", "two", "three"]
