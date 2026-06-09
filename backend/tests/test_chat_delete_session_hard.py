"""Hard-delete chat session must clear dependent rows (e.g. canvas_documents)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

import leagent.db.models  # noqa: F401
from leagent.services.chat.service import ChatService
from leagent.db.models.agent_memory import AgentEpisode
from leagent.db.models.canvas import CanvasContentType, CanvasDocument
from leagent.db.models.file import File, FileStatus, FileType
from leagent.db.models.message import ChatSession, Message, MessageRole, MessageStatus
from leagent.services.auth.service import LOCAL_USER_ID


@pytest.mark.asyncio
async def test_hard_delete_session_with_canvas_and_messages_commits() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def db_session_cm():
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    class _DbShim:
        def session(self):
            return db_session_cm()

    user_id = uuid4()
    session_id = uuid4()
    msg_id = uuid4()
    canvas_id = uuid4()
    file_id = uuid4()
    episode_id = uuid4()

    async with factory() as setup:
        setup.add(ChatSession(id=session_id, user_id=user_id, name="s"))
        setup.add(
            Message(
                id=msg_id,
                session_id=session_id,
                role=MessageRole.USER,
                content="hi",
                status=MessageStatus.COMPLETED,
            )
        )
        setup.add(
            CanvasDocument(
                canvas_id=canvas_id,
                session_id=session_id,
                user_id=user_id,
                title="doc",
                content_type=CanvasContentType.HTML.value,
                message_id=msg_id,
            )
        )
        setup.add(
            AgentEpisode(
                id=episode_id,
                session_id=session_id,
                user_id=user_id,
                summary="s",
            )
        )
        setup.add(
            File(
                id=file_id,
                name="a",
                original_name="a.bin",
                file_type=FileType.OTHER,
                size=1,
                storage_path="/tmp/a",
                status=FileStatus.UPLOADED,
                user_id=user_id,
                session_id=session_id,
            )
        )
        await setup.commit()

    svc = ChatService.__new__(ChatService)
    svc._db = _DbShim()
    svc._cache = None

    assert await svc.delete_session(session_id, user_id, soft=False) is True

    async with factory() as check:
        assert await check.get(ChatSession, session_id) is None
        assert await check.get(Message, msg_id) is None
        res = await check.execute(select(CanvasDocument).where(CanvasDocument.session_id == session_id))
        assert res.scalars().all() == []
        assert await check.get(AgentEpisode, episode_id) is None
        assert await check.get(File, file_id) is None

    await engine.dispose()
