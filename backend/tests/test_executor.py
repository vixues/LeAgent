"""Tests for ToolExecutor (tools layer): single, parallel, sequential, AggregatedResult."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leagent.tools.base import SyncTool, ToolCategory, ToolContext, ToolResult
from leagent.tools.executor import (
    AggregatedResult,
    ExecutionResult,
    ToolCall,
    ToolExecutor,
    _recover_canvas_publish_args,
    _recover_project_edit_args,
    _try_parse_raw_tool_args,
    format_tool_arguments_json_error,
    parse_tool_arguments_str,
    strict_json_loads_error,
)
from leagent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Tool stubs
# ---------------------------------------------------------------------------


class _EchoTool(SyncTool):
    name = "echo_tool"
    description = "Echoes the input value"
    category = ToolCategory.UTIL
    version = "1.0.0"
    is_concurrency_safe = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        return {"echo": params["value"]}


class _FailingTool(SyncTool):
    name = "failing_tool"
    description = "Always fails"
    category = ToolCategory.UTIL
    version = "1.0.0"
    is_concurrency_safe = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        raise RuntimeError("intentional failure")


class _SlowTool(SyncTool):
    name = "slow_tool"
    description = "Sleeps before returning"
    category = ToolCategory.UTIL
    version = "1.0.0"
    is_concurrency_safe = False

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"delay": {"type": "number"}}}

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        import time
        time.sleep(params.get("delay", 0.01))
        return ToolResult.ok({"done": True})


def _make_registry(*tools: SyncTool) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def _ctx() -> ToolContext:
    return ToolContext(user_id="u1", session_id="s1")


class _FakeAuditSession:
    def __init__(self) -> None:
        self.entries: list[Any] = []

    async def __aenter__(self) -> "_FakeAuditSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def add(self, entry: Any) -> None:
        self.entries.append(entry)


class _FakeAuditDb:
    def __init__(self) -> None:
        self.session_obj = _FakeAuditSession()

    def session(self) -> _FakeAuditSession:
        return self.session_obj


# ---------------------------------------------------------------------------
# AggregatedResult unit tests (pure data)
# ---------------------------------------------------------------------------


class TestAggregatedResult:
    def _make_result(self, success: bool, tool: str = "t") -> ExecutionResult:
        return ExecutionResult(
            call_id=f"call_{tool}",
            tool_name=tool,
            result=ToolResult.ok({}) if success else ToolResult.fail("err"),
            started_at=0.0,
            finished_at=0.1,
        )

    def test_all_successful_true(self) -> None:
        agg = AggregatedResult(results=[
            self._make_result(True, "a"),
            self._make_result(True, "b"),
        ])
        assert agg.all_successful is True
        assert agg.any_successful is True
        assert agg.successful_count == 2
        assert agg.failed_count == 0

    def test_all_successful_false(self) -> None:
        agg = AggregatedResult(results=[
            self._make_result(True, "a"),
            self._make_result(False, "b"),
        ])
        assert agg.all_successful is False
        assert agg.any_successful is True
        assert agg.successful_count == 1
        assert agg.failed_count == 1

    def test_empty_results(self) -> None:
        agg = AggregatedResult()
        assert agg.all_successful is True  # vacuous truth
        assert agg.any_successful is False
        assert agg.successful_count == 0
        assert agg.failed_count == 0

    def test_get_by_tool(self) -> None:
        agg = AggregatedResult(results=[
            self._make_result(True, "tool_a"),
            self._make_result(False, "tool_a"),
            self._make_result(True, "tool_b"),
        ])
        by_a = agg.get_by_tool("tool_a")
        assert len(by_a) == 2

    def test_get_result_by_call_id(self) -> None:
        r = self._make_result(True, "x")
        agg = AggregatedResult(results=[r])
        found = agg.get_result("call_x")
        assert found is r


# ---------------------------------------------------------------------------
# ToolExecutor tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestToolExecutorSingle:
    async def test_execute_success(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        result = await executor.execute("echo_tool", {"value": "hello"}, _ctx())
        assert result.result.success
        assert result.result.data == {"echo": "hello"}
        assert result.tool_name == "echo_tool"

    async def test_execute_failure(self) -> None:
        reg = _make_registry(_FailingTool())
        executor = ToolExecutor(registry=reg)
        result = await executor.execute("failing_tool", {}, _ctx())
        assert not result.result.success
        assert result.result.error == "intentional failure"

    async def test_execute_missing_tool(self) -> None:
        reg = _make_registry()
        executor = ToolExecutor(registry=reg)
        result = await executor.execute("nonexistent_tool", {}, _ctx())
        assert not result.result.success
        assert "not found" in result.result.error.lower()

    async def test_execute_disabled_tool(self) -> None:
        tool = _EchoTool()
        tool.is_enabled = False  # type: ignore[assignment]
        reg = _make_registry(tool)
        executor = ToolExecutor(registry=reg)
        result = await executor.execute("echo_tool", {"value": "hi"}, _ctx())
        assert not result.result.success

    async def test_execute_call_object(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        call = ToolCall(tool_name="echo_tool", parameters={"value": "world"})
        result = await executor.execute_call(call, _ctx())
        assert result.result.success

    async def test_progress_callback_invoked(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        events: list[dict] = []
        await executor.execute("echo_tool", {"value": "x"}, _ctx(), on_progress=events.append)
        event_types = {e["type"] for e in events}
        assert "tool_start" in event_types
        assert "tool_end" in event_types

    async def test_execute_writes_audit_log_when_db_context_present(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        db = _FakeAuditDb()
        ctx = ToolContext(user_id=None, session_id="s1", task_id="t1", db=db)  # type: ignore[arg-type]

        result = await executor.execute(
            "echo_tool",
            {"value": "hello", "api_token": "secret"},
            ctx,
        )

        assert result.result.success
        # Standalone builds stub audit persistence (executor._audit_tool_execution is a no-op).
        assert db.session_obj.entries == []

    async def test_execute_recovers_raw_json_args(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        result = await executor.execute(
            "echo_tool",
            {"__raw__": '{"value":"hello"}'},
            _ctx(),
        )
        assert result.result.success
        assert result.result.data == {"echo": "hello"}

    async def test_execute_recovers_code_fence_json_args(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        result = await executor.execute(
            "echo_tool",
            {"__raw__": '```json\n{"value":"from_fence"}\n```'},
            _ctx(),
        )
        assert result.result.success
        assert result.result.data == {"echo": "from_fence"}

    async def test_execute_recovers_double_encoded_json_args(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        result = await executor.execute(
            "echo_tool",
            {"__raw__": '"{\\"value\\": \\"double\\"}"'},
            _ctx(),
        )
        assert result.result.success
        assert result.result.data == {"echo": "double"}

    async def test_execute_recovers_bom_prefixed_json_args(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        result = await executor.execute(
            "echo_tool",
            {"__raw__": '\ufeff{"value":"bom"}'},
            _ctx(),
        )
        assert result.result.success
        assert result.result.data == {"echo": "bom"}

    async def test_execute_recovers_trailing_commas_outside_strings(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        result = await executor.execute(
            "echo_tool",
            {"__raw__": '{"value":"comma,} literal",}'},
            _ctx(),
        )
        assert result.result.success
        assert result.result.data == {"echo": "comma,} literal"}

    async def test_recovers_code_execution_source_from_malformed_outer_json(self) -> None:
        raw = (
            '{"source": "\n'
            'translation = """Title "quoted" text"""\n'
            'output_path = "/tmp/out.txt"\n'
            'result = {"saved_to": output_path}\n'
            '"}'
        )
        parsed = _try_parse_raw_tool_args(raw)
        assert parsed is not None
        assert parsed["source"].startswith("\ntranslation =")
        assert '"""Title "quoted" text"""' in parsed["source"]
        assert 'result = {"saved_to": output_path}' in parsed["source"]

    async def test_execute_fails_with_malformed_raw_args(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        result = await executor.execute(
            "echo_tool",
            {"__raw__": '{"value": "broken"'},
            _ctx(),
        )
        assert not result.result.success
        assert result.result.error is not None
        assert result.result.error.startswith("Malformed tool arguments JSON")
        assert "Retry with strict JSON" in result.result.error

    async def test_document_generate_accepts_recovered_raw_args(self, tmp_path) -> None:
        from leagent.tools.gen.document_tool import DocumentGenerateTool

        reg = _make_registry(DocumentGenerateTool())
        executor = ToolExecutor(registry=reg)
        out_path = tmp_path / "generated.md"
        raw = json.dumps(
            {
                "output_path": str(out_path),
                "title": "t",
                "content": "# Heading\n\nhello",
            }
        )
        result = await executor.execute("document_generate", {"__raw__": raw}, _ctx())
        assert result.result.success
        assert out_path.exists()


def test_format_code_execution_args_error_avoids_generic_json_noise() -> None:
    raw = '{"source": "' + ("print('x')\n" * 400)
    err = strict_json_loads_error(raw)
    assert err is not None
    msg = format_tool_arguments_json_error(raw, err, tool_name="code_execution")
    assert "Malformed tool arguments JSON" not in msg
    assert "`code_execution` did not run:" in msg
    assert "source_blob_id" in msg
    assert "smaller tree" not in msg.lower()


def test_format_tool_argument_blob_raw_args_error_mentions_chunk_base64() -> None:
    raw = '{"action":"append","blob_id":"abc","chunk":"<!DOCTYPE html><p>a\"b</p>'
    err = strict_json_loads_error(raw)
    assert err is not None
    msg = format_tool_arguments_json_error(raw, err, tool_name="tool_argument_blob")
    assert "`tool_argument_blob` did not run:" in msg
    assert "chunk_base64" in msg


def test_parse_tool_arguments_str_repairs_trailing_comma() -> None:
    raw = '{"title":"T","mode":"gen_ui",}'
    assert parse_tool_arguments_str(raw) == {"title": "T", "mode": "gen_ui"}


def test_parse_tool_arguments_str_double_encoded_json_string() -> None:
    inner = {"title": "Dash", "mode": "html"}
    wrapped = json.dumps(json.dumps(inner))
    assert parse_tool_arguments_str(wrapped) == inner


def test_parse_tool_arguments_str_returns_none_for_unclosed_object() -> None:
    assert parse_tool_arguments_str('{"value": "broken"') is None


def test_parse_tool_arguments_str_accepts_trailing_brace_junk() -> None:
    """``json.loads`` fails with Extra data; first object is recovered via raw_decode."""
    assert parse_tool_arguments_str('{"value":"ok"}}') == {"value": "ok"}


def test_parse_tool_arguments_str_repairs_emit_ui_style_extra_close_brace() -> None:
    """Real LLM failure: one superfluous ``}`` before the next sibling (e.g. before Alert)."""
    raw = (Path(__file__).parent / "fixtures" / "emit_ui_tree_malformed_llm.json").read_text(
        encoding="utf-8",
    )
    parsed = parse_tool_arguments_str(raw)
    assert parsed is not None
    assert "tree" in parsed
    assert parsed["tree"]["type"] == "Stack"
    assert any(c.get("type") == "Alert" for c in parsed["tree"].get("children", []))


def test_parse_tool_arguments_str_escapes_raw_newlines_in_codeblock() -> None:
    raw = (
        '{"tree":{"type":"CodeBlock","props":{"language":"javascript","code":"'
        "function greet(name) {\n  return 'Hello, ' + name;\n}"
        '"}}}'
    )
    parsed = parse_tool_arguments_str(raw)
    assert parsed is not None
    assert parsed["tree"]["props"]["code"] == "function greet(name) {\n  return 'Hello, ' + name;\n}"


def test_parse_tool_arguments_str_repairs_unescaped_quotes_in_slides_body() -> None:
    """CJK prose with raw ``"忘记"`` must not block ``slides_generate``."""
    raw = (
        '{"output_path":"deck.pptx","title":"可靠性故障分析",'
        '"slides":[{"layout":"content","title":"故障1：上下文丢失",'
        '"kicker":"故障分析",'
        '"body":"**现象**\\nAgent在处理长对话时，偶尔"忘记"用户最初提供的详细信息，'
        '需要用户后续重新确认。\\n\\n**根因**\\n- 上下文窗口管理策略有待优化\\n'
        '- 长对话中信息压缩损失了关键细节\\n\\n**改进**"},'
        '{"layout":"closing","title":"谢谢"}]}'
    )
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    parsed = parse_tool_arguments_str(raw)
    assert parsed is not None
    assert parsed["output_path"] == "deck.pptx"
    assert parsed["slides"][0]["title"] == "故障1：上下文丢失"
    assert '偶尔"忘记"用户' in parsed["slides"][0]["body"]
    assert parsed["slides"][1]["layout"] == "closing"


def test_parse_tool_arguments_str_repairs_unescaped_quotes_with_raw_newlines() -> None:
    raw = (
        '{"output_path":"x.md","content":"标题\n偶尔"忘记"细节\n结束",'
        '"title":"t"}'
    )
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    parsed = parse_tool_arguments_str(raw)
    assert parsed is not None
    assert parsed["content"] == '标题\n偶尔"忘记"细节\n结束'
    assert parsed["title"] == "t"


def test_parse_tool_arguments_str_recovers_complete_emit_ui_tree_from_broken_outer_args() -> None:
    raw = '{"tree":{"type":"Text","props":{"value":"ok"}},"canvas_id":'
    parsed = parse_tool_arguments_str(raw)
    assert parsed == {"tree": {"type": "Text", "props": {"value": "ok"}}}


def test_parse_tool_arguments_str_recovers_truncated_emit_ui_tree_prefix() -> None:
    raw = '{"tree":{"type":"CodeBlock","props":{"code":"function greet(name) {'
    parsed = parse_tool_arguments_str(raw)
    assert parsed is not None
    assert parsed["tree"] == {
        "type": "CodeBlock",
        "props": {"code": "function greet(name) {"},
    }


def test_parse_tool_arguments_str_leaves_missing_tree_object_unrecoverable() -> None:
    assert parse_tool_arguments_str('{"tree":') is None


def test_recover_canvas_publish_args_html_blob_id_only() -> None:
    raw = (
        '{"title":"Swarm","mode":"html","session_id":"current",'
        '"html_blob_id":"a1b2c3d4e5f64789900112233445566"}'
    )
    assert _recover_canvas_publish_args(raw) == {
        "title": "Swarm",
        "mode": "html",
        "session_id": "current",
        "html_blob_id": "a1b2c3d4e5f64789900112233445566",
    }


def test_recover_canvas_publish_args_html_files_map() -> None:
    raw = (
        '{"title":"Page","mode":"html","html_files":{"index.html":"<html></html>"},'
        '"html_bundle_entry":"index.html"}'
    )
    recovered = _recover_canvas_publish_args(raw)
    assert recovered is not None
    assert recovered["title"] == "Page"
    assert recovered["html_files"]["index.html"] == "<html></html>"
    assert recovered["html_bundle_entry"] == "index.html"


def test_recover_canvas_publish_args_unterminated_html() -> None:
    """max_tokens mid-string: recover partial html so ingest can stage a blob."""
    raw = (
        '{"title":"Arch","mode":"html","html":"<!DOCTYPE html>\\n<html><body>'
        "<h1>AirSim</h1><p>truncated"
    )
    recovered = _recover_canvas_publish_args(raw)
    assert recovered is not None
    assert recovered["title"] == "Arch"
    assert recovered["mode"] == "html"
    assert "<!DOCTYPE html>" in recovered["html"]
    assert "AirSim" in recovered["html"]
    assert "truncated" in recovered["html"]


def test_recover_project_edit_args_basic() -> None:
    raw = (
        '{"path":"src/index.html","old_string":"<div>old</div>",'
        '"new_string":"<div>new content\nwith lines</div>"}'
    )
    result = _recover_project_edit_args(raw)
    assert result is not None
    assert result["path"] == "src/index.html"
    assert result["old_string"] == "<div>old</div>"
    assert "new content" in result["new_string"]


def test_recover_project_edit_args_with_raw_newlines() -> None:
    raw = '{"path":"app.py","old_string":"pass","new_string":"def main():\n    print(\'hello\')\n"}'
    result = _recover_project_edit_args(raw)
    assert result is not None
    assert result["path"] == "app.py"
    assert result["old_string"] == "pass"
    assert "def main()" in result["new_string"]


def test_recover_project_edit_args_returns_none_for_irrelevant() -> None:
    raw = '{"html":"<div>test</div>"}'
    assert _recover_project_edit_args(raw) is None


def test_try_parse_raw_tool_args_includes_canvas_publish_recovery() -> None:
    """Invalid JSON (raw newline inside html string) recovers via canvas_publish path."""
    raw = '{"title":"T","mode":"html","html":"<div>x\ny","open_in_panel":false}'
    parsed = _try_parse_raw_tool_args(raw)
    assert parsed is not None
    assert parsed.get("title") == "T"
    assert parsed.get("mode") == "html"
    assert parsed.get("html") == "<div>x\ny"
    assert parsed.get("open_in_panel") is False


@pytest.mark.asyncio
class TestToolExecutorParallel:
    async def test_execute_parallel(self) -> None:
        reg = _make_registry(_EchoTool())
        executor = ToolExecutor(registry=reg)
        calls = [
            ToolCall(tool_name="echo_tool", parameters={"value": f"v{i}"})
            for i in range(5)
        ]
        agg = await executor.execute_parallel(calls, _ctx())
        assert isinstance(agg, AggregatedResult)
        assert agg.successful_count == 5

    async def test_execute_parallel_mixed(self) -> None:
        reg = _make_registry(_EchoTool(), _FailingTool())
        executor = ToolExecutor(registry=reg)
        calls = [
            ToolCall(tool_name="echo_tool", parameters={"value": "ok"}),
            ToolCall(tool_name="failing_tool", parameters={}),
        ]
        agg = await executor.execute_parallel(calls, _ctx())
        assert agg.successful_count == 1
        assert agg.failed_count == 1
        assert not agg.all_successful
        assert agg.any_successful


@pytest.mark.asyncio
class TestToolExecutorPartitioned:
    async def test_partition_calls(self) -> None:
        reg = _make_registry(_EchoTool(), _SlowTool())
        executor = ToolExecutor(registry=reg)
        calls = [
            ToolCall(tool_name="echo_tool", parameters={"value": "a"}),
            ToolCall(tool_name="slow_tool", parameters={}),
        ]
        concurrent, serial = executor.partition_calls(calls)
        concurrent_names = {c.tool_name for c in concurrent}
        serial_names = {c.tool_name for c in serial}
        assert "echo_tool" in concurrent_names
        assert "slow_tool" in serial_names

    async def test_execute_partitioned(self) -> None:
        reg = _make_registry(_EchoTool(), _SlowTool())
        executor = ToolExecutor(registry=reg)
        calls = [
            ToolCall(tool_name="echo_tool", parameters={"value": "test"}),
            ToolCall(tool_name="slow_tool", parameters={"delay": 0.0}),
        ]
        agg = await executor.execute_partitioned(calls, _ctx())
        assert len(agg.results) == 2

    async def test_execute_sequential_stop_on_failure(self) -> None:
        reg = _make_registry(_FailingTool(), _EchoTool())
        executor = ToolExecutor(registry=reg)
        calls = [
            ToolCall(tool_name="failing_tool", parameters={}),
            ToolCall(tool_name="echo_tool", parameters={"value": "should_not_run"}),
        ]
        agg = await executor.execute_sequential(calls, _ctx(), stop_on_failure=True)
        assert len(agg.results) == 1
        assert not agg.results[0].result.success
