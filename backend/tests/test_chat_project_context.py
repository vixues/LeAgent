"""Verify that ``project_folder_id`` propagates into ``tool_extra``.

The chat endpoint resolves a folder bound to a code project and
injects the path into ``QueryEngineConfig.tool_extra['project_roots']``
on the engine. We test the small public surface — the controller's
``run`` method — rather than booting the full FastAPI router. A
fake :class:`QueryEngine` captures the config so we can assert on
``tool_extra``.

This keeps the assertion close to the contract that matters for
``coding_agent`` and the ``project_*`` tools, and avoids tying the
test to the (much larger) request/response cycle of ``/chat/stream``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest


class _FakeEngine:
    """Stand-in :class:`QueryEngine` that records its config."""

    captured_config: Any | None = None

    def __init__(self, config: Any) -> None:
        type(self).captured_config = config

    @property
    def cwd(self) -> str:
        return getattr(self.captured_config, "cwd", ".")

    def abort(self) -> None:
        pass

    async def submit_message(self, *_args: Any, **_kwargs: Any):  # type: ignore[no-untyped-def]
        # Yield nothing so ``_run_via_query_engine`` exits its loop
        # immediately and the test can inspect ``captured_config``.
        if False:
            yield None  # pragma: no cover - generator marker


def _build_controller(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Construct an AgentController with all collaborators mocked out."""
    from unittest.mock import AsyncMock, MagicMock

    from leagent.agent.base import AgentConfig, AgentMode
    from leagent.agent.controller import AgentController
    from leagent.agent import query_engine as qe_mod

    monkeypatch.setattr(qe_mod, "QueryEngine", _FakeEngine)

    llm = MagicMock()
    tools = MagicMock()
    planner = MagicMock()
    executor = MagicMock()
    executor.service_manager = None

    controller = AgentController(
        llm=llm,
        tools=tools,
        planner=planner,
        executor=executor,
        config=AgentConfig(
            max_iterations=1,
            mode=AgentMode.REACT,
            enable_memory=False,
            enable_streaming=False,
            verbose=False,
            use_query_engine=True,
        ),
    )

    # ``_create_context`` uses lower-level managers; bypass with a
    # minimal stub so we don't need a DB/session manager.
    async def _fake_create_context(
        session_id: UUID,
        user_id: UUID | None,
        *,
        task_id: UUID | None = None,
    ) -> Any:
        from leagent.agent.base import AgentContext, AgentState

        return AgentContext(
            task_id=task_id or uuid4(),
            session_id=session_id,
            user_id=user_id or uuid4(),
            config=controller.config,
            state=AgentState.IDLE,
        )

    controller._create_context = _fake_create_context  # type: ignore[assignment]

    async def _fake_load(_sid: Any) -> Any:
        from leagent.agent.base import ConversationContext

        return ConversationContext(session_id=_sid)

    controller._load_conversation = _fake_load  # type: ignore[assignment]
    controller._save_conversation = AsyncMock()  # type: ignore[assignment]
    controller._record_episode = AsyncMock()  # type: ignore[assignment]

    async def _fake_match_workflow(_q: str) -> Any:
        return None

    controller._match_workflow = _fake_match_workflow  # type: ignore[assignment]

    return controller


@pytest.mark.asyncio
async def test_run_via_query_engine_injects_project_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _FakeEngine.captured_config = None
    controller = _build_controller(monkeypatch)
    project_path = str(tmp_path)

    await controller.run(
        "hello",
        uuid4(),
        user_id=uuid4(),
        project_roots=[project_path],
    )

    assert _FakeEngine.captured_config is not None
    cfg = _FakeEngine.captured_config
    extra = getattr(cfg, "tool_extra", {}) or {}
    assert extra.get("project_roots") == [project_path]
    assert getattr(cfg, "cwd", None) == project_path
    assert "project_*" not in getattr(cfg, "tools_deny_patterns", [])


@pytest.mark.asyncio
async def test_run_via_query_engine_without_project_roots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeEngine.captured_config = None
    controller = _build_controller(monkeypatch)

    await controller.run("hi", uuid4(), user_id=uuid4())

    cfg = _FakeEngine.captured_config
    assert cfg is not None
    extra = getattr(cfg, "tool_extra", {}) or {}
    assert "project_roots" not in extra
    assert getattr(cfg, "cwd", None) == "."
    assert "project_*" in getattr(cfg, "tools_deny_patterns", [])


@pytest.mark.asyncio
async def test_resolve_project_folder_path_rejects_unowned() -> None:
    """The chat resolver returns None when the folder isn't owned by the caller."""
    from leagent.api.v1.chat import _resolve_project_folder_path

    class _MockSession:
        async def __aenter__(self) -> "_MockSession":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            return None

    class _MockDB:
        def session(self) -> _MockSession:
            return _MockSession()

    # Patch out the load helper so it returns a folder owned by another user.
    import leagent.api.v1.chat as chat_mod

    other_user = uuid4()

    async def _fake_load(_session: Any, _model: Any, fid: Any, parent_table: str = "") -> Any:
        return type(
            "Folder",
            (),
            {
                "id": fid,
                "is_deleted": False,
                "is_project": True,
                "user_id": other_user,
                "project_path": "/tmp/whatever",
            },
        )()

    # The function imports the helper inside its body, so monkeypatch the
    # reference on the source module the import resolves to.
    from leagent.db import sqlite_compat

    original = sqlite_compat.load_entity_by_id
    sqlite_compat.load_entity_by_id = _fake_load  # type: ignore[assignment]
    try:
        path = await _resolve_project_folder_path(uuid4(), _MockDB(), str(uuid4()))
    finally:
        sqlite_compat.load_entity_by_id = original  # type: ignore[assignment]

    assert path is None

    # Silence "unused" warnings for chat_mod.
    assert chat_mod is not None
