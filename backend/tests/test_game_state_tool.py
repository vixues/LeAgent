"""Roundtrip tests for the session-scoped game_state tool."""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from leagent.services.session.state import SessionState
from leagent.tools.base import ToolContext
from leagent.tools.util.game_state import GameStateTool


class _FakeSessionManager:
    def __init__(self) -> None:
        self._states: dict[str, SessionState] = {}

    async def load(self, session_id):  # noqa: ANN001
        return self._states.get(str(session_id))

    @asynccontextmanager
    async def locked(self, session_id):  # noqa: ANN001
        sid = str(session_id)
        state = self._states.get(sid)
        if state is None:
            state = SessionState(session_id=session_id)
            self._states[sid] = state
        yield state


class _FakeServiceManager:
    def __init__(self, session_manager: _FakeSessionManager) -> None:
        self.session_manager = session_manager


@pytest.fixture
def game_context() -> tuple[ToolContext, _FakeSessionManager]:
    session_id = uuid4()
    manager = _FakeSessionManager()
    sm = _FakeServiceManager(manager)
    context = ToolContext(
        user_id=str(uuid4()),
        session_id=str(session_id),
        extra={},
    )
    context.service_manager = sm  # noqa: SLF001 — tool reads via getattr
    return context, manager


@pytest.mark.asyncio
async def test_game_state_init_read_update_score_roundtrip(
    game_context: tuple[ToolContext, _FakeSessionManager],
) -> None:
    context, _manager = game_context
    tool = GameStateTool()
    game_id = "quiz-1"

    init = await tool.execute(
        {
            "operation": "init",
            "game_id": game_id,
            "phase": "playing",
            "payload": {"round": 1, "answer": None},
        },
        context,
    )
    assert init["game"]["phase"] == "playing"
    assert init["game"]["payload"]["round"] == 1

    read = await tool.execute(
        {"operation": "read", "game_id": game_id},
        context,
    )
    assert read["game"]["turn"] == 0

    updated = await tool.execute(
        {
            "operation": "update",
            "game_id": game_id,
            "payload": {"answer": "B"},
            "advance_turn": True,
        },
        context,
    )
    assert updated["game"]["turn"] == 1
    assert updated["game"]["payload"]["answer"] == "B"

    scored = await tool.execute(
        {
            "operation": "score",
            "game_id": game_id,
            "score_delta": 10,
            "rule_tag": "correct",
        },
        context,
    )
    assert scored["game"]["score"] == 10
    assert scored["game"]["score_history"][-1]["tag"] == "correct"

    final = await tool.execute(
        {"operation": "read", "game_id": game_id},
        context,
    )
    assert final["game"]["turn"] == 1
    assert final["game"]["score"] == 10
