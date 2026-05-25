"""Smoke coverage for :class:`TaskManager` + the bundled handlers.

We spin up an in-memory SQLite DB, monkeypatch
``leagent.services.database.get_database_service`` so the background
task coroutine can open its own session, and then drive a fake handler
end-to-end (pending -> running -> completed) and a never-returning one
to verify kill flips the task to ``KILLED``.

The real :mod:`leagent.tasks.handlers` sub-modules are also
imported to make sure their modules load without side-effects (the
package needs to be importable for the bootstrap hook).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

import leagent.services.database.models  # noqa: F401 - populate metadata
from leagent.services.database.models.task import (
    Task,
    TaskContext,
    TaskStatus,
    TaskType,
)
from leagent.services.task_manager import TaskManager


# ---------------------------------------------------------------------------
# Fake DB service
# ---------------------------------------------------------------------------


class _InMemoryDB:
    def __init__(self) -> None:
        # A disk-backed temp DB is the simplest way to share state across
        # the short-lived sessions the TaskManager opens from its
        # background coroutine. An ``:memory:`` URL would give each new
        # connection its own empty DB on aiosqlite.
        fd, path = tempfile.mkstemp(suffix=".db", prefix="wa_test_")
        os.close(fd)
        self._path = path
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{path}",
            echo=False,
            connect_args={"timeout": 15},
        )
        self._factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._ready = False

    async def prepare(self) -> None:
        # Build only the subset of tables/indexes we need. Using the full
        # ``SQLModel.metadata.create_all`` trips over duplicate-index
        # definitions in unrelated models (e.g. ``todos``) on SQLite.
        from leagent.services.database.models.task import Task

        async with self._engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Task.__table__.create(sync_conn, checkfirst=True)
            )
        self._ready = True

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        assert self._ready, "call prepare() before opening sessions"
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
async def fake_db(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_InMemoryDB]:
    db = _InMemoryDB()
    await db.prepare()

    # TaskManager imports the singleton lazily inside ``_run_task``; patch
    # the symbol where it is looked up.
    from leagent.services import database as db_pkg

    monkeypatch.setattr(db_pkg, "get_database_service", lambda: db, raising=True)
    yield db
    await db.dispose()


# ---------------------------------------------------------------------------
# Test handlers
# ---------------------------------------------------------------------------


class _EchoHandler:
    """Completes immediately after writing a line to the task output."""

    name = "echo_handler"
    task_type = TaskType.SHELL

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> dict[str, Any]:
        text = str(params.get("text", "hello"))
        task_ctx.append_output(text + "\n")
        return {"echoed": text}

    async def kill(self, task_id: str, session: AsyncSession) -> None:
        return None


class _FailingHandler:
    name = "failing_handler"
    task_type = TaskType.TOOL

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> dict[str, Any]:
        raise RuntimeError("boom")

    async def kill(self, task_id: str, session: AsyncSession) -> None:
        return None


class _BlockingHandler:
    """Runs until it is explicitly aborted by the context event."""

    name = "blocking_handler"
    task_type = TaskType.AGENT

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> dict[str, Any]:
        # Wait for abort or a very long timeout; the test flips the abort.
        await asyncio.wait_for(task_ctx.abort_event.wait(), timeout=30.0)
        return {"aborted": True}

    async def kill(self, task_id: str, session: AsyncSession) -> None:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _wait_until(predicate, *, timeout: float = 5.0) -> None:
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if await predicate() if asyncio.iscoroutinefunction(predicate) else predicate():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition never became true")


async def _fetch_status(db: _InMemoryDB, task_id) -> TaskStatus:
    async with db.session() as s:
        t = await s.get(Task, task_id)
        assert t is not None
        return t.status


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handlers_package_imports_cleanly() -> None:
    """The production handler modules must import without side effects."""
    from leagent.tasks import handlers as pkg

    assert hasattr(pkg, "AgentTaskHandler")
    assert hasattr(pkg, "ShellTaskHandler")
    assert hasattr(pkg, "WorkflowTaskHandler")
    assert hasattr(pkg, "ToolTaskHandler")
    assert hasattr(pkg, "BatchTaskHandler")


@pytest.mark.asyncio
async def test_register_handler_tracks_task_type() -> None:
    mgr = TaskManager()
    echo = _EchoHandler()
    mgr.register_handler(echo)
    assert mgr.get_handler(TaskType.SHELL) is echo
    assert mgr.get_handler(TaskType.AGENT) is None
    assert echo in mgr.get_all_handlers()


@pytest.mark.asyncio
async def test_create_start_completes(fake_db: _InMemoryDB) -> None:
    """Happy path: task transitions pending -> running -> completed."""
    mgr = TaskManager()
    mgr.register_handler(_EchoHandler())

    user_id = uuid4()
    async with fake_db.session() as session:
        task = await mgr.create_task(
            session,
            name="unit-echo",
            task_type=TaskType.SHELL,
            user_id=user_id,
            input_data={"text": "hi"},
        )
        assert task.status == TaskStatus.PENDING
        await mgr.start_task(session, task, params={"text": "hi"})
        assert task.status == TaskStatus.RUNNING
        task_id = task.id

    async def _is_complete() -> bool:
        return (await _fetch_status(fake_db, task_id)) == TaskStatus.COMPLETED

    await _wait_until(_is_complete)
    assert not mgr.is_running(str(task_id))


@pytest.mark.asyncio
async def test_spawn_exception_marks_failed(fake_db: _InMemoryDB) -> None:
    mgr = TaskManager()
    mgr.register_handler(_FailingHandler())
    async with fake_db.session() as session:
        task = await mgr.create_task(
            session, name="unit-fail", task_type=TaskType.TOOL
        )
        await mgr.start_task(session, task, params={})
        task_id = task.id

    async def _is_failed() -> bool:
        return (await _fetch_status(fake_db, task_id)) == TaskStatus.FAILED

    await _wait_until(_is_failed)
    async with fake_db.session() as s:
        t = await s.get(Task, task_id)
        assert t is not None
        assert t.error == "boom"


@pytest.mark.asyncio
async def test_kill_transitions_to_killed(fake_db: _InMemoryDB) -> None:
    mgr = TaskManager()
    mgr.register_handler(_BlockingHandler())
    mark_killed_calls = 0
    original_mark_killed = mgr._mark_killed

    async def _track_mark_killed(task_id: str) -> None:
        nonlocal mark_killed_calls
        mark_killed_calls += 1
        await original_mark_killed(task_id)

    mgr._mark_killed = _track_mark_killed

    async with fake_db.session() as session:
        task = await mgr.create_task(
            session, name="unit-block", task_type=TaskType.AGENT
        )
        await mgr.start_task(session, task, params={})
        task_id = task.id

    await asyncio.sleep(0.05)
    assert mgr.is_running(str(task_id))

    async with fake_db.session() as session:
        killed = await mgr.kill_task(session, str(task_id))
    assert killed is True

    async def _is_killed() -> bool:
        return (await _fetch_status(fake_db, task_id)) == TaskStatus.KILLED

    await _wait_until(_is_killed)
    await asyncio.sleep(0)
    assert mark_killed_calls == 0


@pytest.mark.asyncio
async def test_task_timeout_marks_timeout(fake_db: _InMemoryDB) -> None:
    """TaskManager enforces task.timeout_seconds for background runs."""

    mgr = TaskManager()
    mgr.register_handler(_BlockingHandler())
    async with fake_db.session() as session:
        task = await mgr.create_task(
            session,
            name="unit-timeout",
            task_type=TaskType.AGENT,
            timeout_seconds=1,
        )
        await mgr.start_task(session, task, params={})
        task_id = task.id

    async def _is_timeout() -> bool:
        return (await _fetch_status(fake_db, task_id)) == TaskStatus.TIMEOUT

    await _wait_until(_is_timeout, timeout=5.0)


@pytest.mark.asyncio
async def test_start_task_without_handler_fails(fake_db: _InMemoryDB) -> None:
    mgr = TaskManager()  # intentionally empty registry
    async with fake_db.session() as session:
        task = await mgr.create_task(
            session, name="unit-noop", task_type=TaskType.SHELL
        )
        await mgr.start_task(session, task)
        assert task.status == TaskStatus.FAILED
        assert task.error is not None and "No handler" in task.error
