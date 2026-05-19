"""Tests for agent hooks: HookManager dispatch, LoggingHook, MetricsHook, RateLimitHook, etc."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from leagent.agent.base import (
    AgentContext,
    AgentResponse,
    AgentState,
    ExecutionPlan,
    ExecutionStep,
    PlanStep,
    StepType,
    ToolCall,
    ToolResult,
)
from leagent.agent.hooks import (
    AgentHook,
    HookManager,
    LoggingHook,
    MetricsHook,
    RateLimitError,
    RateLimitHook,
    TaskHistoryHook,
    create_default_hooks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx() -> AgentContext:
    return AgentContext(
        task_id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        start_time=datetime.utcnow(),
    )


def _step(step_type: StepType = StepType.THOUGHT) -> ExecutionStep:
    return ExecutionStep(type=step_type, content="test step")


def _tool_call() -> ToolCall:
    return ToolCall(name="pdf_reader", arguments={"file_path": "/tmp/test.pdf"})


def _tool_result(success: bool = True) -> ToolResult:
    return ToolResult(
        tool_call_id="call-1",
        name="pdf_reader",
        success=success,
        data="content" if success else None,
        error=None if success else "failed",
    )


def _response() -> AgentResponse:
    return AgentResponse(session_id=uuid4(), text="done")


# ---------------------------------------------------------------------------
# HookManager
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHookManager:
    async def test_dispatch_calls_all_hooks(self) -> None:
        called: list[str] = []

        class _TrackerHook(AgentHook):
            async def on_start(self, context: AgentContext, user_input: str) -> None:
                called.append("on_start")

            async def on_complete(self, context: AgentContext, response: AgentResponse) -> None:
                called.append("on_complete")

        mgr = HookManager()
        hook = _TrackerHook()
        mgr.register(hook)
        ctx = _ctx()
        await mgr.dispatch_start(ctx, "hello")
        await mgr.dispatch_complete(ctx, _response())

        assert "on_start" in called
        assert "on_complete" in called

    async def test_error_in_hook_doesnt_propagate(self) -> None:
        class _BrokenHook(AgentHook):
            async def on_start(self, context: AgentContext, user_input: str) -> None:
                raise RuntimeError("broken hook!")

        mgr = HookManager()
        mgr.register(_BrokenHook())
        ctx = _ctx()
        # Should not raise
        await mgr.dispatch_start(ctx, "hello")

    async def test_priority_ordering(self) -> None:
        order: list[int] = []

        class _HookA(AgentHook):
            priority = 10

            async def on_start(self, context: AgentContext, user_input: str) -> None:
                order.append(10)

        class _HookB(AgentHook):
            priority = 5

            async def on_start(self, context: AgentContext, user_input: str) -> None:
                order.append(5)

        class _HookC(AgentHook):
            priority = 100

            async def on_start(self, context: AgentContext, user_input: str) -> None:
                order.append(100)

        mgr = HookManager()
        mgr.register(_HookC())
        mgr.register(_HookA())
        mgr.register(_HookB())
        await mgr.dispatch_start(_ctx(), "hi")
        assert order == [5, 10, 100]

    async def test_unregister_hook(self) -> None:
        called: list[str] = []

        class _H(AgentHook):
            async def on_start(self, context: AgentContext, user_input: str) -> None:
                called.append("called")

        mgr = HookManager()
        h = _H()
        mgr.register(h)
        mgr.unregister(h)
        await mgr.dispatch_start(_ctx(), "hi")
        assert len(called) == 0

    async def test_clear(self) -> None:
        called: list[str] = []

        class _H(AgentHook):
            async def on_start(self, context: AgentContext, user_input: str) -> None:
                called.append("called")

        mgr = HookManager()
        mgr.register(_H())
        mgr.clear()
        await mgr.dispatch_start(_ctx(), "hi")
        assert len(called) == 0


# ---------------------------------------------------------------------------
# LoggingHook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLoggingHook:
    async def test_instantiation(self) -> None:
        hook = LoggingHook()
        assert hook.priority == 10

    async def test_on_start_doesnt_raise(self) -> None:
        hook = LoggingHook()
        await hook.on_start(_ctx(), "Hello, agent!")

    async def test_on_step_doesnt_raise(self) -> None:
        hook = LoggingHook()
        await hook.on_step(_ctx(), _step())

    async def test_on_tool_call_doesnt_raise(self) -> None:
        hook = LoggingHook()
        await hook.on_tool_call(_ctx(), _tool_call())

    async def test_on_complete_doesnt_raise(self) -> None:
        hook = LoggingHook()
        await hook.on_complete(_ctx(), _response())

    async def test_on_error_doesnt_raise(self) -> None:
        hook = LoggingHook()
        await hook.on_error(_ctx(), RuntimeError("test error"))


# ---------------------------------------------------------------------------
# MetricsHook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMetricsHook:
    async def test_tool_counters(self) -> None:
        hook = MetricsHook()
        ctx = _ctx()

        await hook.on_start(ctx, "do something")
        await hook.on_tool_result(ctx, _tool_call(), _tool_result(success=True))
        await hook.on_tool_result(ctx, _tool_call(), _tool_result(success=True))
        await hook.on_tool_result(ctx, _tool_call(), _tool_result(success=False))

        metrics = hook._task_metrics.get(ctx.task_id)
        assert metrics is not None
        assert metrics["tool_calls"] == 3
        assert metrics["tool_successes"] == 2
        assert metrics["tool_failures"] == 1

    async def test_step_counting(self) -> None:
        hook = MetricsHook()
        ctx = _ctx()
        await hook.on_start(ctx, "task")
        await hook.on_step(ctx, _step(StepType.THOUGHT))
        await hook.on_step(ctx, _step(StepType.THOUGHT))
        await hook.on_step(ctx, _step(StepType.TOOL_CALL))

        metrics = hook._task_metrics.get(ctx.task_id)
        assert metrics is not None
        assert metrics["steps_by_type"]["thought"] == 2
        assert metrics["steps_by_type"]["tool_call"] == 1

    async def test_cleanup_on_complete(self) -> None:
        hook = MetricsHook()
        ctx = _ctx()
        await hook.on_start(ctx, "task")
        assert ctx.task_id in hook._task_metrics

        await hook.on_complete(ctx, _response())
        assert ctx.task_id not in hook._task_metrics

    async def test_cleanup_on_error(self) -> None:
        hook = MetricsHook()
        ctx = _ctx()
        await hook.on_start(ctx, "task")
        await hook.on_error(ctx, RuntimeError("oops"))
        assert ctx.task_id not in hook._task_metrics


# ---------------------------------------------------------------------------
# RateLimitHook
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRateLimitHook:
    async def test_allows_within_limit(self) -> None:
        hook = RateLimitHook(max_tasks_per_minute=5, max_tasks_per_hour=20)
        ctx = _ctx()
        # Should not raise for first call
        await hook.on_start(ctx, "task")

    async def test_per_minute_limit(self) -> None:
        hook = RateLimitHook(max_tasks_per_minute=2, max_tasks_per_hour=100)
        user_id = uuid4()
        for i in range(2):
            ctx = AgentContext(user_id=user_id)
            await hook.on_start(ctx, f"task {i}")

        ctx = AgentContext(user_id=user_id)
        with pytest.raises(RateLimitError, match="per minute"):
            await hook.on_start(ctx, "over limit")

    async def test_per_hour_limit(self) -> None:
        hook = RateLimitHook(max_tasks_per_minute=100, max_tasks_per_hour=2)
        user_id = uuid4()
        for i in range(2):
            ctx = AgentContext(user_id=user_id)
            await hook.on_start(ctx, f"task {i}")

        ctx = AgentContext(user_id=user_id)
        with pytest.raises(RateLimitError, match="per hour"):
            await hook.on_start(ctx, "over limit")

    async def test_different_users_independent(self) -> None:
        hook = RateLimitHook(max_tasks_per_minute=1, max_tasks_per_hour=10)
        user_a = uuid4()
        user_b = uuid4()

        ctx_a = AgentContext(user_id=user_a)
        ctx_b = AgentContext(user_id=user_b)

        await hook.on_start(ctx_a, "user A task")
        # user B should still be allowed
        await hook.on_start(ctx_b, "user B task")


# ---------------------------------------------------------------------------
# TaskHistoryHook
# ---------------------------------------------------------------------------


class TestTaskHistoryHook:
    @pytest.mark.asyncio
    async def test_on_complete_calls_observe_turn_not_record_procedure(self) -> None:
        mem = MagicMock()
        mem.record_procedure = AsyncMock()
        mem.observe_turn = AsyncMock(return_value=MagicMock(targets=[], suppress=False))
        hook = TaskHistoryHook(agent_memory=mem)
        ctx = _ctx()
        await hook.on_complete(
            ctx,
            AgentResponse(session_id=ctx.session_id, text="ok"),
        )
        mem.observe_turn.assert_awaited_once()
        mem.record_procedure.assert_not_awaited()

    def test_infer_task_type_document(self) -> None:
        hook = TaskHistoryHook()
        ctx = _ctx()
        tc = ToolCall(name="pdf_reader", arguments={})
        step = ExecutionStep(type=StepType.TOOL_CALL, content="", tool_call=tc)
        ctx.steps = [step]
        assert hook._infer_task_type(ctx) == "document_processing"

    def test_infer_task_type_web(self) -> None:
        hook = TaskHistoryHook()
        ctx = _ctx()
        tc = ToolCall(name="web_scraper", arguments={})
        step = ExecutionStep(type=StepType.TOOL_CALL, content="", tool_call=tc)
        ctx.steps = [step]
        assert hook._infer_task_type(ctx) == "web_automation"

    def test_infer_task_type_general_fallback(self) -> None:
        hook = TaskHistoryHook()
        ctx = _ctx()
        ctx.steps = []
        assert hook._infer_task_type(ctx) == "general"

    def test_infer_task_type_data(self) -> None:
        hook = TaskHistoryHook()
        ctx = _ctx()
        tc = ToolCall(name="data_validator", arguments={})
        step = ExecutionStep(type=StepType.TOOL_CALL, content="", tool_call=tc)
        ctx.steps = [step]
        assert hook._infer_task_type(ctx) == "data_processing"


# ---------------------------------------------------------------------------
# create_default_hooks
# ---------------------------------------------------------------------------


class TestCreateDefaultHooks:
    def test_without_agent_memory(self) -> None:
        hooks = create_default_hooks(agent_memory=None)
        hook_types = {type(h).__name__ for h in hooks}
        assert "LoggingHook" in hook_types
        assert "MetricsHook" in hook_types
        assert "TaskHistoryHook" not in hook_types

    def test_with_agent_memory(self) -> None:
        from unittest.mock import MagicMock

        agent_memory = MagicMock()
        hooks = create_default_hooks(agent_memory=agent_memory)
        hook_types = {type(h).__name__ for h in hooks}
        assert "TaskHistoryHook" in hook_types
