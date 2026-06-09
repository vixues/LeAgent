"""Unit tests for :class:`SessionManager` + :class:`TieredSessionStore`.

These tests pin down the three properties we care about most:

1. ``append_user`` / ``append_assistant`` / ``append_tool_result`` leave the
   session in a consistent, LLM-ready state after a round-trip through the
   tiered store.
2. ``TieredSessionStore`` survives a flushed in-memory LRU and still
   round-trips through the SQLite-backed store.
3. ``SessionState.replace_messages`` is wired through the manager so
   auto-compaction can swap the transcript under the lock.

The :class:`SessionManager.attach_files` path talks to the filesystem and
the ``files`` table, so we test it lightly via a temp directory here; the
end-to-end integration with the chat endpoint is exercised in the API
tests.
"""

from __future__ import annotations

import io
from uuid import uuid4

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import leagent.db.models  # noqa: F401 - ensure metadata is loaded
from leagent.config.settings import get_settings
from leagent.services.session.manager import SessionManager
from leagent.services.session.state import (
    ATTACHMENT_KIND_DOCUMENT,
    SessionAttachment,
    SessionMessage,
    SessionState,
)
from leagent.services.session.store import TieredSessionStore


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _InMemoryDatabase:
    """Minimal stand-in for :class:`DatabaseService` backed by aiosqlite."""

    def __init__(self) -> None:
        self._engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", echo=False, future=True
        )
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
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

    def session(self):  # noqa: ANN201 - async context manager
        return _SessionContext(self._session_factory)


class _SessionContext:
    """Adapter that mimics ``DatabaseService.session()``: async with + commit on exit."""

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
def settings_for_session(tmp_path):
    """Point upload + session ttl at something test-friendly."""
    s = get_settings()
    s.files.upload_dir = str(tmp_path / "uploads")
    s.files.max_upload_bytes = 1024 * 1024
    s.files.preview_ttl_seconds = 60
    s.files.signed_url_secret = "unit-test-signing-secret"
    s.session.in_memory_lru_size = 4
    return s


@pytest.fixture()
async def database() -> _InMemoryDatabase:
    db = _InMemoryDatabase()
    await db.start()
    yield db
    await db.dispose()


@pytest.fixture()
async def manager(settings_for_session, database) -> SessionManager:  # noqa: ANN001
    return SessionManager(settings_for_session, cache=None, database=database)


def _upload(contents: bytes, *, filename: str, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(contents),
        filename=filename,
        headers={"content-type": content_type},
    )


# ---------------------------------------------------------------------------
# SessionState helpers
# ---------------------------------------------------------------------------


