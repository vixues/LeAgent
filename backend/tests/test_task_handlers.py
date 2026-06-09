"""Unit coverage for the bundled :mod:`leagent.tasks.handlers` modules.

These tests bypass :class:`TaskManager` and exercise each handler's
``spawn`` directly with a minimal :class:`TaskContext`. Heavy
dependencies (LLM, WorkflowService, other sub-tasks) are mocked out so
the tests can run without network or database.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leagent.db.models.task import (
    TaskContext,
    TaskStatus,
    TaskType,
)
from leagent.tasks.handlers import (
    AgentTaskHandler,
    BatchTaskHandler,
    ShellTaskHandler,
    ToolTaskHandler,
    WorkflowTaskHandler,
)


def _ctx(task_type: TaskType, tmp_path) -> TaskContext:
    return TaskContext(
        f"test-{task_type.value}", task_type, output_dir=str(tmp_path)
    )


# ---------------------------------------------------------------------------
# ShellTaskHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shell_handler_runs_argv(tmp_path) -> None:
    handler = ShellTaskHandler()
    ctx = _ctx(TaskType.SHELL, tmp_path)

    result = await handler.spawn(
        ctx,
        {"cmd": [sys.executable, "-c", "print('shell-handler-ok')"]},
        session=MagicMock(),
    )
    assert result["exit_code"] == 0
    with open(ctx.output_file, "r", encoding="utf-8") as f:
        contents = f.read()
    assert "shell-handler-ok" in contents


@pytest.mark.asyncio
async def test_shell_handler_rejects_missing_argv(tmp_path) -> None:
    handler = ShellTaskHandler()
    ctx = _ctx(TaskType.SHELL, tmp_path)
    with pytest.raises(ValueError, match="cmd"):
        await handler.spawn(ctx, {}, session=MagicMock())


@pytest.mark.asyncio
async def test_shell_handler_nonzero_raises(tmp_path) -> None:
    handler = ShellTaskHandler()
    ctx = _ctx(TaskType.SHELL, tmp_path)
    with pytest.raises(RuntimeError, match="exited with code"):
        await handler.spawn(
            ctx,
            {"cmd": [sys.executable, "-c", "import sys; sys.exit(3)"]},
            session=MagicMock(),
        )


# ---------------------------------------------------------------------------
# ToolTaskHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_handler_dispatches_to_executor(tmp_path) -> None:
    handler = ToolTaskHandler()
    ctx = _ctx(TaskType.TOOL, tmp_path)

    fake_result = MagicMock()
    fake_result.result.success = True
    fake_result.result.to_dict.return_value = {"stdout": "ok"}
    fake_result.duration_ms = 12

    executor = MagicMock()
    executor.execute = AsyncMock(return_value=fake_result)

    with patch(
        "leagent.tools.executor.ToolExecutor",
        return_value=executor,
    ), patch(
        "leagent.tools.registry.get_registry",
        return_value=MagicMock(),
    ):
        summary = await handler.spawn(
            ctx,
            {"tool_name": "echo", "parameters": {"text": "hi"}},
            session=MagicMock(),
        )

    executor.execute.assert_awaited_once()
    assert summary["tool_name"] == "echo"
    assert summary["success"] is True
    assert summary["output"] == {"stdout": "ok"}


@pytest.mark.asyncio
async def test_tool_handler_raises_when_tool_fails(tmp_path) -> None:
    handler = ToolTaskHandler()
    ctx = _ctx(TaskType.TOOL, tmp_path)

    fake_result = MagicMock()
    fake_result.result.success = False
    fake_result.result.to_dict.return_value = {"error": "nope"}
    fake_result.duration_ms = 4

    executor = MagicMock()
    executor.execute = AsyncMock(return_value=fake_result)

    with patch(
        "leagent.tools.executor.ToolExecutor", return_value=executor
    ), patch("leagent.tools.registry.get_registry", return_value=MagicMock()):
        with pytest.raises(RuntimeError, match="nope"):
            await handler.spawn(
                ctx, {"tool_name": "echo"}, session=MagicMock()
            )


@pytest.mark.asyncio
async def test_tool_handler_requires_tool_name(tmp_path) -> None:
    handler = ToolTaskHandler()
    ctx = _ctx(TaskType.TOOL, tmp_path)
    with pytest.raises(ValueError, match="tool_name"):
        await handler.spawn(ctx, {}, session=MagicMock())


# ---------------------------------------------------------------------------
# WorkflowTaskHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workflow_handler_invokes_service(tmp_path) -> None:
    wf_result = MagicMock()
    wf_result.to_dict.return_value = {"status": "completed", "node_count": 2}

    svc = MagicMock()
    svc.run = AsyncMock(return_value=wf_result)

    sm = MagicMock()
    sm.workflow_service = svc

    handler = WorkflowTaskHandler(service_manager=sm)
    ctx = _ctx(TaskType.WORKFLOW, tmp_path)

    summary = await handler.spawn(
        ctx,
        {
            "flow_id": "00000000-0000-0000-0000-000000000001",
            "inputs": {"a": 1},
        },
        session=MagicMock(),
    )
    svc.run.assert_awaited_once()
    assert summary["status"] == "completed"


@pytest.mark.asyncio
async def test_workflow_handler_requires_service(tmp_path) -> None:
    sm = MagicMock()
    sm.workflow_service = None
    handler = WorkflowTaskHandler(service_manager=sm)
    ctx = _ctx(TaskType.WORKFLOW, tmp_path)
    with pytest.raises(RuntimeError, match="WorkflowService"):
        await handler.spawn(
            ctx,
            {"flow_id": "00000000-0000-0000-0000-000000000001"},
            session=MagicMock(),
        )


# ---------------------------------------------------------------------------
# AgentTaskHandler
# ---------------------------------------------------------------------------


async def _fake_submit(prompt: str):
    """Emit a tiny SDK message stream for AgentTaskHandler to consume."""
    from leagent.agent.query_engine import SDKMessage

    yield SDKMessage(type="system_init", data={})
    yield SDKMessage(type="stream_delta", data={"content": "hello"})
    yield SDKMessage(type="assistant", data={"content": "hello world"})
    yield SDKMessage(
        type="result",
        data={"usage": {"total_tokens": 7}, "terminal_reason": "completed"},
    )


@pytest.mark.asyncio
async def test_agent_handler_requires_llm(tmp_path) -> None:
    sm = MagicMock()
    sm.llm_service = None
    handler = AgentTaskHandler(service_manager=sm)
    ctx = _ctx(TaskType.AGENT, tmp_path)
    with pytest.raises(RuntimeError, match="LLMService"):
        await handler.spawn(ctx, {"prompt": "hi"}, session=MagicMock())


@pytest.mark.asyncio
async def test_agent_handler_streams_query_engine(tmp_path) -> None:
    sm = MagicMock()
    sm.llm_service = MagicMock()
    handler = AgentTaskHandler(service_manager=sm)
    ctx = _ctx(TaskType.AGENT, tmp_path)

    fake_engine = MagicMock()

    def _submit(_prompt):
        return _fake_submit(_prompt)

    fake_engine.submit_message = _submit
    fake_engine.abort = MagicMock()

    with patch(
        "leagent.agent.query_engine.QueryEngine", return_value=fake_engine
    ), patch(
        "leagent.tools.executor.ToolExecutor", return_value=MagicMock()
    ), patch(
        "leagent.tools.registry.get_registry", return_value=MagicMock()
    ):
        result = await handler.spawn(
            ctx, {"prompt": "say hi"}, session=MagicMock()
        )

    assert result["text"] == "hello world"
    assert result["usage"]["total_tokens"] == 7


@pytest.mark.asyncio
async def test_agent_handler_applies_runtime_profile(tmp_path) -> None:
    sm = MagicMock()
    sm.llm_service = MagicMock()
    handler = AgentTaskHandler(service_manager=sm)
    ctx = _ctx(TaskType.AGENT, tmp_path)

    fake_engine = MagicMock()

    def _submit(_prompt):
        return _fake_submit(_prompt)

    fake_engine.submit_message = _submit
    fake_engine.abort = MagicMock()
    query_engine_ctor = MagicMock(return_value=fake_engine)
    executor_ctor = MagicMock(return_value=MagicMock())

    with patch(
        "leagent.agent.query_engine.QueryEngine", query_engine_ctor
    ), patch(
        "leagent.tools.executor.ToolExecutor", executor_ctor
    ), patch(
        "leagent.tools.registry.get_registry", return_value=MagicMock()
    ):
        result = await handler.spawn(
            ctx,
            {
                "prompt": "run tests",
                "runtime_profile": "coding_long",
                "project_roots": [str(tmp_path)],
            },
            session=MagicMock(),
        )

    cfg = query_engine_ctor.call_args.args[0]
    assert cfg.prompt_variant == "default_agent"
    assert cfg.max_turns == 60
    assert cfg.tool_extra["runtime_profile"] == "coding_long"
    assert cfg.tool_extra["project_roots"] == [str(tmp_path)]
    assert executor_ctor.call_args.kwargs["default_timeout"] == 1800.0
    assert result["runtime_profile"] == "coding_long"


# ---------------------------------------------------------------------------
# BatchTaskHandler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_batch_handler_requires_children(tmp_path) -> None:
    handler = BatchTaskHandler()
    ctx = _ctx(TaskType.BATCH, tmp_path)
    with pytest.raises(ValueError, match="children"):
        await handler.spawn(ctx, {}, session=MagicMock())


@pytest.mark.asyncio
async def test_batch_handler_spawns_children(tmp_path) -> None:
    from uuid import uuid4

    handler = BatchTaskHandler(max_concurrency=2)
    ctx = _ctx(TaskType.BATCH, tmp_path)

    child_ids = [uuid4() for _ in range(3)]

    class _FakeCreated:
        def __init__(self, tid) -> None:
            self.id = tid
            self.status = TaskStatus.COMPLETED

    created = [_FakeCreated(cid) for cid in child_ids]
    status_by_id = {str(c.id): TaskStatus.COMPLETED for c in created}

    mgr = MagicMock()
    mgr.create_task = AsyncMock(side_effect=list(created))
    mgr.start_task = AsyncMock(return_value=None)

    class _Session:
        def __init__(self) -> None:
            pass

        async def get(self, _model, pk):  # noqa: ANN001
            class _T:
                status = status_by_id[str(pk)]

            return _T()

        async def commit(self) -> None:
            return None

    class _DB:
        def session(self):
            class _Ctx:
                async def __aenter__(self_inner) -> _Session:
                    return _Session()

                async def __aexit__(self_inner, a, b, c):
                    return None

            return _Ctx()

    with patch(
        "leagent.services.task_manager.get_task_manager", return_value=mgr
    ), patch(
        "leagent.db.get_database_service", return_value=_DB()
    ):
        result = await handler.spawn(
            ctx,
            {
                "children": [
                    {"task_type": "shell", "input_data": {"cmd": ["true"]}},
                    {"task_type": "shell", "input_data": {"cmd": ["true"]}},
                    {"task_type": "shell", "input_data": {"cmd": ["true"]}},
                ],
                "poll_interval_sec": 0.01,
            },
            session=MagicMock(),
        )

    assert result["failed_count"] == 0
    assert len(result["children"]) == 3
    mgr.create_task.await_count == 3  # noqa: B015 - sanity, not an assert
    assert mgr.create_task.await_count == 3
    assert mgr.start_task.await_count == 3
