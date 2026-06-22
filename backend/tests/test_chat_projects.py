from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import leagent.db.models  # noqa: F401 - register SQLModel metadata
from leagent.config.settings import get_settings
from leagent.services.chat.projects import ChatProjectService
from leagent.services.chat.service import ChatService


class _InMemoryDatabase:
    def __init__(self) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        self._engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        self._session_factory = sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def start(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

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

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        assert self._session is not None
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()


@pytest.mark.asyncio
async def test_project_password_unlock_token_is_scoped() -> None:
    db = _InMemoryDatabase()
    await db.start()
    try:
        user_id = uuid4()
        other_user_id = uuid4()
        service = ChatProjectService(db)  # type: ignore[arg-type]
        project = await service.create_project(
            user_id=user_id,
            name="Brand refresh",
            password="secret",
        )

        assert await service.verify_project_password(
            project.id,
            user_id=user_id,
            password="secret",
        )
        assert not await service.verify_project_password(
            project.id,
            user_id=user_id,
            password="wrong",
        )

        token, _expires_at = service.mint_unlock_token(project_id=project.id, user_id=user_id)
        assert service.verify_unlock_token(token, project_id=project.id, user_id=user_id)
        assert not service.verify_unlock_token(token, project_id=project.id, user_id=other_user_id)
        assert not service.verify_unlock_token(token, project_id=uuid4(), user_id=user_id)
    finally:
        await db.dispose()


@pytest.mark.asyncio
async def test_chat_session_can_be_created_and_listed_for_project() -> None:
    db = _InMemoryDatabase()
    await db.start()
    try:
        user_id = uuid4()
        settings = get_settings()
        project_service = ChatProjectService(db)  # type: ignore[arg-type]
        chat_service = ChatService(settings, db_service=db, cache_service=None)  # type: ignore[arg-type]
        project = await project_service.create_project(
            user_id=user_id,
            name="Packaging concepts",
        )
        session = await chat_service.create_session(
            user_id,
            name="Round 1",
            project_id=project.id,
        )

        sessions = await chat_service.list_sessions(user_id, project_id=project.id)
        assert [s.id for s in sessions] == [session.id]
        assert sessions[0].project_id == project.id
    finally:
        await db.dispose()