class TestSessionStateSerialisation:
    def test_round_trip_preserves_messages(self) -> None:
        sid = uuid4()
        state = SessionState(session_id=sid, user_id=uuid4())
        state.append_message(SessionMessage(role="user", content="hello"))
        state.append_message(
            SessionMessage(
                role="assistant",
                content="hi",
                tool_calls=[{"id": "call_1", "name": "search", "arguments": {}}],
            )
        )

        restored = SessionState.from_json(state.to_json())

        assert restored.session_id == sid
        assert [m.role for m in restored.messages] == ["user", "assistant"]
        assert restored.messages[1].tool_calls == [
            {"id": "call_1", "name": "search", "arguments": {}}
        ]

    def test_fingerprint_is_stable(self) -> None:
        fp1 = SessionState.fingerprint_system_prompt("you are helpful")
        fp2 = SessionState.fingerprint_system_prompt("you are helpful")
        fp3 = SessionState.fingerprint_system_prompt("you are HELPFUL")
        assert fp1 == fp2 != fp3


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessionManagerTranscript:
    async def test_append_roundtrip(self, manager: SessionManager) -> None:
        sid = uuid4()
        user_id = uuid4()
        await manager.get_or_create(sid, user_id=user_id)

        await manager.append_user(sid, "what files did I just upload?")
        await manager.append_assistant(
            sid,
            "You attached report.pdf.",
            tool_calls=[{"id": "call_1", "name": "file_manager", "arguments": {}}],
            input_tokens=40,
            output_tokens=10,
        )
        await manager.append_tool_result(
            sid,
            tool_call_id="call_1",
            content="report.pdf (size=123)",
        )

        state = await manager.load(sid)
        assert state is not None
        roles = [m.role for m in state.messages]
        assert roles == ["user", "assistant", "tool"]
        assert state.usage.input_tokens == 40
        assert state.usage.output_tokens == 10
        assert state.usage.turns == 1

    async def test_replace_messages_swaps_transcript(
        self, manager: SessionManager
    ) -> None:
        sid = uuid4()
        await manager.append_user(sid, "turn 1")
        await manager.append_assistant(sid, "reply 1")
        await manager.append_user(sid, "turn 2")

        compacted = [
            SessionMessage(role="system", content="[summary] of turns 1-2"),
        ]
        await manager.replace_messages(sid, compacted)

        state = await manager.load(sid)
        assert state is not None
        assert len(state.messages) == 1
        assert state.messages[0].role == "system"
        assert "summary" in state.messages[0].content

    async def test_attach_files_persists_and_signs(
        self, manager: SessionManager, tmp_path
    ) -> None:
        sid = uuid4()
        user_id = uuid4()
        await manager.get_or_create(sid, user_id=user_id)

        upload = _upload(b"hello world", filename="notes.txt", content_type="text/plain")
        attachments = await manager.attach_files(sid, [upload], user_id=user_id)

        assert len(attachments) == 1
        att = attachments[0]
        assert att.filename == "notes.txt"
        assert att.kind in {ATTACHMENT_KIND_DOCUMENT, "text", "document"}
        assert att.size == len(b"hello world")
        assert att.preview_url and "preview" in att.preview_url
        assert att.download_url and "download" in att.download_url

        state = await manager.load(sid)
        assert state is not None
        assert [a.filename for a in state.attachments] == ["notes.txt"]

    async def test_attachment_manifest_includes_direct_path_guidance(
        self, manager: SessionManager
    ) -> None:
        sid = uuid4()
        att = SessionAttachment(
            id=uuid4(),
            session_id=sid,
            filename="Budget.xlsx",
            storage_path=f"/tmp/{uuid4()}_Budget.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            kind="document",
            size=123,
            sha256="abc123",
        )
        manifest = manager.build_attachment_manifest([att])
        assert "FIRST file-reading tool call" in manifest
        assert "aliases=" in manifest
        assert "storage_basename=" in manifest
        assert "path=/tmp/" in manifest


