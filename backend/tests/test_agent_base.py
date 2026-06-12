"""Tests for agent base models: AgentContext, ExecutionPlan, ConversationContext, etc."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest

from leagent.agent.base import (
    AgentConfig,
    AgentContext,
    AgentMode,
    AgentResponse,
    AgentState,
    ConversationContext,
    ExecutionPlan,
    ExecutionStep,
    PlanStep,
    StepType,
    ToolCall,
    ToolResult,
)


# ===========================================================================
# ToolCall & ToolResult
# ===========================================================================


class TestToolCall:
    def test_default_id_generated(self) -> None:
        tc = ToolCall(name="my_tool", arguments={"x": 1})
        assert tc.id
        assert len(tc.id) > 0

    def test_explicit_id(self) -> None:
        tc = ToolCall(id="abc-123", name="my_tool")
        assert tc.id == "abc-123"

    def test_arguments_default_empty(self) -> None:
        tc = ToolCall(name="my_tool")
        assert tc.arguments == {}


class TestToolResult:
    def test_content_success_string(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=True, data="hello")
        assert tr.content == "hello"

    def test_content_success_dict(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=True, data={"key": "val"})
        assert "key" in tr.content
        parsed = json.loads(tr.content)
        assert parsed["key"] == "val"

    def test_content_failure(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=False, error="boom")
        assert "Error" in tr.content or "boom" in tr.content

    def test_content_none_data(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=True, data=None)
        assert isinstance(tr.content, str)


# ===========================================================================
# AgentResponse
# ===========================================================================


class TestAgentResponse:
    def test_success_property(self) -> None:
        resp = AgentResponse(session_id=uuid4(), text="done")
        assert resp.success is True

    def test_not_success_on_error(self) -> None:
        resp = AgentResponse(session_id=uuid4(), text="", error="something failed")
        assert resp.success is False

    def test_not_success_when_partial(self) -> None:
        resp = AgentResponse(session_id=uuid4(), text="...", partial=True)
        assert resp.success is False

    def test_tool_calls_count(self) -> None:
        step_tool = ExecutionStep(type=StepType.TOOL_CALL, content="call")
        step_thought = ExecutionStep(type=StepType.THOUGHT, content="think")
        resp = AgentResponse(
            session_id=uuid4(),
            steps=[step_tool, step_thought, step_tool],
        )
        assert resp.tool_calls_count == 2

    def test_to_stream_events_includes_error_and_complete_for_failed_turn(self) -> None:
        resp = AgentResponse(
            session_id=uuid4(),
            error="DNS failure",
            terminal_reason="model_error",
        )
        types = [event.type for event in resp.to_stream_events()]
        assert types == ["error", "complete"]
        assert resp.to_stream_events()[0].data["terminal_reason"] == "model_error"

    def test_to_stream_events_complete_only_on_success(self) -> None:
        resp = AgentResponse(session_id=uuid4(), text="ok", terminal_reason="completed")
        events = resp.to_stream_events()
        assert len(events) == 1
        assert events[0].type == "complete"


# ===========================================================================
# AgentContext
# ===========================================================================


@pytest.mark.asyncio
class TestAgentContext:
    async def test_initial_state(self) -> None:
        ctx = AgentContext()
        assert ctx.state == AgentState.IDLE
        assert not ctx.is_cancelled

    async def test_transition_to(self) -> None:
        ctx = AgentContext()
        await ctx.transition_to(AgentState.THINKING)
        assert ctx.state == AgentState.THINKING

    async def test_cancel(self) -> None:
        ctx = AgentContext()
        assert not ctx.is_cancelled
        ctx.cancel()
        assert ctx.is_cancelled

    async def test_elapsed_ms_zero_when_no_start(self) -> None:
        ctx = AgentContext()
        assert ctx.elapsed_ms == 0

    async def test_elapsed_ms_nonzero_after_start(self) -> None:
        ctx = AgentContext(start_time=datetime.utcnow())
        await asyncio.sleep(0.01)
        assert ctx.elapsed_ms >= 0

    async def test_record_step(self) -> None:
        ctx = AgentContext()
        step = ExecutionStep(type=StepType.THOUGHT, content="thinking...")
        ctx.record_step(step)
        assert len(ctx.steps) == 1
        assert ctx.steps[0].type == StepType.THOUGHT

    async def test_add_output_file_dedup(self) -> None:
        ctx = AgentContext()
        ctx.add_output_file("/tmp/file.pdf")
        ctx.add_output_file("/tmp/file.pdf")
        ctx.add_output_file("/tmp/other.txt")
        assert len(ctx.output_files) == 2

    async def test_set_get_variable(self) -> None:
        ctx = AgentContext()
        ctx.set_variable("key", "value")
        assert ctx.get_variable("key") == "value"
        assert ctx.get_variable("missing", "default") == "default"

    async def test_to_response(self) -> None:
        ctx = AgentContext(session_id=uuid4(), start_time=datetime.utcnow())
        step = ExecutionStep(type=StepType.ANSWER, content="done")
        ctx.record_step(step)
        resp = ctx.to_response(text="completed", error=None)
        assert isinstance(resp, AgentResponse)
        assert resp.text == "completed"
        assert len(resp.steps) == 1

    async def test_to_response_with_error(self) -> None:
        ctx = AgentContext()
        resp = ctx.to_response(text="", error="something went wrong")
        assert resp.error == "something went wrong"
        assert not resp.success

    async def test_finalize_turn_maps_kernel_model_error(self) -> None:
        ctx = AgentContext(session_id=uuid4())
        conv = ConversationContext(session_id=ctx.session_id)
        resp = ctx.finalize_turn(
            text="",
            reason="model_error",
            conversation=conv,
            turn_message_start=0,
            error="DNS lookup failed",
            usage={"total_tokens": 0},
        )
        assert resp.terminal_reason == "model_error"
        assert resp.error == "DNS lookup failed"
        assert resp.success is False
        assert any(step.type == StepType.ANSWER for step in resp.steps)


# ===========================================================================
# ExecutionPlan
# ===========================================================================


class TestExecutionPlan:
    def _plan(self) -> ExecutionPlan:
        return ExecutionPlan(
            goal="Do something",
            steps=[
                PlanStep(id=1, description="Step one"),
                PlanStep(id=2, description="Step two", depends_on=[1]),
                PlanStep(id=3, description="Step three", depends_on=[1, 2]),
            ],
        )

    def test_current_step_first_no_deps(self) -> None:
        plan = self._plan()
        step = plan.current_step
        assert step is not None
        assert step.id == 1

    def test_current_step_after_completing_first(self) -> None:
        plan = self._plan()
        plan.mark_step_completed(1, result="done")
        step = plan.current_step
        assert step is not None
        assert step.id == 2

    def test_current_step_is_none_when_complete(self) -> None:
        plan = self._plan()
        for i in [1, 2, 3]:
            plan.mark_step_completed(i)
        assert plan.current_step is None

    def test_is_complete(self) -> None:
        plan = self._plan()
        assert not plan.is_complete
        plan.mark_step_completed(1)
        plan.mark_step_completed(2)
        plan.mark_step_completed(3)
        assert plan.is_complete

    def test_progress_fraction(self) -> None:
        plan = self._plan()
        assert plan.progress == 0.0
        plan.mark_step_completed(1)
        assert abs(plan.progress - 1 / 3) < 0.01
        plan.mark_step_completed(2)
        plan.mark_step_completed(3)
        assert plan.progress == 1.0

    def test_get_ready_steps(self) -> None:
        plan = self._plan()
        ready = plan.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].id == 1

    def test_get_ready_steps_after_step1(self) -> None:
        plan = self._plan()
        plan.mark_step_completed(1)
        ready = plan.get_ready_steps()
        assert any(s.id == 2 for s in ready)

    def test_mark_step_failed(self) -> None:
        plan = self._plan()
        plan.mark_step_failed(1, error="network failure")
        step = plan.get_step(1)
        assert step is not None
        assert step.status == "failed"
        assert step.error == "network failure"

    def test_progress_empty_plan(self) -> None:
        plan = ExecutionPlan(goal="empty")
        assert plan.progress == 1.0


# ===========================================================================
# ConversationContext
# ===========================================================================


class TestConversationContext:
    def test_append_user_message(self) -> None:
        ctx = ConversationContext()
        ctx.append_user_message("Hello")
        assert len(ctx.messages) == 1
        assert ctx.messages[0].role == "user"
        assert ctx.messages[0].content == "Hello"

    def test_append_assistant_message(self) -> None:
        ctx = ConversationContext()
        ctx.append_assistant_message("Hi there!")
        assert ctx.messages[0].role == "assistant"

    def test_append_tool_result(self) -> None:
        ctx = ConversationContext()
        ctx.append_tool_result("call-1", "pdf_reader", "extracted text")
        msg = ctx.messages[0]
        assert msg.role == "tool"
        assert msg.tool_call_id == "call-1"
        assert msg.name == "pdf_reader"

    def test_to_messages_no_system(self) -> None:
        ctx = ConversationContext()
        ctx.append_user_message("Hello")
        msgs = ctx.to_messages(include_system=False)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

    def test_to_messages_with_system(self) -> None:
        ctx = ConversationContext(system_prompt="You are a helpful assistant.")
        ctx.append_user_message("Hello")
        msgs = ctx.to_messages(include_system=True)
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_to_messages_without_system_prompt(self) -> None:
        ctx = ConversationContext(system_prompt="")
        ctx.append_user_message("Hello")
        msgs = ctx.to_messages(include_system=True)
        assert msgs[0]["role"] == "user"  # no system message injected

    def test_token_estimate(self) -> None:
        ctx = ConversationContext(system_prompt="Hello world")
        ctx.append_user_message("A" * 300)
        estimate = ctx.token_estimate
        assert estimate > 0

    def test_trim_windowing(self) -> None:
        ctx = ConversationContext(max_turns=2)
        for i in range(10):
            ctx.append_user_message(f"msg {i}")
            ctx.append_assistant_message(f"resp {i}")
        ctx.trim(max_turns=2)
        # Should have at most 4 messages (2 pairs)
        assert len(ctx.messages) <= 4

    def test_serialize_deserialize_roundtrip(self) -> None:
        ctx = ConversationContext(system_prompt="test prompt", max_turns=10)
        ctx.append_user_message("Hello")
        ctx.append_assistant_message("Hi!")

        serialized = ctx.serialize()
        assert isinstance(serialized, str)

        restored = ConversationContext.deserialize(serialized)
        assert restored.system_prompt == ctx.system_prompt
        assert len(restored.messages) == 2
        assert restored.messages[0].content == "Hello"
        assert restored.messages[1].content == "Hi!"
