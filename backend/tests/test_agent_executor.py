"""Tests for agent ToolExecutor, ResultProcessor, and ErrorRecovery."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from leagent.agent.base import AgentContext, ToolCall, ToolResult
from leagent.agent.executor import ErrorRecovery, ResultProcessor, ToolExecutor
from leagent.exceptions.tool import (
    ToolExecutionError,
    ToolTimeoutError,
    ToolValidationError,
)
from leagent.tools.base import SyncTool, ToolCategory, ToolContext
from leagent.tools.base import ToolResult as BaseToolResult
from leagent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Minimal tool stubs
# ---------------------------------------------------------------------------


class _EchoTool(SyncTool):
    name = "echo_tool"
    description = "Echoes the value parameter"
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext | None = None) -> dict[str, Any]:
        return {"echo": params["value"]}


class _FailTool(SyncTool):
    name = "fail_tool"
    description = "Always fails"
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute_sync(self, params: dict[str, Any], context: ToolContext | None = None) -> dict[str, Any]:
        raise RuntimeError("intentional failure from fail_tool")


def _registry(*tools: SyncTool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def _agent_ctx() -> AgentContext:
    return AgentContext(task_id=uuid4(), session_id=uuid4())


# ===========================================================================
# ToolExecutor.run_tool
# ===========================================================================


@pytest.mark.asyncio
class TestAgentToolExecutorRunTool:
    async def test_success(self) -> None:
        executor = ToolExecutor(registry=_registry(_EchoTool()))
        result = await executor.run_tool("echo_tool", {"value": "hi"})
        assert result.success
        assert result.data is not None

    async def test_not_found_returns_error(self) -> None:
        executor = ToolExecutor(registry=_registry())
        result = await executor.run_tool("nonexistent_tool", {})
        assert not result.success
        assert "not found" in (result.error or "").lower()

    async def test_failure_tool(self) -> None:
        executor = ToolExecutor(registry=_registry(_FailTool()))
        result = await executor.run_tool("fail_tool", {})
        assert not result.success
        assert "intentional failure" in (result.error or "")

    async def test_with_agent_context(self) -> None:
        executor = ToolExecutor(registry=_registry(_EchoTool()))
        ctx = _agent_ctx()
        result = await executor.run_tool("echo_tool", {"value": "ctx test"}, context=ctx)
        assert result.success


# ===========================================================================
# ToolExecutor.run_tools_parallel
# ===========================================================================


@pytest.mark.asyncio
class TestAgentToolExecutorParallel:
    async def test_parallel_all_success(self) -> None:
        executor = ToolExecutor(registry=_registry(_EchoTool()))
        calls = [
            ToolCall(name="echo_tool", arguments={"value": f"v{i}"})
            for i in range(4)
        ]
        results = await executor.run_tools_parallel(calls)
        assert len(results) == 4
        assert all(r.success for r in results)

    async def test_parallel_mixed_results(self) -> None:
        executor = ToolExecutor(registry=_registry(_EchoTool(), _FailTool()))
        calls = [
            ToolCall(name="echo_tool", arguments={"value": "ok"}),
            ToolCall(name="fail_tool", arguments={}),
        ]
        results = await executor.run_tools_parallel(calls)
        assert len(results) == 2
        successes = sum(1 for r in results if r.success)
        failures = sum(1 for r in results if not r.success)
        assert successes == 1
        assert failures == 1

    async def test_parallel_empty_returns_empty(self) -> None:
        executor = ToolExecutor(registry=_registry())
        results = await executor.run_tools_parallel([])
        assert results == []


# ===========================================================================
# ResultProcessor
# ===========================================================================


class TestResultProcessor:
    def test_normalize_none(self) -> None:
        result = ResultProcessor.normalize(None)
        assert result["success"] is True
        assert result["data"] is None

    def test_normalize_dict(self) -> None:
        d = {"key": "val", "num": 42}
        result = ResultProcessor.normalize(d)
        assert result is d  # dict returned as-is

    def test_normalize_list(self) -> None:
        lst = [1, 2, 3]
        result = ResultProcessor.normalize(lst)
        assert result["success"] is True
        assert result["data"] == [1, 2, 3]
        assert result["count"] == 3

    def test_normalize_string(self) -> None:
        result = ResultProcessor.normalize("hello world")
        assert result["data"] == "hello world"
        assert result["length"] == 11

    def test_normalize_number(self) -> None:
        result = ResultProcessor.normalize(42)
        assert result["data"] == 42

    def test_normalize_pydantic_model(self) -> None:
        from pydantic import BaseModel

        class _M(BaseModel):
            x: int = 1
            y: str = "y"

        result = ResultProcessor.normalize(_M())
        assert result["x"] == 1
        assert result["y"] == "y"

    def test_summarize_success_string(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=True, data="short string")
        summary = ResultProcessor.summarize(tr)
        assert summary == "short string"

    def test_summarize_success_long_string_truncated(self) -> None:
        long_str = "x" * 1000
        tr = ToolResult(tool_call_id="1", name="t", success=True, data=long_str)
        summary = ResultProcessor.summarize(tr, max_length=100)
        assert len(summary) <= 103  # 100 + "..."
        assert summary.endswith("...")

    def test_summarize_error(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=False, error="timeout occurred")
        summary = ResultProcessor.summarize(tr)
        assert "Error" in summary
        assert "timeout occurred" in summary

    def test_summarize_dict(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=True, data={"a": 1, "b": 2})
        summary = ResultProcessor.summarize(tr)
        assert "keys" in summary.lower()

    def test_summarize_list(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=True, data=[1, 2, 3, 4, 5])
        summary = ResultProcessor.summarize(tr)
        assert "5" in summary

    def test_summarize_none_data(self) -> None:
        tr = ToolResult(tool_call_id="1", name="t", success=True, data=None)
        summary = ResultProcessor.summarize(tr)
        assert "no output" in summary.lower() or summary

    # ---- extract_files --------------------------------------------------

    def test_extract_files_single_file_key(self) -> None:
        tr = ToolResult(
            tool_call_id="1",
            name="t",
            success=True,
            data={"file_path": "/tmp/out.csv"},
        )
        assert ResultProcessor.extract_files(tr) == ["/tmp/out.csv"]

    def test_extract_files_produced_files_list(self) -> None:
        tr = ToolResult(
            tool_call_id="1",
            name="t",
            success=True,
            data={"produced_files": ["/tmp/a.csv", "/tmp/b.csv"]},
        )
        assert ResultProcessor.extract_files(tr) == ["/tmp/a.csv", "/tmp/b.csv"]

    def test_extract_files_artifact_refs(self) -> None:
        tr = ToolResult(
            tool_call_id="1",
            name="t",
            success=True,
            data={
                "artifacts": [
                    {"uri": "file:///tmp/x.json", "kind": "json"},
                    {"path": "/tmp/y.png"},
                    "not-a-dict-string-ok",
                ],
            },
        )
        files = ResultProcessor.extract_files(tr)
        assert files == [
            "file:///tmp/x.json",
            "/tmp/y.png",
            "not-a-dict-string-ok",
        ]

    def test_extract_files_dedups_and_preserves_order(self) -> None:
        tr = ToolResult(
            tool_call_id="1",
            name="t",
            success=True,
            data={
                "file_path": "/tmp/a.csv",
                "produced_files": ["/tmp/a.csv", "/tmp/b.csv"],
            },
        )
        assert ResultProcessor.extract_files(tr) == ["/tmp/a.csv", "/tmp/b.csv"]

    def test_extract_files_on_failure_returns_empty(self) -> None:
        tr = ToolResult(
            tool_call_id="1",
            name="t",
            success=False,
            error="boom",
            data={"file_path": "/tmp/a.csv"},
        )
        assert ResultProcessor.extract_files(tr) == []

    # ---- serialize_for_llm ---------------------------------------------

    def test_serialize_for_llm_string_data(self) -> None:
        base = BaseToolResult(success=True, data="hello")
        assert ResultProcessor.serialize_for_llm(base) == "hello"

    def test_serialize_for_llm_failure_surfaces_error(self) -> None:
        base = BaseToolResult(success=False, error="boom")
        assert "boom" in ResultProcessor.serialize_for_llm(base)

    def test_serialize_for_llm_dict_is_json(self) -> None:
        import json as _json

        base = BaseToolResult(success=True, data={"x": 1})
        out = ResultProcessor.serialize_for_llm(base)
        assert _json.loads(out) == {"x": 1}

    def test_serialize_for_llm_truncates_large_string(self) -> None:
        blob = "z" * 120_000
        base = BaseToolResult(success=True, data=blob)
        out = ResultProcessor.serialize_for_llm(base)
        assert len(out) < len(blob)
        assert "truncated" in out.lower()

    # ---- to_tool_result_message ----------------------------------------

    def test_to_tool_result_message_shape(self) -> None:
        base = BaseToolResult(success=True, data={"x": 1})
        msg = ResultProcessor.to_tool_result_message(
            base, tool_call_id="abc", name="echo_tool",
        )
        assert msg.tool_call_id == "abc"
        assert msg.name == "echo_tool"
        assert msg.success is True
        assert "x" in msg.content


# ===========================================================================
# ErrorRecovery
# ===========================================================================


def _call(name: str = "echo_tool", **args: Any) -> ToolCall:
    return ToolCall(name=name, arguments=args or {"value": "x"})


@pytest.mark.asyncio
class TestErrorRecovery:
    def _make(self) -> ErrorRecovery:
        executor = ToolExecutor(registry=_registry(_EchoTool()))
        return ErrorRecovery(executor)

    async def test_success_result_returned_unchanged(self) -> None:
        recovery = self._make()
        base = BaseToolResult(success=True, data="ok")
        recovered = await recovery.attempt_recovery(
            base, tool_call=_call(), context=_agent_ctx(),
        )
        assert recovered is base

    async def test_no_handler_returns_none(self) -> None:
        recovery = self._make()
        base = BaseToolResult(success=False, error="some random error")
        recovered = await recovery.attempt_recovery(
            base, tool_call=_call(), context=_agent_ctx(),
        )
        assert recovered is None

    async def test_register_and_invoke_handler(self) -> None:
        recovery = self._make()

        async def _handler(
            result: BaseToolResult,
            tool_call: ToolCall,
            context: AgentContext | None,
        ) -> BaseToolResult:
            assert tool_call.name == "echo_tool"
            return BaseToolResult(success=True, data="recovered!")

        recovery.register_handler("connection_reset", _handler)
        base = BaseToolResult(success=False, error="connection_reset occurred")
        recovered = await recovery.attempt_recovery(
            base, tool_call=_call(), context=_agent_ctx(),
        )
        assert recovered is not None
        assert recovered.success
        assert recovered.data == "recovered!"

    async def test_handler_exception_safe(self) -> None:
        recovery = self._make()

        async def _bad_handler(
            result: BaseToolResult,
            tool_call: ToolCall,
            context: AgentContext | None,
        ) -> BaseToolResult:
            raise RuntimeError("handler crashed")

        recovery.register_handler("connection_reset", _bad_handler)
        base = BaseToolResult(success=False, error="connection_reset blew up")
        # Should not propagate the exception
        recovered = await recovery.attempt_recovery(
            base, tool_call=_call(), context=_agent_ctx(),
        )
        assert recovered is None

    async def test_timeout_exception_triggers_retry(self) -> None:
        executor = MagicMock()
        executor.default_timeout = 30
        executor.run_tool = AsyncMock(
            return_value=BaseToolResult(success=True, data="retried"),
        )
        recovery = ErrorRecovery(executor)

        recovered = await recovery.attempt_recovery(
            BaseToolResult(success=False, error="timed out after 30s"),
            tool_call=_call(),
            exception=ToolTimeoutError(tool_name="echo_tool", timeout_sec=30),
        )
        assert recovered is not None
        assert recovered.success
        # Doubled timeout (60) should have been passed.
        assert executor.run_tool.await_count == 1
        kwargs = executor.run_tool.await_args.kwargs
        assert kwargs.get("timeout") == 60

    async def test_validation_error_returns_none_no_retry(self) -> None:
        executor = MagicMock()
        executor.run_tool = AsyncMock(
            return_value=BaseToolResult(success=True, data="nope"),
        )
        recovery = ErrorRecovery(executor)

        recovered = await recovery.attempt_recovery(
            BaseToolResult(success=False, error="invalid params"),
            tool_call=_call(),
            exception=ToolValidationError("bad params", tool_name="echo_tool"),
        )
        assert recovered is None
        executor.run_tool.assert_not_awaited()

    async def test_rate_limit_retries_with_backoff(self, monkeypatch: Any) -> None:
        sleeps: list[float] = []

        async def _fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

        executor = MagicMock()
        executor.run_tool = AsyncMock(
            side_effect=[
                BaseToolResult(success=False, error="429 rate limit hit"),
                BaseToolResult(success=True, data="ok finally"),
            ]
        )
        recovery = ErrorRecovery(executor)
        recovered = await recovery.attempt_recovery(
            BaseToolResult(success=False, error="429 rate limit"),
            tool_call=_call(),
        )
        assert recovered is not None
        assert recovered.success
        assert len(sleeps) == 2  # two backoff attempts before success

    async def test_as_middleware_invokes_recovery_on_failure(self) -> None:
        executor = MagicMock()
        executor.default_timeout = 30
        # First run fails (timeout); recovery re-runs and succeeds.
        executor.run_tool = AsyncMock(
            side_effect=[
                BaseToolResult(success=False, error="timeout after 30s"),
                BaseToolResult(success=True, data="recovered"),
            ]
        )
        recovery = ErrorRecovery(executor)
        dispatch = recovery.as_middleware()
        result = await dispatch(_call())
        assert result.success
        assert result.data == "recovered"
        assert executor.run_tool.await_count == 2

    async def test_as_middleware_reraises_when_recovery_none(self) -> None:
        executor = MagicMock()
        executor.run_tool = AsyncMock(
            side_effect=ToolExecutionError("boom", tool_name="echo_tool"),
        )
        recovery = ErrorRecovery(executor)
        dispatch = recovery.as_middleware()
        with pytest.raises(ToolExecutionError):
            await dispatch(_call())