# ---------------------------------------------------------------------------
# TieredSessionStore fall-through
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Controller _save/_load conversation round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestControllerConversationRoundTrip:
    """Verify that the controller's save/load conversation methods preserve
    the full transcript, including tool_calls on assistant messages and
    tool_call_id/name on tool messages.

    These tests exercise the real :class:`SessionManager` and
    :class:`ConversationContext` <-> :class:`SessionMessage` bridge that
    broke when the controller incorrectly referenced ``tool_name`` (not a
    field on the slots-based ``SessionMessage``).
    """

    async def test_save_load_plain_messages(self, manager: SessionManager) -> None:
        """User + assistant messages survive a save/load round-trip."""
        from leagent.agent.base import ConversationContext

        sid = uuid4()
        await manager.get_or_create(sid)

        conversation = ConversationContext(session_id=sid)
        conversation.append_user_message("hello")
        conversation.append_assistant_message("hi there")

        # Simulate what controller._save_conversation does
        conversation.trim()
        session_messages = [
            SessionMessage(
                role=str(msg.role),
                content=str(msg.content or ""),
                tool_call_id=getattr(msg, "tool_call_id", None),
                tool_calls=getattr(msg, "tool_calls", None),
            )
            for msg in conversation.messages
        ]
        async with manager.locked(sid) as state:
            state.replace_messages(session_messages)

        # Simulate what controller._load_conversation does
        loaded_state = await manager.load(sid)
        assert loaded_state is not None

        restored = ConversationContext(session_id=sid)
        for message in loaded_state.messages:
            if message.role == "user":
                restored.append_user_message(message.content)
            elif message.role == "assistant":
                restored.append_assistant_message(
                    message.content, tool_calls=message.tool_calls,
                )

        assert len(restored.messages) == 2
        assert restored.messages[0].role == "user"
        assert restored.messages[0].content == "hello"
        assert restored.messages[1].role == "assistant"
        assert restored.messages[1].content == "hi there"

    async def test_save_load_with_tool_calls(self, manager: SessionManager) -> None:
        """Assistant tool_calls and tool results survive the round-trip."""
        from leagent.agent.base import ConversationContext

        sid = uuid4()
        await manager.get_or_create(sid)

        conversation = ConversationContext(session_id=sid)
        conversation.append_user_message("read file.txt")
        conversation.append_assistant_message(
            "",
            tool_calls=[
                {"id": "call_abc", "name": "file_manager", "arguments": {"path": "file.txt"}},
            ],
        )
        conversation.append_tool_result("call_abc", "file_manager", "contents of file.txt")
        conversation.append_assistant_message("The file contains: contents of file.txt")

        # Save (mirrors controller._save_conversation)
        conversation.trim()
        session_messages = [
            SessionMessage(
                role=str(msg.role),
                content=str(msg.content or ""),
                tool_call_id=getattr(msg, "tool_call_id", None),
                tool_calls=getattr(msg, "tool_calls", None),
            )
            for msg in conversation.messages
        ]
        async with manager.locked(sid) as state:
            state.replace_messages(session_messages)

        # Load (mirrors controller._load_conversation)
        loaded_state = await manager.load(sid)
        assert loaded_state is not None

        restored = ConversationContext(session_id=sid)
        tool_call_names: dict[str, str] = {}
        for message in loaded_state.messages:
            if message.role == "user":
                restored.append_user_message(message.content)
            elif message.role == "assistant":
                restored.append_assistant_message(
                    message.content, tool_calls=message.tool_calls,
                )
                for tc in message.tool_calls or []:
                    tc_id = tc.get("id", "")
                    tc_name = tc.get("name") or tc.get("function", {}).get("name", "")
                    if tc_id and tc_name:
                        tool_call_names[tc_id] = tc_name
            elif message.role == "tool":
                tool_name = tool_call_names.get(message.tool_call_id or "", "")
                restored.append_tool_result(
                    message.tool_call_id or "",
                    tool_name,
                    message.content,
                )

        assert len(restored.messages) == 4
        assert restored.messages[1].tool_calls == [
            {"id": "call_abc", "name": "file_manager", "arguments": {"path": "file.txt"}},
        ]
        assert restored.messages[2].role == "tool"
        assert restored.messages[2].tool_call_id == "call_abc"
        assert restored.messages[2].name == "file_manager"
        assert restored.messages[2].content == "contents of file.txt"

    async def test_session_message_rejects_tool_name_kwarg(self) -> None:
        """SessionMessage(slots=True) must reject unknown kwargs like tool_name.

        This was the root cause of the silent save failure: the controller
        passed ``tool_name=...`` which raised TypeError, caught by a bare
        except and silently dropped. Confirm the dataclass rejects it.
        """
        with pytest.raises(TypeError, match="tool_name"):
            SessionMessage(
                role="tool",
                content="result",
                tool_call_id="call_1",
                tool_name="echo",  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# TieredSessionStore fall-through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTieredSessionStoreFallback:
    async def test_postgres_survives_lru_eviction(
        self, settings_for_session, database
    ) -> None:
        """Even with a flushed LRU, state must rehydrate from SQLite."""
        store = TieredSessionStore(settings_for_session, cache=None, database=database)

        sid = uuid4()
        state = SessionState(session_id=sid, user_id=uuid4())
        state.append_message(SessionMessage(role="user", content="persist me"))
        await store.save(state)

        # Simulate fresh worker: new store with a fresh LRU.
        restart = TieredSessionStore(settings_for_session, cache=None, database=database)
        loaded = await restart.load(sid)
        assert loaded is not None
        assert [m.role for m in loaded.messages] == ["user"]
        assert loaded.messages[0].content == "persist me"
