"""LLM request log linkage via ContextVars and LLMService persistence."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

import leagent.db.models  # noqa: F401
from leagent.db.models import LLMRequestLog
from leagent.llm.base import LLMResponse, TokenUsage
from leagent.llm.service import LLMService
from leagent.utils.logging import (
    bind_turn_log_context,
    current_llm_call_kind,
    next_llm_call_index,
    session_id_var,
    user_message_id_var,
)


class _CaptureDB:
    def __init__(self) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        self._engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
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


def test_bind_turn_log_context_resets_call_index() -> None:
    bind_turn_log_context(
        session_id="sess-1",
        user_id="user-1",
        user_message_id="msg-1",
        call_kind="chat",
    )
    assert session_id_var.get() == "sess-1"
    assert user_message_id_var.get() == "msg-1"
    assert current_llm_call_kind() == "chat"
    assert next_llm_call_index() == 0
    assert next_llm_call_index() == 1

    bind_turn_log_context(session_id="sess-1", user_message_id="msg-2")
    assert next_llm_call_index() == 0


@pytest.mark.asyncio
async def test_record_request_log_persists_linkage(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _CaptureDB()
    await db.start()
    monkeypatch.setattr("leagent.db.get_database_service", lambda: db)

    bind_turn_log_context(
        session_id="sess-abc",
        user_id="user-xyz",
        user_message_id="turn-key-1",
        call_kind="chat",
    )

    svc = LLMService(MagicMock(), MagicMock())
    usage = TokenUsage(
        prompt_tokens=10,
        completion_tokens=5,
        prompt_cache_hit_tokens=3,
        prompt_cache_miss_tokens=2,
    )
    svc._record_request_log(
        LLMResponse(model="gpt-4o", usage=usage),
        provider="openai",
        request_model="gpt-4o",
        model="gpt-4o",
        duration=0.5,
        is_streaming=True,
    )
    await asyncio.sleep(0.05)

    async with db.session() as session:
        rows = list((await session.exec(select(LLMRequestLog))).all())

    assert len(rows) == 1
    log = rows[0]
    assert log.session_id == "sess-abc"
    assert log.user_id == "user-xyz"
    assert log.user_message_id == "turn-key-1"
    assert log.call_index == 0
    assert log.call_kind == "chat"
    assert log.input_tokens == 10
    assert log.output_tokens == 5
    assert log.cache_read_tokens == 3
    assert log.cache_miss_tokens == 2
    assert log.is_streaming is True

    await db.dispose()


@pytest.mark.asyncio
async def test_record_failed_request_log_persists_error(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _CaptureDB()
    await db.start()
    monkeypatch.setattr("leagent.db.get_database_service", lambda: db)

    bind_turn_log_context(session_id="s1", user_message_id="m1")
    svc = LLMService(MagicMock(), MagicMock())
    svc._record_failed_request_log(
        provider="openai",
        request_model="gpt-4o",
        model="gpt-4o",
        duration=1.2,
        error="rate limit exceeded",
        status_code=429,
    )
    await asyncio.sleep(0.05)

    async with db.session() as session:
        rows = list((await session.exec(select(LLMRequestLog))).all())

    assert len(rows) == 1
    assert rows[0].status_code == 429
    assert rows[0].error == "rate limit exceeded"
    assert rows[0].input_tokens == 0

    await db.dispose()
