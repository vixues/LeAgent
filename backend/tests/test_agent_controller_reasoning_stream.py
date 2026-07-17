"""``_run_via_query_engine`` forwards ``reasoning_delta`` to ``on_thinking`` (cumulative)."""

from __future__ import annotations

import asyncio
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from leagent.agent import query_engine as qe_mod
from leagent.agent.base import (
    AgentConfig,
    AgentContext,
    AgentMode,
    AgentResponse,
    AgentState,
    ConversationContext,
)
from leagent.agent.controller import AgentController
from leagent.agent.query_engine import SDKMessage


class _FakeEngineBase:
    """Minimal QueryEngine stand-in compatible with ``run_loop``."""

    def __init__(self, config: object) -> None:
        self.config = config
        self.abort_event = getattr(config, "abort_event", None) or asyncio.Event()

    def abort(self) -> None:
        self.abort_event.set()


class _FakeQueryEngine(_FakeEngineBase):
    async def submit_message(self, *_a: object, **_kw: object):
        yield SDKMessage(type="stream_delta", data={"reasoning_delta": "hel"})
        yield SDKMessage(type="stream_delta", data={"reasoning_delta": "lo"})


class _AnswerOnlyQueryEngine(_FakeEngineBase):
    async def submit_message(self, *_a: object, **_kw: object):
        yield SDKMessage(type="stream_delta", data={"content": "fresh answer"})


class _ToolUsingQueryEngine(_FakeEngineBase):
    async def submit_message(self, *_a: object, **_kw: object):
        yield SDKMessage(
            type="assistant_tools",
            data={
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_current",
                        "type": "function",
                        "function": {"name": "code_execution", "arguments": "{}"},
                    }
                ],
            },
        )
        yield SDKMessage(type="stream_delta", data={"content": "tool answer"})


@pytest.mark.asyncio
async def test_reasoning_delta_calls_on_thinking_cumulative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qe_mod, "QueryEngine", _FakeQueryEngine)

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

    sid = uuid4()
    uid = uuid4()
    ctx = AgentContext(
        task_id=uuid4(),
        session_id=sid,
        user_id=uid,
        config=controller.config,
        state=AgentState.THINKING,
    )
    conv = ConversationContext(session_id=sid)

    handler = MagicMock()
    handler.on_thinking = AsyncMock()
    handler.on_token = AsyncMock()
    handler.on_tool_call = AsyncMock()
    handler.on_tool_result = AsyncMock()
    handler.on_user_input_request = AsyncMock()
    handler.on_complete = AsyncMock()
    handler.on_error = AsyncMock()

    await controller._run_via_query_engine(
        "hi",
        conv,
        ctx,
        handler,
        skip_user_append=True,
    )

    assert [c.args[0] for c in handler.on_thinking.await_args_list] == ["hel", "hello"]
    handler.on_token.assert_not_called()


@pytest.mark.asyncio
async def test_query_engine_complete_metadata_excludes_historical_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qe_mod, "QueryEngine", _AnswerOnlyQueryEngine)

    controller = AgentController(
        llm=MagicMock(),
        tools=MagicMock(),
        planner=MagicMock(),
        executor=MagicMock(service_manager=None),
        config=AgentConfig(
            max_iterations=1,
            mode=AgentMode.REACT,
            enable_memory=False,
            enable_streaming=False,
            verbose=False,
            use_query_engine=True,
        ),
    )
    sid = uuid4()
    uid = uuid4()
    ctx = AgentContext(
        task_id=uuid4(),
        session_id=sid,
        user_id=uid,
        config=controller.config,
        state=AgentState.THINKING,
    )
    conv = ConversationContext(session_id=sid)
    conv.append_assistant_message(
        "",
        tool_calls=[
            {
                "id": "call_old",
                "type": "function",
                "function": {"name": "ask_user", "arguments": "{}"},
            }
        ],
    )
    conv.append_tool_result("call_old", "ask_user", '{"answers": {}}')
    conv.append_user_message("next question")

    handler = MagicMock()
    handler.on_thinking = AsyncMock()
    handler.on_token = AsyncMock()
    handler.on_tool_call = AsyncMock()
    handler.on_tool_result = AsyncMock()
    handler.on_user_input_request = AsyncMock()
    handler.on_complete = AsyncMock()
    handler.on_error = AsyncMock()

    await controller._run_via_query_engine(
        "next question",
        conv,
        ctx,
        handler,
        skip_user_append=True,
    )

    response = handler.on_complete.await_args.args[0]
    assert "assistant_tool_calls" not in response.metadata


