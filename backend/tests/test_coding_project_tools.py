"""Unit tests for the LLM-facing coding-project tools.

The tools are thin wrappers around the manager, so we patch the
``get_coding_projects_service`` helper to return a hand-rolled mock
manager and exercise the tool envelopes (parameter validation,
error mapping, output shape).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from leagent.services.database.models import (
    CodingProject,
    CodingProjectRuntimeKind,
    CodingProjectStatus,
)
from leagent.tools.base import ToolContext
from leagent.project.scaffold.tools import (
    CodingProjectLogsTool,
    CodingProjectReadTool,
    CodingProjectRunTool,
    CodingProjectScaffoldTool,
    CodingProjectStatusTool,
    CodingProjectStopTool,
)


def _project(user_id: UUID, **overrides: Any) -> CodingProject:
    base = dict(
        id=uuid4(),
        user_id=user_id,
        folder_id=None,
        name="demo",
        description=None,
        template="vanilla-html",
        runtime_kind=CodingProjectRuntimeKind.FRONTEND,
        root_path="/tmp/demo",
        port=None,
        pid=None,
        status=CodingProjectStatus.IDLE,
        last_started_at=None,
        last_stopped_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_deleted=False,
    )
    base.update(overrides)
    return CodingProject(**base)


@pytest.fixture()
def patched_manager(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    manager = MagicMock()
    manager.scaffold = AsyncMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    manager.get_for_user = AsyncMock()
    manager.snapshot_logs = MagicMock(return_value=[])
    sup = MagicMock()
    sup.is_running = MagicMock(return_value=False)
    manager.supervisor = sup
    manager.build_preview_url = MagicMock(
        side_effect=lambda pid, token, sub_path="": f"/api/v1/coding-projects/{pid}/preview/?token={token}"
    )

    monkeypatch.setattr(
        "leagent.project.scaffold.tools._get_manager",
        lambda: manager,
    )
    return manager


@pytest.fixture()
def authed_context() -> ToolContext:
    return ToolContext(
        user_id=str(uuid4()),
        session_id=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_scaffold_tool_returns_project_envelope(
    patched_manager: MagicMock, authed_context: ToolContext
) -> None:
    user_id = UUID(authed_context.user_id)
    patched_manager.scaffold.return_value = _project(user_id, name="x")

    tool = CodingProjectScaffoldTool()
    result = await tool.execute(
        {"name": "x", "template": "vanilla-html"},
        authed_context,
    )
    assert result["name"] == "x"
    assert result["template"] == "vanilla-html"
    assert result["runtime_kind"] == "frontend"
    patched_manager.scaffold.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_tool_surfaces_preview_url(
    patched_manager: MagicMock, authed_context: ToolContext
) -> None:
    user_id = UUID(authed_context.user_id)
    project = _project(user_id, status=CodingProjectStatus.RUNNING, port=39000)
    running = MagicMock(host="127.0.0.1", port=39000, pid=42, run_seq=1)
    patched_manager.start.return_value = (project, running, "T-OK")

    tool = CodingProjectRunTool()
    result = await tool.execute(
        {"project_id": str(project.id)}, authed_context
    )
    assert result["status"] == "running"
    assert result["preview_token"] == "T-OK"
    assert "preview/" in result["preview_url"]


@pytest.mark.asyncio
async def test_run_tool_returns_error_envelope_on_exception(
    patched_manager: MagicMock, authed_context: ToolContext
) -> None:
    patched_manager.start.side_effect = RuntimeError("boom")
    tool = CodingProjectRunTool()
    result = await tool.execute(
        {"project_id": str(uuid4())}, authed_context
    )
    assert "error" in result
    assert "boom" in result["error"]


@pytest.mark.asyncio
async def test_stop_tool_idempotent(
    patched_manager: MagicMock, authed_context: ToolContext
) -> None:
    user_id = UUID(authed_context.user_id)
    project = _project(user_id, status=CodingProjectStatus.IDLE)
    patched_manager.stop.return_value = project

    tool = CodingProjectStopTool()
    result = await tool.execute(
        {"project_id": str(project.id)}, authed_context
    )
    assert result["status"] == "idle"


@pytest.mark.asyncio
async def test_status_and_logs(
    patched_manager: MagicMock, authed_context: ToolContext
) -> None:
    user_id = UUID(authed_context.user_id)
    project = _project(user_id, status=CodingProjectStatus.RUNNING, port=42)
    patched_manager.get_for_user.return_value = project

    status_tool = CodingProjectStatusTool()
    status_result = await status_tool.execute(
        {"project_id": str(project.id)}, authed_context
    )
    assert status_result["status"] == "running"
    assert status_result["port"] == 42

    logs_tool = CodingProjectLogsTool()
    log_result = await logs_tool.execute(
        {"project_id": str(project.id)}, authed_context
    )
    assert "log_lines" in log_result


@pytest.mark.asyncio
async def test_tool_requires_authenticated_user_id() -> None:
    tool = CodingProjectStatusTool()
    bare = ToolContext(user_id=None, session_id=None)
    with pytest.raises(PermissionError):
        await tool.execute({"project_id": str(uuid4())}, bare)


@pytest.mark.asyncio
async def test_logs_tool_friendly_error_on_truncated_project_id(
    patched_manager: MagicMock, authed_context: ToolContext
) -> None:
    """LLM-truncated UUIDs must not surface as raw ValueError from uuid.UUID."""
    tool = CodingProjectLogsTool()
    result = await tool.execute(
        {
            "project_id": "91480013-a277-4bb7-97fa-7ac65827a33",
            "max_lines": 10,
        },
        authed_context,
    )
    assert "error" in result
    assert "project_id" in result["error"]
    assert "36 characters" in result["error"]
    patched_manager.get_for_user.assert_not_called()


@pytest.mark.asyncio
async def test_scaffold_rejects_malformed_folder_id(
    patched_manager: MagicMock, authed_context: ToolContext
) -> None:
    tool = CodingProjectScaffoldTool()
    result = await tool.execute(
        {
            "name": "demo",
            "template": "vanilla-html",
            "folder_id": "91480013-a277-4bb7-97fa-7ac65827a33",
        },
        authed_context,
    )
    assert "error" in result
    assert "folder_id" in result["error"]
    patched_manager.scaffold.assert_not_called()


@pytest.mark.asyncio
async def test_read_tool_returns_line_numbered_content(
    patched_manager: MagicMock, authed_context: ToolContext, tmp_path
) -> None:
    user_id = UUID(authed_context.user_id)
    root = tmp_path / "proj"
    root.mkdir()
    (root / "hello.txt").write_text("alpha\nbeta\n", encoding="utf-8")
    project = _project(user_id, root_path=str(root))
    patched_manager.get_for_user.return_value = project

    tool = CodingProjectReadTool()
    result = await tool.execute(
        {"project_id": str(project.id), "path": "hello.txt"},
        authed_context,
    )
    assert "error" not in result
    assert result["path"] == "hello.txt"
    assert "1|alpha" in result["content"]
    assert "2|beta" in result["content"]
    patched_manager.get_for_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_tool_rejects_path_escape(
    patched_manager: MagicMock, authed_context: ToolContext, tmp_path
) -> None:
    user_id = UUID(authed_context.user_id)
    root = tmp_path / "proj"
    root.mkdir()
    project = _project(user_id, root_path=str(root))
    patched_manager.get_for_user.return_value = project

    tool = CodingProjectReadTool()
    result = await tool.execute(
        {
            "project_id": str(project.id),
            "path": "../../../etc/passwd",
        },
        authed_context,
    )
    assert "error" in result
    assert "outside" in result["error"].lower()


@pytest.mark.asyncio
async def test_read_tool_friendly_error_on_truncated_project_id(
    patched_manager: MagicMock, authed_context: ToolContext
) -> None:
    tool = CodingProjectReadTool()
    result = await tool.execute(
        {
            "project_id": "91480013-a277-4bb7-97fa-7ac65827a33",
            "path": "x.txt",
        },
        authed_context,
    )
    assert "error" in result
    assert "project_id" in result["error"]
    assert "36 characters" in result["error"]
    patched_manager.get_for_user.assert_not_called()
