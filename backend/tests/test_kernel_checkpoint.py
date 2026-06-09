"""Kernel run-loop + durable checkpoint store tests.

Pins the architecture-upgrade contracts:

* ``run_loop`` preserves the SDK wire shape (``AgentEvent`` == ``SDKMessage``),
  populates ``RunState.messages`` for resume, dispatches single-site tool
  hooks, and saves a checkpoint on ``awaiting_user_input``.
* ``SQLCheckpointStore`` round-trips a checkpoint through the database.
* ``AgentRuntime.resume`` rejects an unknown checkpoint id.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession

from leagent.agent.base import AgentContext
from leagent.agent.hooks import AgentHook, HookManager
from leagent.agent.query_engine import SDKMessage
from leagent.sdk.kernel.checkpoint import (
    InMemoryCheckpointStore,
    SQLCheckpointStore,
    create_checkpoint,
)
from leagent.sdk.kernel.loop import run_loop
from leagent.sdk.kernel.state import RunState


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeConfig:
    session_id = None
    user_id = None
    agent_id = "test_agent"


class _FakeEngine:
    """Scripted stand-in for QueryEngine used by ``run_loop``."""

    def __init__(self, scripted: list[SDKMessage]) -> None:
        self._scripted = scripted
        self.mutable_messages: list[dict] = []
        self.abort_event = asyncio.Event()
        self.config = _FakeConfig()
        self.submit_kwargs: dict = {}

    async def submit_message(self, prompt, **kwargs) -> AsyncIterator[SDKMessage]:
        self.submit_kwargs = kwargs
        self.mutable_messages.append({"role": "user", "content": str(prompt)})
        for msg in self._scripted:
            if msg.type == "assistant":
                self.mutable_messages.append(
                    {"role": "assistant", "content": msg.data.get("content", "")}
                )
            yield msg


class _RecordingHook(AgentHook):
    def __init__(self) -> None:
        self.tool_calls: list[str] = []
        self.tool_results: list[bool] = []

    async def on_tool_call(self, context, tool_call) -> None:
        self.tool_calls.append(tool_call.name)

    async def on_tool_result(self, context, tool_call, result) -> None:
        self.tool_results.append(result.success)


def _awaiting_script() -> list[SDKMessage]:
    return [
        SDKMessage(type="system_init", data={"session_id": "s"}),
        SDKMessage(type="tool_use", data={"id": "t1", "name": "web_search", "input": {}}),
        SDKMessage(
            type="tool_result",
            data={"tool_use_id": "t1", "name": "web_search", "success": True, "content": "ok"},
        ),
        SDKMessage(type="assistant", data={"content": "hello"}),
        SDKMessage(
            type="result",
            data={"reason": "awaiting_user_input", "session_id": "s", "usage": {}},
        ),
    ]


# ---------------------------------------------------------------------------
# run_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_loop_preserves_wire_shape_and_forwards_kwargs() -> None:
    engine = _FakeEngine(_awaiting_script())
    state = RunState(session_id="s", agent_name="test_agent")

    events = [
        ev async for ev in run_loop(engine, "hi", run_state=state, append_user_turn=False)
    ]

    # AgentEvent must mirror SDKMessage {type, data} exactly.
    assert [e.type for e in events] == [
        "system_init", "tool_use", "tool_result", "assistant", "result",
    ]
    # submit kwargs forwarded through the loop.
    assert engine.submit_kwargs == {"append_user_turn": False}


@pytest.mark.asyncio
async def test_run_loop_populates_messages_and_checkpoints_on_pause() -> None:
    engine = _FakeEngine(_awaiting_script())
    store = InMemoryCheckpointStore()
    state = RunState(session_id="s", agent_name="test_agent")
    hook = _RecordingHook()
    hooks = HookManager()
    hooks.register(hook)
    ctx = AgentContext()

    checkpoint_id = None
    async for ev in run_loop(
        engine, "hi",
        run_state=state,
        checkpoint_store=store,
        hooks=hooks,
        hook_context=ctx,
    ):
        if ev.type == "result":
            checkpoint_id = ev.data.get("checkpoint_id")

    # RunState carries the live transcript (not empty) for resume.
    assert state.messages
    assert any(m.get("role") == "assistant" for m in state.messages)
    assert state.tool_calls_total == 1

    # Single-site hooks fired.
    assert hook.tool_calls == ["web_search"]
    assert hook.tool_results == [True]

    # A durable checkpoint was saved and its id surfaced on the result event.
    assert checkpoint_id is not None
    saved = await store.load(checkpoint_id)
    assert saved is not None
    assert saved.reason == "awaiting_user_input"
    assert saved.messages == state.messages


@pytest.mark.asyncio
async def test_run_loop_completed_turn_does_not_checkpoint_by_default() -> None:
    script = [SDKMessage(type="result", data={"reason": "completed", "usage": {}})]
    engine = _FakeEngine(script)
    store = InMemoryCheckpointStore()
    state = RunState(session_id="s")

    async for _ in run_loop(engine, "hi", run_state=state, checkpoint_store=store):
        pass

    assert len(store) == 0


# ---------------------------------------------------------------------------
# SQLCheckpointStore round-trip
# ---------------------------------------------------------------------------


class _InMemoryDB:
    """SQLite-backed DatabaseService-shaped fake for the checkpoint table."""

    def __init__(self) -> None:
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._path = path
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{path}",
            echo=False,
            poolclass=NullPool,
            connect_args={"check_same_thread": False, "timeout": 15},
        )
        self._factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._repositories = None

    async def prepare(self) -> None:
        from leagent.db.models.agent_checkpoint import AgentCheckpoint

        async with self._engine.begin() as conn:
            await conn.run_sync(
                lambda sc: AgentCheckpoint.__table__.create(sc, checkfirst=True)
            )

    @property
    def repositories(self):
        if self._repositories is None:
            from leagent.db.repositories import Repositories

            self._repositories = Repositories(self)
        return self._repositories

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self._engine.dispose()
        try:
            os.remove(self._path)
        except OSError:
            pass


@pytest_asyncio.fixture()
async def fake_db() -> AsyncIterator[_InMemoryDB]:
    db = _InMemoryDB()
    await db.prepare()
    yield db
    await db.dispose()


@pytest.mark.asyncio
async def test_sql_checkpoint_store_round_trip(fake_db: _InMemoryDB) -> None:
    store = SQLCheckpointStore(fake_db)
    cp = create_checkpoint(
        session_id="sess-1",
        agent_name="default_agent",
        turn=2,
        messages=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}],
        reason="awaiting_user_input",
        usage={"total_tokens": 42},
        metadata={"k": "v"},
    )

    await store.save(cp)

    loaded = await store.load(cp.checkpoint_id)
    assert loaded is not None
    assert loaded.session_id == "sess-1"
    assert loaded.agent_name == "default_agent"
    assert loaded.turn == 2
    assert loaded.reason == "awaiting_user_input"
    assert loaded.messages == cp.messages
    assert loaded.usage == {"total_tokens": 42}
    assert loaded.metadata == {"k": "v"}

    listed = await store.list_for_session("sess-1")
    assert [c.checkpoint_id for c in listed] == [cp.checkpoint_id]

    # Upsert (same id) replaces rather than duplicates.
    cp.turn = 3
    await store.save(cp)
    again = await store.load(cp.checkpoint_id)
    assert again.turn == 3
    assert len(await store.list_for_session("sess-1")) == 1

    await store.delete(cp.checkpoint_id)
    assert await store.load(cp.checkpoint_id) is None


# ---------------------------------------------------------------------------
# Resume API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_resume_unknown_checkpoint_raises() -> None:
    from leagent.runtime import AgentRuntime, RuntimeContext

    rt = AgentRuntime(RuntimeContext(checkpoint_store=InMemoryCheckpointStore()))
    with pytest.raises(ValueError, match="not found"):
        async for _ in rt.resume("default_agent", "missing-id", "hello"):
            pass


@pytest.mark.asyncio
async def test_runtime_resume_seeds_engine_with_checkpoint_messages() -> None:
    """End-to-end: load a checkpoint, rebuild the engine with its history."""
    from leagent.runtime import AgentEvent, AgentRuntime, RuntimeContext

    store = InMemoryCheckpointStore()
    history = [
        {"role": "user", "content": "translate this"},
        {"role": "assistant", "content": "which language?"},
    ]
    cp = create_checkpoint(
        session_id="",
        agent_name="default_agent",
        turn=1,
        messages=history,
        reason="awaiting_user_input",
    )
    await store.save(cp)

    rt = AgentRuntime(RuntimeContext(checkpoint_store=store))

    captured: dict = {}

    def _fake_build_engine(agent, **kwargs):
        captured["initial_messages"] = kwargs.get("initial_messages")
        return object()

    async def _fake_stream(agent, prompt, **kwargs):
        captured["prompt"] = prompt
        yield AgentEvent(type="assistant", data={"content": "French it is"})
        yield AgentEvent(type="result", data={"reason": "completed", "usage": {}})

    rt.build_engine = _fake_build_engine  # type: ignore[assignment]
    rt.stream = _fake_stream  # type: ignore[assignment]

    events = [
        ev
        async for ev in rt.resume("default_agent", cp.checkpoint_id, "French")
    ]

    # The rebuilt engine was seeded with the checkpoint's transcript.
    assert captured["initial_messages"] == history
    # The resume prompt (the user's answer to the pause) drove the new turn.
    assert captured["prompt"] == "French"
    assert [e.type for e in events] == ["assistant", "result"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
