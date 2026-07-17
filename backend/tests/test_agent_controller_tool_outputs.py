from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from leagent.agent.base import AgentConfig, AgentContext, ToolResult
from leagent.agent.script_agent import build_script_execution_agent
from leagent.agent.controller import AgentController
from leagent.tools.registry import ToolRegistry


class _FakeSessionManager:
    def __init__(self) -> None:
        self.registered: list[dict[str, Any]] = []

    async def register_external_file(
        self,
        session_id,
        user_id,
        source_path: str,
        *,
        display_name: str | None = None,
        allowed_roots=None,
    ) -> dict[str, Any] | None:
        path = Path(source_path).expanduser().resolve()
        if not path.is_file():
            return None
        roots = tuple(str(Path(root).expanduser().resolve()) for root in (allowed_roots or ()))
        self.registered.append(
            {
                "path": str(path),
                "display_name": display_name,
                "allowed_roots": roots,
            }
        )
        return {
            "id": str(uuid4()),
            "filename": display_name or path.name,
            "name": display_name or path.name,
            "kind": "text",
            "content_type": "text/plain",
            "size": path.stat().st_size,
            "preview_url": "/preview",
            "download_url": "/download",
        }

    async def promote_tool_output(
        self,
        session_id,
        user_id,
        *,
        path: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        content_type: str | None = None,
        source_tool_path: str | None = None,
        allowed_roots=None,
        origin_ref: str | None = None,
    ) -> dict[str, Any] | None:
        assert path is not None and data is None
        return await self.register_external_file(
            session_id,
            user_id,
            str(path),
            display_name=filename,
            allowed_roots=allowed_roots,
        )


class _CaptureHandler:
    def __init__(self) -> None:
        self.attachments: list[dict[str, Any]] = []

    async def on_workspace_attachments(self, items: list[dict[str, Any]]) -> None:
        self.attachments.extend(items)


def _controller(session_manager: Any | None = None) -> AgentController:
    return AgentController(
        llm=MagicMock(),
        tools=MagicMock(),
        planner=MagicMock(),
        executor=MagicMock(),
        session_manager=session_manager,
    )


async def _finalize_single_tool_call(name: str, raw_args: str) -> dict[str, Any]:
    """Drive one coalesced tool call through the production recovery path."""
    from leagent.agent.deps import _finalize_pending_tool_calls

    pending = {0: {"id": "call_1", "name": name, "arguments": raw_args}}
    events = await _finalize_pending_tool_calls(pending, {}, session_id=None)
    tool_calls = [e.tool_call for e in events if e.tool_call]
    assert len(tool_calls) == 1
    return tool_calls[0]


@pytest.mark.asyncio
async def test_finalize_recovers_code_execution_source_from_malformed_json() -> None:
    raw_args = '{"source": "\nprint("broken json")\n"}'

    call = await _finalize_single_tool_call("code_execution", raw_args)

    assert call["name"] == "code_execution"
    assert call["arguments"].get("source") == '\nprint("broken json")\n'


@pytest.mark.asyncio
async def test_finalize_preserves_unrecoverable_arguments_as_raw() -> None:
    raw_args = '{"value": "broken"'

    call = await _finalize_single_tool_call("echo_tool", raw_args)

    assert call["arguments"] == {"__raw__": raw_args}


def test_script_execution_agent_uses_script_agent_prompt_variant() -> None:
    parent = SimpleNamespace(
        llm=MagicMock(),
        tools=ToolRegistry(),
        agent_memory=None,
        session_manager=None,
        planner=MagicMock(),
        executor=SimpleNamespace(service_manager=None),
        config=AgentConfig(),
        _hooks=None,
        _permission_context=None,
    )

    agent = build_script_execution_agent(parent=parent)

    assert agent.config.agent_name == "script_agent"
    assert agent.config.prompt_variant == "script_agent"


@pytest.mark.asyncio
async def test_ingests_code_execution_workspace_produced_files(tmp_path: Path) -> None:
    workspace = tmp_path / "code-workspace"
    workspace.mkdir()
    output = workspace / "out.txt"
    output.write_text("hello", encoding="utf-8")
    session_manager = _FakeSessionManager()
    controller = _controller(session_manager=session_manager)
    context = AgentContext()
    handler = _CaptureHandler()

    await controller._ingest_produced_path_for_workspace(
        context,
        ToolResult(
            tool_call_id="call_1",
            name="code_execution",
            success=True,
            data={
                "workspace": str(workspace),
                "produced_files": [{"path": "out.txt", "bytes": output.stat().st_size}],
            },
        ),
        context.session_id,
        context.user_id,
        handler,
    )

    assert session_manager.registered == [
        {
            "path": str(output.resolve()),
            "display_name": "out.txt",
            "allowed_roots": (str(workspace.resolve()),),
        }
    ]
    assert context.output_files == [str(output.resolve())]
    assert handler.attachments[0]["filename"] == "out.txt"


@pytest.mark.asyncio
async def test_ingests_nested_saved_to_result_path(tmp_path: Path) -> None:
    output = tmp_path / "文章_英文翻译.txt"
    output.write_text("translated", encoding="utf-8")
    session_manager = _FakeSessionManager()
    controller = _controller(session_manager=session_manager)
    context = AgentContext()
    handler = _CaptureHandler()

    await controller._ingest_produced_path_for_workspace(
        context,
        ToolResult(
            tool_call_id="call_1",
            name="code_execution",
            success=True,
            data={"result": {"saved_to": str(output)}},
        ),
        context.session_id,
        context.user_id,
        handler,
    )

    assert session_manager.registered[0]["path"] == str(output.resolve())
    assert session_manager.registered[0]["display_name"] == "文章_英文翻译.txt"
    assert session_manager.registered[0]["allowed_roots"] == ()
    assert handler.attachments[0]["filename"] == "文章_英文翻译.txt"


@pytest.mark.asyncio
async def test_ingests_file_manager_destination(tmp_path: Path) -> None:
    dest = tmp_path / "copied.txt"
    dest.write_text("x", encoding="utf-8")
    session_manager = _FakeSessionManager()
    controller = _controller(session_manager=session_manager)
    context = AgentContext()
    handler = _CaptureHandler()

    await controller._ingest_produced_path_for_workspace(
        context,
        ToolResult(
            tool_call_id="call_1",
            name="file_manager",
            success=True,
            data={
                "source": str(tmp_path / "missing.txt"),
                "destination": str(dest),
                "success": True,
            },
        ),
        context.session_id,
        context.user_id,
        handler,
    )

    assert len(session_manager.registered) == 1
    assert session_manager.registered[0]["path"] == str(dest.resolve())


@pytest.mark.asyncio
async def test_ingests_json_string_data_with_output_path(tmp_path: Path) -> None:
    out = tmp_path / "from-json.txt"
    out.write_text("j", encoding="utf-8")
    session_manager = _FakeSessionManager()
    controller = _controller(session_manager=session_manager)
    context = AgentContext()
    handler = _CaptureHandler()

    payload = json.dumps({"output_path": str(out), "success": True})
    await controller._ingest_produced_path_for_workspace(
        context,
        ToolResult(
            tool_call_id="call_1",
            name="excel_generator",
            success=True,
            data=payload,
        ),
        context.session_id,
        context.user_id,
        handler,
    )

    assert len(session_manager.registered) == 1
    assert session_manager.registered[0]["path"] == str(out.resolve())
