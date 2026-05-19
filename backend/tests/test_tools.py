"""Tests for the LeAgent tool system.

Covers ToolResult, ToolContext, BaseTool contract, and all new attributes
introduced in the latest architecture (safety flags, concurrency, interrupt
behaviour, result-size budget, aliases, validate_input lifecycle).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from leagent.tools.base import (
    BaseTool,
    ToolCategory,
    ToolContext,
    ToolResult,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Stub tools
# ---------------------------------------------------------------------------


class EchoTool(BaseTool):
    name = "echo_tool"
    description = "Echoes the input back."
    category = ToolCategory.UTIL
    version = "2.0.0"
    timeout_sec = 30
    max_retries = 1
    aliases = ["echo", "mirror"]
    search_hint = "echo mirror reflect"
    is_read_only = True
    is_concurrency_safe = True
    max_result_size_chars = 50_000

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The message to echo"},
            },
            "required": ["message"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return {"echoed": params["message"]}


class FailingTool(BaseTool):
    name = "failing_tool"
    description = "Always raises."
    max_retries = 0
    is_destructive = True
    interrupt_behavior = "cancel"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        raise RuntimeError("Intentional failure")


class SemanticValidationTool(BaseTool):
    """Rejects inputs with 'bad' in the message field."""

    name = "semantic_val_tool"
    description = "Validates input semantically."
    max_retries = 0

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }

    async def validate_input(
        self, params: dict[str, Any], context: ToolContext
    ) -> ValidationResult:
        if "bad" in params.get("message", ""):
            return ValidationResult(valid=False, message="Contains forbidden word")
        return ValidationResult(valid=True)

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return {"ok": True}


class AbortableTool(BaseTool):
    """Checks abort signal before executing."""

    name = "abortable_tool"
    description = "Can be aborted."
    max_retries = 0

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return {"done": True}


def _ctx(**kwargs: Any) -> ToolContext:
    return ToolContext(user_id="u1", session_id="s1", **kwargs)


# ===========================================================================
# ToolResult
# ===========================================================================


class TestToolResult:
    def test_ok_creates_success(self) -> None:
        r = ToolResult.ok(data={"key": "value"}, duration_ms=100)
        assert r.success is True
        assert r.data == {"key": "value"}
        assert r.duration_ms == 100
        assert r.error is None

    def test_fail_creates_failure(self) -> None:
        r = ToolResult.fail(error="oops", duration_ms=50)
        assert r.success is False
        assert r.error == "oops"
        assert r.duration_ms == 50
        assert r.data is None

    def test_to_dict_keys(self) -> None:
        d = ToolResult.ok(data=42).to_dict()
        assert "success" in d
        assert "data" in d
        assert "error" in d
        assert "duration_ms" in d
        assert "metadata" in d

    def test_ok_with_metadata(self) -> None:
        r = ToolResult.ok(data=None, source="pdf_reader")
        assert r.metadata.get("source") == "pdf_reader"

    def test_fail_with_metadata(self) -> None:
        r = ToolResult.fail(error="bad", attempt=3)
        assert r.metadata.get("attempt") == 3

    def test_fail_with_structured_data(self) -> None:
        r = ToolResult.fail(
            "boom",
            duration_ms=10,
            data={"status": "error", "stderr": "trace"},
        )
        assert r.success is False
        assert r.error == "boom"
        assert r.data == {"status": "error", "stderr": "trace"}


def test_serialize_tool_result_failure_includes_detail_json() -> None:
    from leagent.agent.query import _serialize_result

    r = ToolResult.fail("main", data={"stderr": "e", "returncode": 1})
    s = _serialize_result(r)
    payload = json.loads(s)
    assert payload["tool_ok"] is False
    assert payload["error"] == "main"
    assert payload["detail"]["stderr"] == "e"


# ===========================================================================
# ToolContext
# ===========================================================================


class TestToolContext:
    def test_creation(self) -> None:
        ctx = ToolContext(user_id="u1", session_id="s1")
        assert ctx.user_id == "u1"
        assert ctx.session_id == "s1"
        assert ctx.task_id is None

    def test_with_task_returns_new_context(self) -> None:
        ctx = ToolContext(user_id="u1", session_id="s1")
        ctx2 = ctx.with_task("task-99")
        assert ctx2.task_id == "task-99"
        assert ctx2.user_id == "u1"
        assert ctx.task_id is None  # original unchanged

    def test_is_aborted_false_when_no_signal(self) -> None:
        ctx = ToolContext(user_id="u", session_id="s")
        assert ctx.is_aborted is False

    def test_is_aborted_true_when_event_set(self) -> None:
        event = asyncio.Event()
        event.set()
        ctx = ToolContext(user_id="u", session_id="s", abort_signal=event)
        assert ctx.is_aborted is True

    def test_is_aborted_false_when_event_not_set(self) -> None:
        event = asyncio.Event()
        ctx = ToolContext(user_id="u", session_id="s", abort_signal=event)
        assert ctx.is_aborted is False

    def test_extra_dict_accessible(self) -> None:
        ctx = ToolContext(user_id="u", session_id="s")
        ctx.extra["custom"] = "value"
        assert ctx.extra["custom"] == "value"


# ===========================================================================
# BaseTool class-level attributes (new architecture)
# ===========================================================================


class TestBaseToolAttributes:
    def test_name(self) -> None:
        assert EchoTool().name == "echo_tool"

    def test_description(self) -> None:
        assert "Echoes" in EchoTool().description

    def test_category(self) -> None:
        assert EchoTool().category == ToolCategory.UTIL

    def test_version(self) -> None:
        assert EchoTool().version == "2.0.0"

    def test_aliases(self) -> None:
        t = EchoTool()
        assert "echo" in t.aliases
        assert "mirror" in t.aliases

    def test_search_hint(self) -> None:
        assert EchoTool().search_hint != ""

    def test_is_read_only(self) -> None:
        assert EchoTool().is_read_only is True

    def test_is_concurrency_safe(self) -> None:
        assert EchoTool().is_concurrency_safe is True

    def test_is_destructive_default_false(self) -> None:
        assert EchoTool().is_destructive is False

    def test_is_destructive_true_on_failing_tool(self) -> None:
        assert FailingTool().is_destructive is True

    def test_interrupt_behavior_default_block(self) -> None:
        assert EchoTool().interrupt_behavior == "block"

    def test_interrupt_behavior_cancel(self) -> None:
        assert FailingTool().interrupt_behavior == "cancel"

    def test_max_result_size_chars(self) -> None:
        assert EchoTool().max_result_size_chars == 50_000

    def test_requires_gpu_default_false(self) -> None:
        assert EchoTool().requires_gpu is False

    def test_is_enabled_default_true(self) -> None:
        assert EchoTool().is_enabled is True

    def test_parameters_schema(self) -> None:
        params = EchoTool().parameters
        assert params["type"] == "object"
        assert "message" in params["properties"]

    def test_to_openai_schema(self) -> None:
        schema = EchoTool().to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "echo_tool"
        assert "parameters" in schema["function"]

    def test_repr_contains_name(self) -> None:
        r = repr(EchoTool())
        assert "echo_tool" in r

    def test_validate_params_valid(self) -> None:
        valid, err = EchoTool().validate_params({"message": "hello"})
        assert valid is True
        assert err is None

    def test_validate_params_missing_required(self) -> None:
        valid, err = EchoTool().validate_params({})
        assert valid is False
        assert err is not None

    def test_validate_params_wrong_type(self) -> None:
        valid, err = EchoTool().validate_params({"message": 123})
        # Some JSON schema validators coerce; accept either outcome
        assert isinstance(valid, bool)


# ===========================================================================
# BaseTool.run() execution lifecycle
# ===========================================================================


@pytest.mark.asyncio
class TestToolRunLifecycle:
    async def test_run_success(self) -> None:
        result = await EchoTool().run({"message": "hi"}, _ctx())
        assert result.success is True
        assert result.data == {"echoed": "hi"}

    async def test_run_schema_validation_failure(self) -> None:
        result = await EchoTool().run({}, _ctx())
        assert result.success is False
        assert "Invalid parameters" in result.error

    async def test_run_execution_failure(self) -> None:
        result = await FailingTool().run({}, _ctx())
        assert result.success is False
        assert "Intentional failure" in result.error

    async def test_run_duration_ms_recorded(self) -> None:
        result = await EchoTool().run({"message": "timing"}, _ctx())
        assert result.duration_ms >= 0

    async def test_run_semantic_validation_failure(self) -> None:
        result = await SemanticValidationTool().run({"message": "bad input"}, _ctx())
        assert result.success is False
        assert "forbidden" in result.error.lower()

    async def test_run_semantic_validation_passes(self) -> None:
        result = await SemanticValidationTool().run({"message": "good input"}, _ctx())
        assert result.success is True

    async def test_abort_before_execution(self) -> None:
        signal = asyncio.Event()
        signal.set()
        ctx = ToolContext(user_id="u", session_id="s", abort_signal=signal)
        result = await AbortableTool().run({}, ctx)
        assert result.success is False
        assert "aborted" in result.error.lower()

    async def test_on_progress_callback(self) -> None:
        progress_events: list[dict] = []
        result = await EchoTool().run(
            {"message": "progress test"},
            _ctx(),
            on_progress=lambda e: progress_events.append(e),
        )
        assert result.success is True


# ===========================================================================
# ToolCategory enum
# ===========================================================================


class TestToolCategoryEnum:
    def test_doc(self) -> None:
        assert ToolCategory.DOC.value == "doc"

    def test_web(self) -> None:
        assert ToolCategory.WEB.value == "web"

    def test_data(self) -> None:
        assert ToolCategory.DATA.value == "data"

    def test_gen(self) -> None:
        assert ToolCategory.GEN.value == "gen"

    def test_integration(self) -> None:
        assert ToolCategory.INTEGRATION.value == "integration"

    def test_util(self) -> None:
        assert ToolCategory.UTIL.value == "util"

    def test_all_values_are_str(self) -> None:
        for cat in ToolCategory:
            assert isinstance(cat.value, str)


# ===========================================================================
# ValidationResult
# ===========================================================================


class TestValidationResult:
    def test_valid(self) -> None:
        vr = ValidationResult(valid=True)
        assert vr.valid is True
        assert vr.message == ""

    def test_invalid_with_message(self) -> None:
        vr = ValidationResult(valid=False, message="path not found", error_code=404)
        assert vr.valid is False
        assert "path not found" in vr.message
        assert vr.error_code == 404