@pytest.mark.asyncio
async def test_query_engine_complete_metadata_keeps_current_turn_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qe_mod, "QueryEngine", _ToolUsingQueryEngine)

    controller = AgentController(
        llm=MagicMock(),
        tools=MagicMock(),
        planner=MagicMock(),
        executor=MagicMock(service_manager=None),
        config=AgentConfig(
            max_iterations=1,
            mode=AgentMode.REACT,
            enable_memory=False,
            enable_streaming=False,
            verbose=False,
            use_query_engine=True,
        ),
    )
    sid = uuid4()
    uid = uuid4()
    ctx = AgentContext(
        task_id=uuid4(),
        session_id=sid,
        user_id=uid,
        config=controller.config,
        state=AgentState.THINKING,
    )
    conv = ConversationContext(session_id=sid)
    conv.append_user_message("run a tool")

    handler = MagicMock()
    handler.on_thinking = AsyncMock()
    handler.on_token = AsyncMock()
    handler.on_tool_call = AsyncMock()
    handler.on_tool_result = AsyncMock()
    handler.on_user_input_request = AsyncMock()
    handler.on_complete = AsyncMock()
    handler.on_error = AsyncMock()

    await controller._run_via_query_engine(
        "run a tool",
        conv,
        ctx,
        handler,
        skip_user_append=True,
    )

    response = handler.on_complete.await_args.args[0]
    assert response.metadata["assistant_tool_calls"] == [
        {
            "id": "call_current",
            "type": "function",
            "function": {"name": "code_execution", "arguments": "{}"},
        }
    ]


@pytest.mark.asyncio
async def test_run_stream_waits_for_agent_cleanup_after_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        config=AgentConfig(enable_memory=False, enable_streaming=True),
    )

    sid = uuid4()
    uid = uuid4()
    cleanup_ran = asyncio.Event()

    async def fake_run(
        self,  # noqa: ARG001
        user_input: str,  # noqa: ARG001
        session_id,
        *,
        user_id=None,  # noqa: ARG001
        attachments=None,  # noqa: ARG001
        project_roots=None,  # noqa: ARG001
        authorized_roots=None,  # noqa: ARG001
        stream_handler=None,
        skip_append_user=False,  # noqa: ARG001
        persisted_user_message_id=None,  # noqa: ARG001
        agent_task_id=None,  # noqa: ARG001
        execution_run_id=None,  # noqa: ARG001
        runtime_profile=None,  # noqa: ARG001
        checkpoint_id=None,  # noqa: ARG001
    ):
        assert stream_handler is not None
        await stream_handler.on_complete(
            AgentResponse(session_id=session_id, text="ok", success=True),
        )
        await asyncio.sleep(0)
        cleanup_ran.set()
        return AgentResponse(session_id=session_id, text="ok", success=True)

    # Bind on the instance so ``run_stream``'s nested ``create_task`` always resolves to
    # this stub (class-level patches + cached settings singletons have caused flakes).
    monkeypatch.setattr(controller, "run", MethodType(fake_run, controller))
    monkeypatch.setattr(
        "leagent.config.settings.get_settings",
        lambda: SimpleNamespace(agent=SimpleNamespace(stream_drain_timeout_sec=300)),
    )

    events = [event async for event in controller.run_stream("hi", sid, user_id=uid)]

    assert [event.type for event in events] == ["complete"]
    assert cleanup_ran.is_set()
