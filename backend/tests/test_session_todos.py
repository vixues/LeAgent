"""Session-scoped agent todo persistence and plan tool behaviour."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.services.session.state import (
    SessionState,
    SessionTodo,
    enforce_single_in_progress_todos,
    session_todos_from_tool_dicts,
    session_todos_to_tool_dicts,
)
from leagent.tools.base import ToolContext
from leagent.tools.util.plan_tools import TodoReadTool, TodoWriteTool


def test_session_todo_round_trip() -> None:
    todo = SessionTodo(id="a", content="Step A", status="in_progress", order=0)
    state = SessionState(session_id=uuid4(), todos=[todo])
    restored = SessionState.from_dict(state.to_dict())
    assert len(restored.todos) == 1
    assert restored.todos[0].id == "a"
    assert restored.todos[0].status == "in_progress"


def test_enforce_single_in_progress() -> None:
    items = session_todos_from_tool_dicts([
        {"id": "1", "content": "One", "status": "in_progress"},
        {"id": "2", "content": "Two", "status": "in_progress"},
    ])
    normalised = enforce_single_in_progress_todos(items)
    in_progress = [t for t in normalised if t.status == "in_progress"]
    assert len(in_progress) == 1
    assert in_progress[0].id == "1"
    assert normalised[1].status == "pending"


def test_session_todos_to_tool_dicts_sorted_by_order() -> None:
    todos = [
        SessionTodo(id="b", content="B", status="pending", order=1),
        SessionTodo(id="a", content="A", status="pending", order=0),
    ]
    as_dicts = session_todos_to_tool_dicts(todos)
    assert [d["id"] for d in as_dicts] == ["a", "b"]


def test_parse_todos_from_session_metadata() -> None:
    from leagent.db.models.message import parse_todos_from_session_metadata

    raw = (
        '{"session_state_v1": {"todos": ['
        '{"id": "t1", "content": "One", "status": "completed", "order": 0}'
        "]}}"
    )
    parsed = parse_todos_from_session_metadata(raw)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "t1"
    assert parsed[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_todo_write_persists_via_session_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = uuid4()
    stored: list[SessionTodo] = []

    class _FakeSessionManager:
        async def get_todos(self, sid):  # noqa: ANN001
            return list(stored)

        async def set_todos(self, sid, todos):  # noqa: ANN001
            if todos and isinstance(todos[0], dict):
                stored.clear()
                stored.extend(session_todos_from_tool_dicts(todos))
            else:
                stored.clear()
                stored.extend(todos)
            return list(stored)

    class _FakeSM:
        session_manager = _FakeSessionManager()

    import leagent.main as main_mod

    monkeypatch.setattr(main_mod, "get_service_manager", lambda: _FakeSM())

    context = ToolContext(user_id=str(uuid4()), session_id=str(session_id), extra={})
    tool = TodoWriteTool()
    result = await tool.execute(
        {
            "todos": [
                {"id": "t1", "content": "First", "status": "pending"},
                {"id": "t2", "content": "Second", "status": "in_progress"},
            ],
            "merge": False,
        },
        context,
    )
    assert result["count"] == 2
    assert len(stored) == 2
    assert context.extra["todos"][0]["id"] == "t1"


@pytest.mark.asyncio
async def test_todo_read_hydrates_from_session(monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = uuid4()

    class _FakeSessionManager:
        async def get_todos(self, sid):  # noqa: ANN001
            return [SessionTodo(id="x", content="Hydrated", status="completed", order=0)]

    class _FakeSM:
        session_manager = _FakeSessionManager()

    import leagent.main as main_mod

    monkeypatch.setattr(main_mod, "get_service_manager", lambda: _FakeSM())

    context = ToolContext(user_id=str(uuid4()), session_id=str(session_id), extra={})
    tool = TodoReadTool()
    result = await tool.execute({}, context)
    assert result["count"] == 1
    assert result["todos"][0]["content"] == "Hydrated"


@pytest.mark.asyncio
async def test_update_todo_status_demotes_other_in_progress(tmp_path) -> None:
    from leagent.config.settings import get_settings
    from leagent.services.session.manager import SessionManager

    settings = get_settings()
    settings.files.upload_dir = str(tmp_path / "uploads")
    settings.session.in_memory_lru_size = 4

    session_id = uuid4()
    manager = SessionManager(settings, cache=None, database=None)

    await manager.set_todos(
        session_id,
        [
            {"id": "a", "content": "A", "status": "in_progress"},
            {"id": "b", "content": "B", "status": "pending"},
        ],
    )

    updated = await manager.update_todo_status(session_id, "b", "in_progress")
    by_id = {t.id: t.status for t in updated}
    assert by_id["b"] == "in_progress"
    assert by_id["a"] == "pending"

    reloaded = await manager.get_todos(session_id)
    assert {t.id: t.status for t in reloaded} == by_id
