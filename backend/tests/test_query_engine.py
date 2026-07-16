"""Offline tests for the new QueryEngine / query-loop stack.

These tests never hit a real LLM: they inject a fake ``call_model`` via
``QueryDeps`` that emits a canned sequence of ``ModelStreamEvent`` items
(content deltas + tool calls + a final ``message_stop``). That's enough
to exercise the real tool dispatch, SDK message mapping, recovery
transitions, and abort handling.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import UUID, uuid4

import pytest

from leagent.agent.base import AgentResponse
from leagent.agent.deps import ModelStreamEvent, QueryDeps
from leagent.agent.query import (
    ASK_USER_PENDING_TOOL_JSON,
    AssistantMessage,
    QueryParams,
    ToolResultMessage,
    _build_length_recovery_state,
    _dispatch_tools,
    _inject_pending_ask_user_tool_stubs,
    _normalize_ask_user_questions,
    _prepare_canvas_length_salvage,
    drop_orphan_tool_messages,
    inject_missing_tool_result_stubs,
    query,
)
from leagent.agent.query_engine import QueryEngine, QueryEngineConfig, SDKMessage
from leagent.agent.state import QueryState, AutoCompactTrackingState
from leagent.agent.tool_use_context import ToolUseContext
from leagent.agent.transitions import Continue, ContinueReason, Terminal, TerminalReason
from leagent.context import FileState
from leagent.context.sources.gated_policy import (
    CANVAS_INTENT_MAX_OUTPUT_TOKENS,
    resolve_canvas_intent_max_output_tokens,
)
from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ToolPermissionContext
from leagent.tools.executor import ToolExecutor
from leagent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Lightweight test doubles
# ---------------------------------------------------------------------------


class _EchoTool(BaseTool):
    """Minimal echo tool: returns ``{"echoed": params["text"]}``."""

    name = "echo"
    description = "Echo back the provided text."
    category = ToolCategory.UTIL
    is_concurrency_safe = True
    is_read_only = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        return {"echoed": params.get("text", "")}


class _SleepTool(BaseTool):
    """Awaits ``delay`` seconds then returns. Non-concurrency-safe by default."""

    name = "sleep"
    description = "Sleep for ``delay`` seconds."
    category = ToolCategory.UTIL
    is_concurrency_safe = False
    is_read_only = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"delay": {"type": "number"}},
            "required": ["delay"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, str]:
        await asyncio.sleep(float(params.get("delay", 0)))
        return {"slept": str(params.get("delay", 0))}


class _CanvasPublishStub(BaseTool):
    """Records canvas_publish calls; optionally enforces force_sharded_html."""

    name = "canvas_publish"
    description = "Stub canvas publish."
    category = ToolCategory.CANVAS
    is_concurrency_safe = True
    is_read_only = False

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "mode": {"type": "string"},
                "html": {"type": "string"},
                "html_files": {"type": "object"},
                "html_blob_id": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["title", "mode"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        has_inline = bool((params.get("html") or "").strip())
        has_files = bool(params.get("html_files"))
        has_blob = bool(params.get("html_blob_id"))
        if (
            has_inline
            and not has_files
            and not has_blob
            and bool((context.extra or {}).get("force_sharded_html"))
        ):
            raise ValueError(
                "Inline `html` is blocked after repeated output-length truncation."
            )
        self.calls.append(dict(params))
        return {"published": True, "title": params.get("title")}


def _make_registry(*extra_tools: BaseTool) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(_EchoTool())
    reg.register(_SleepTool())
    for tool in extra_tools:
        reg.register(tool)
    return reg


def _scripted_call_model(script: list[list[ModelStreamEvent]]):
    """Return a ``call_model`` that replays one batch per turn.

    ``script[i]`` is the list of events emitted during turn ``i``. If
    the loop asks for more turns than the script provides, the final
    batch is reused (terminating via ``finish_reason='stop'``).
    """
    turn = {"n": 0}

    async def call_model(
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
        tool_use_context: ToolUseContext,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[ModelStreamEvent]:
        idx = min(turn["n"], len(script) - 1)
        turn["n"] += 1
        for ev in script[idx]:
            yield ev

    return call_model


async def _identity_compact(messages, tool_use_context, *args):  # noqa: ANN001
    return messages


def _make_deps(script: list[list[ModelStreamEvent]]) -> QueryDeps:
    async def _micro(messages, tool_use_context):  # noqa: ANN001
        return messages

    async def _auto(messages, tool_use_context, system_prompt):  # noqa: ANN001
        return messages

    return QueryDeps(
        call_model=_scripted_call_model(script),
        microcompact=_micro,
        autocompact=_auto,
    )


def _make_ctx(
    registry: ToolRegistry,
    *,
    permission_context: ToolPermissionContext | None = None,
) -> ToolUseContext:
    """Build tool context. Uses empty :class:`ToolPermissionContext` by default so
    permission checks match production chat wiring (see ``chat_deps.build_agent_controller``).
    """
    perm = (
        permission_context
        if permission_context is not None
        else ToolPermissionContext()
    )
    return ToolUseContext(
        abort_event=asyncio.Event(),
        tools=registry,
        executor=ToolExecutor(
            registry=registry,
            service_manager=None,
            permission_context=perm,
        ),
        file_state_cache=FileState(),
    )


# ---------------------------------------------------------------------------
# Transition enum sanity
# ---------------------------------------------------------------------------


class TestTransitions:
    def test_terminal_reason_values(self) -> None:
        assert TerminalReason.COMPLETED.value == "completed"
        assert TerminalReason.MAX_TURNS.value == "max_turns"
        assert TerminalReason.ABORTED_STREAMING.value == "aborted_streaming"
        assert TerminalReason.AWAITING_USER_INPUT.value == "awaiting_user_input"

    def test_continue_wraps_meta(self) -> None:
        c = Continue(reason=ContinueReason.NEXT_TURN, meta={"k": 1})
        assert c.reason == ContinueReason.NEXT_TURN
        assert c.meta == {"k": 1}


# ---------------------------------------------------------------------------
# query() loop
# ---------------------------------------------------------------------------


class TestQueryLoop:
    @pytest.mark.asyncio
    async def test_completes_without_tools(self) -> None:
        """No tool calls → assistant message → Terminal(completed)."""
        registry = _make_registry()
        ctx = _make_ctx(registry)
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(content_delta="Hello "),
                    ModelStreamEvent(content_delta="world"),
                    ModelStreamEvent(
                        message_stop={"finish_reason": "stop", "usage": {"total_tokens": 5}}
                    ),
                ]
            ]
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        assistants = [e for e in events if isinstance(e, AssistantMessage)]
        terminals = [e for e in events if isinstance(e, Terminal)]

        assert len(assistants) == 1
        assert assistants[0].content == "Hello world"
        assert assistants[0].tool_calls == []
        assert len(terminals) == 1
        assert terminals[0].reason == TerminalReason.COMPLETED

    @pytest.mark.asyncio
    async def test_accumulates_reasoning_content_on_assistant_turn(self) -> None:
        """Thinking-mode providers stream ``reasoning_content`` fragments; we merge for replay."""
        registry = _make_registry()
        ctx = _make_ctx(registry)
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(reasoning_delta="step "),
                    ModelStreamEvent(reasoning_delta="A"),
                    ModelStreamEvent(content_delta="ok"),
                    ModelStreamEvent(
                        message_stop={"finish_reason": "stop", "usage": {"total_tokens": 3}}
                    ),
                ]
            ]
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
        )
        assistants: list[AssistantMessage] = []
        async for item in query(params):
            if isinstance(item, AssistantMessage):
                assistants.append(item)
        assert len(assistants) == 1
        assert assistants[0].reasoning_content == "step A"
        assert assistants[0].to_openai()["reasoning_content"] == "step A"
        assert assistants[0].to_openai()["content"] == "ok"

    @pytest.mark.asyncio
    async def test_ask_user_yields_awaiting_user_input_without_tool_results(self) -> None:
        """ask_user short-circuits: no ToolResultMessage, Terminal awaits user."""
        registry = _make_registry()
        ctx = _make_ctx(registry)
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(
                        tool_call={
                            "id": "call-ask",
                            "name": "ask_user",
                            "arguments": {
                                "questions": [{"id": "q1", "prompt": "A or B?"}],
                            },
                        },
                    ),
                    ModelStreamEvent(
                        message_stop={
                            "finish_reason": "tool_calls",
                            "usage": {"total_tokens": 1},
                        },
                    ),
                ],
            ],
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        assistants = [e for e in events if isinstance(e, AssistantMessage)]
        tool_results = [e for e in events if isinstance(e, ToolResultMessage)]
        terminals = [e for e in events if isinstance(e, Terminal)]

        assert len(assistants) == 1
        assert len(assistants[0].tool_calls) == 1
        assert assistants[0].tool_calls[0]["name"] == "ask_user"
        assert tool_results == []
        assert terminals[-1].reason == TerminalReason.AWAITING_USER_INPUT
        meta = terminals[-1].meta
        assert meta.get("tool_call", {}).get("id") == "call-ask"
        assert len(meta.get("questions", [])) == 1
        assert meta["questions"][0]["id"] == "q1"

    @pytest.mark.asyncio
    async def test_ask_user_permission_metadata_in_terminal_meta(self) -> None:
        registry = _make_registry()
        ctx = _make_ctx(registry)
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(
                        tool_call={
                            "id": "call-perm",
                            "name": "ask_user",
                            "arguments": {
                                "questions": [
                                    {
                                        "id": "gate1",
                                        "prompt": "Read this path?",
                                        "ui_variant": "permission",
                                        "permission_kind": "file_access",
                                        "detail": "/home/proj/secret.txt",
                                        "primary_choice": "Allow",
                                        "secondary_choice": "Deny",
                                    }
                                ],
                            },
                        },
                    ),
                    ModelStreamEvent(
                        message_stop={
                            "finish_reason": "tool_calls",
                            "usage": {"total_tokens": 1},
                        },
                    ),
                ],
            ],
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
        )

        terminals = [e async for e in query(params) if isinstance(e, Terminal)]
        assert terminals[-1].reason == TerminalReason.AWAITING_USER_INPUT
        q0 = terminals[-1].meta["questions"][0]
        assert q0["ui_variant"] == "permission"
        assert q0["permission_kind"] == "file_access"
        assert q0["detail"] == "/home/proj/secret.txt"
        assert q0["primary_choice"] == "Allow"
        assert q0["secondary_choice"] == "Deny"

    @pytest.mark.asyncio
    async def test_runs_tool_then_completes(self) -> None:
        """Turn 1 emits a tool call; turn 2 produces final text."""
        registry = _make_registry()
        ctx = _make_ctx(registry)
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(
                        tool_call={
                            "id": "call_1",
                            "name": "echo",
                            "arguments": {"text": "hi"},
                        },
                    ),
                    ModelStreamEvent(message_stop={"finish_reason": "tool_calls", "usage": {}}),
                ],
                [
                    ModelStreamEvent(content_delta="done"),
                    ModelStreamEvent(message_stop={"finish_reason": "stop", "usage": {}}),
                ],
            ]
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "echo hi"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_turns=5,
        )

        tool_results: list[ToolResultMessage] = []
        terminal: Terminal | None = None
        async for item in query(params):
            if isinstance(item, ToolResultMessage):
                tool_results.append(item)
            elif isinstance(item, Terminal):
                terminal = item

        assert len(tool_results) == 1
        assert tool_results[0].name == "echo"
        assert "hi" in tool_results[0].content
        assert tool_results[0].success is True
        assert terminal is not None
        assert terminal.reason == TerminalReason.COMPLETED

    @pytest.mark.asyncio
    async def test_denied_tool_returns_permission_error(self) -> None:
        """Executor deny list is enforced on the QueryEngine dispatch path."""
        registry = _make_registry()
        ctx = _make_ctx(
            registry,
            permission_context=ToolPermissionContext(always_deny_rules=["echo"]),
        )
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(
                        tool_call={
                            "id": "call_1",
                            "name": "echo",
                            "arguments": {"text": "hi"},
                        },
                    ),
                    ModelStreamEvent(message_stop={"finish_reason": "tool_calls", "usage": {}}),
                ],
                [
                    ModelStreamEvent(content_delta="done"),
                    ModelStreamEvent(message_stop={"finish_reason": "stop", "usage": {}}),
                ],
            ]
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "echo hi"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_turns=5,
        )

        tool_results: list[ToolResultMessage] = []
        async for item in query(params):
            if isinstance(item, ToolResultMessage):
                tool_results.append(item)

        assert len(tool_results) == 1
        assert tool_results[0].name == "echo"
        assert tool_results[0].success is False
        assert "Permission denied" in (tool_results[0].content or "")

    @pytest.mark.asyncio
    async def test_aborts_mid_stream(self) -> None:
        registry = _make_registry()
        ctx = _make_ctx(registry)
        # Abort before we even enter the loop.
        ctx.abort_event.set()
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(content_delta="never"),
                    ModelStreamEvent(message_stop={"finish_reason": "stop", "usage": {}}),
                ]
            ]
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "x"}],
            system_prompt="t",
            tool_use_context=ctx,
            deps=deps,
        )
        terminals = [ev async for ev in query(params) if isinstance(ev, Terminal)]
        assert len(terminals) == 1
        assert terminals[0].reason == TerminalReason.ABORTED_STREAMING

    @pytest.mark.asyncio
    async def test_max_turns_guard(self) -> None:
        """Infinite tool-calling loops are bounded by ``max_turns``."""
        registry = _make_registry()
        ctx = _make_ctx(registry)
        # Every turn emits the same tool call → loop never converges.
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(
                        tool_call={
                            "id": "c",
                            "name": "echo",
                            "arguments": {"text": "loop"},
                        },
                    ),
                    ModelStreamEvent(message_stop={"finish_reason": "tool_calls", "usage": {}}),
                ]
            ]
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "spin"}],
            system_prompt="t",
            tool_use_context=ctx,
            deps=deps,
            max_turns=3,
        )
        terminals = [ev async for ev in query(params) if isinstance(ev, Terminal)]
        assert len(terminals) == 1
        assert terminals[0].reason == TerminalReason.MAX_TURNS
        assert terminals[0].meta.get("turn_count") == 3


class TestPromptTooLong:
    @pytest.mark.asyncio
    async def test_context_overflow_yields_prompt_too_long(self) -> None:
        """A context-length error during streaming yields PROMPT_TOO_LONG."""
        registry = _make_registry()
        ctx = _make_ctx(registry)

        async def _exploding_stream(**kwargs):
            raise RuntimeError("maximum context length is 128000 tokens")
            yield  # pragma: no cover

        async def _micro(msgs, ctx):
            return msgs

        async def _auto(msgs, ctx, sp):
            return msgs

        deps = QueryDeps(
            call_model=_exploding_stream,
            microcompact=_micro,
            autocompact=_auto,
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="t",
            tool_use_context=ctx,
            deps=deps,
        )
        terminals = [ev async for ev in query(params) if isinstance(ev, Terminal)]
        assert len(terminals) == 1
        assert terminals[0].reason == TerminalReason.PROMPT_TOO_LONG


class TestTokenBudgetExceeded:
    @pytest.mark.asyncio
    async def test_budget_exceeded_yields_token_budget_exceeded(self) -> None:
        """Cumulative usage past ``max_total_tokens`` yields TOKEN_BUDGET_EXCEEDED."""
        registry = _make_registry()
        ctx = _make_ctx(registry)
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(content_delta="hi"),
                    ModelStreamEvent(
                        message_stop={
                            "finish_reason": "stop",
                            "usage": {"prompt_tokens": 500, "completion_tokens": 600, "total_tokens": 1100},
                        },
                    ),
                ]
            ]
        )
        params = QueryParams(
            messages=[{"role": "user", "content": "hi"}],
            system_prompt="t",
            tool_use_context=ctx,
            deps=deps,
            max_total_tokens=1000,
        )
        terminals = [ev async for ev in query(params) if isinstance(ev, Terminal)]
        assert len(terminals) == 1
        assert terminals[0].reason == TerminalReason.TOKEN_BUDGET_EXCEEDED
        assert terminals[0].meta["budget"] == 1000


class TestNormalizeAskUserQuestions:
    def test_permission_metadata_preserved(self) -> None:
        raw = [
            {
                "id": "p1",
                "prompt": "Proceed?",
                "ui_variant": "permission",
                "permission_kind": "tool_run",
                "detail": "web_search",
                "primary_choice": "Run",
                "secondary_choice": "Skip",
            }
        ]
        out = _normalize_ask_user_questions(raw)
        assert len(out) == 1
        assert out[0]["id"] == "p1"
        assert out[0]["ui_variant"] == "permission"
        assert out[0]["permission_kind"] == "tool_run"
        assert out[0]["detail"] == "web_search"
        assert out[0]["primary_choice"] == "Run"
        assert out[0]["secondary_choice"] == "Skip"

    def test_unknown_ui_variant_dropped(self) -> None:
        out = _normalize_ask_user_questions(
            [{"id": "a", "prompt": "x", "ui_variant": "fancy"}]
        )
        assert "ui_variant" not in out[0]

    def test_unknown_permission_kind_dropped(self) -> None:
        out = _normalize_ask_user_questions(
            [{"id": "a", "prompt": "x", "permission_kind": "nope"}]
        )
        assert "permission_kind" not in out[0]


# ---------------------------------------------------------------------------
# _dispatch_tools partitioning
# ---------------------------------------------------------------------------


class TestDispatch:
    @pytest.mark.asyncio
    async def test_preserves_order(self) -> None:
        registry = _make_registry()
        ctx = _make_ctx(registry)
        calls = [
            {"id": "a", "name": "echo", "arguments": {"text": "1"}},
            {"id": "b", "name": "sleep", "arguments": {"delay": 0}},
            {"id": "c", "name": "echo", "arguments": {"text": "2"}},
        ]
        results = await _dispatch_tools(calls, ctx)
        assert [r.tool_call_id for r in results] == ["a", "b", "c"]
        assert all(r.success for r in results)

    @pytest.mark.asyncio
    async def test_unknown_tool_is_error(self) -> None:
        registry = _make_registry()
        ctx = _make_ctx(registry)
        results = await _dispatch_tools(
            [{"id": "x", "name": "does_not_exist", "arguments": {}}],
            ctx,
        )
        assert len(results) == 1
        assert results[0].success is False
        assert "not found" in results[0].content.lower() or "error" in results[0].content.lower()

    @pytest.mark.asyncio
    async def test_raw_arguments_are_recovered_via_executor(self) -> None:
        registry = _make_registry()
        ctx = _make_ctx(registry)
        results = await _dispatch_tools(
            [{"id": "x", "name": "echo", "arguments": {"__raw__": '{"text":"hello"}'}}],
            ctx,
        )
        assert len(results) == 1
        assert results[0].success is True
        assert "hello" in results[0].content


class TestAskUserPendingStubInject:
    """OpenAI-shaped history must have a ``tool`` row per ``ask_user`` tool_call_id."""

    def test_injects_stub_after_assistant_without_tool_reply(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-ask", "name": "ask_user", "arguments": "{}"},
                ],
            },
        ]
        _inject_pending_ask_user_tool_stubs(messages)
        assert len(messages) == 3
        assert messages[2]["role"] == "tool"
        assert messages[2]["tool_call_id"] == "call-ask"
        assert messages[2]["content"] == ASK_USER_PENDING_TOOL_JSON

    def test_skips_when_tool_already_present(self) -> None:
        body = '{"answers": []}'
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-ask", "name": "ask_user", "arguments": "{}"},
                ],
            },
            {"role": "tool", "tool_call_id": "call-ask", "content": body},
        ]
        _inject_pending_ask_user_tool_stubs(messages)
        assert len(messages) == 3
        assert messages[2]["content"] == body


class TestInterruptedToolStubInject:
    """History must include a ``tool`` row for every ``tool_call`` id (OpenAI contract)."""

    def test_injects_stub_when_no_tool_messages_follow(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-a", "name": "echo", "arguments": "{}"},
                ],
            },
        ]
        inject_missing_tool_result_stubs(messages)
        assert len(messages) == 3
        assert messages[2]["role"] == "tool"
        assert messages[2]["tool_call_id"] == "call-a"
        assert messages[2]["name"] == "echo"
        assert "_interrupted" in messages[2]["content"]

    def test_injects_only_missing_ids_when_partial_tool_block(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "c1", "name": "a", "arguments": "{}"},
                    {"id": "c2", "name": "b", "arguments": "{}"},
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "a", "content": "{}"},
            {"role": "user", "content": "continue"},
        ]
        inject_missing_tool_result_stubs(messages)
        assert len(messages) == 5
        assert messages[3]["role"] == "tool"
        assert messages[3]["tool_call_id"] == "c2"
        assert messages[4]["role"] == "user"

    def test_ask_user_stub_not_replaced_when_present(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-ask", "name": "ask_user", "arguments": "{}"},
                ],
            },
        ]
        _inject_pending_ask_user_tool_stubs(messages)
        inject_missing_tool_result_stubs(messages)
        assert len(messages) == 3
        assert messages[2]["content"] == ASK_USER_PENDING_TOOL_JSON


class TestDropOrphanToolMessages:
    """Providers reject ``tool`` without a preceding assistant ``tool_calls``."""

    def test_drops_head_orphans(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "tool", "tool_call_id": "orphan", "content": "{}"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ok"},
        ]
        drop_orphan_tool_messages(messages)
        assert [m["role"] for m in messages] == ["user", "assistant"]

    def test_drops_mid_history_orphans_after_summary(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "[Summary of earlier messages]"},
            {"role": "tool", "tool_call_id": "call-1", "content": "{}"},
            {"role": "tool", "tool_call_id": "call-2", "content": "{}"},
            {"role": "user", "content": "continue"},
            {"role": "assistant", "content": "ok"},
        ]
        drop_orphan_tool_messages(messages)
        assert [m["role"] for m in messages] == ["system", "user", "assistant"]

    def test_keeps_valid_tool_block(self) -> None:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-a", "name": "echo", "arguments": "{}"},
                ],
            },
            {"role": "tool", "tool_call_id": "call-a", "content": "{}"},
            {"role": "assistant", "content": "done"},
        ]
        drop_orphan_tool_messages(messages)
        assert len(messages) == 4
        assert messages[2]["tool_call_id"] == "call-a"

    def test_drops_tool_with_unknown_call_id(self) -> None:
        messages: list[dict[str, Any]] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-a", "name": "echo", "arguments": "{}"},
                ],
            },
            {"role": "tool", "tool_call_id": "call-a", "content": "ok"},
            {"role": "tool", "tool_call_id": "call-zombie", "content": "bad"},
        ]
        drop_orphan_tool_messages(messages)
        assert len(messages) == 2
        assert messages[1]["tool_call_id"] == "call-a"


# ---------------------------------------------------------------------------
# QueryEngine SDK mapping
# ---------------------------------------------------------------------------


class TestQueryEngine:
    @pytest.mark.asyncio
    async def test_submit_message_emits_sdk_frames(self) -> None:
        registry = _make_registry()
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(content_delta="Hi"),
                    ModelStreamEvent(message_stop={"finish_reason": "stop", "usage": {"total_tokens": 2}}),
                ]
            ]
        )
        cfg = QueryEngineConfig(
            cwd=".",
            llm=object(),  # never touched — ``deps`` shortcuts the call_model path
            tools=registry,
            executor=ToolExecutor(registry=registry, service_manager=None),
            deps=deps,
            system_prompt="test agent",
        )
        engine = QueryEngine(cfg)

        types: list[str] = []
        async for msg in engine.submit_message("hello"):
            types.append(msg.type)

        # Must always start with system_init and end with result.
        assert types[0] == "system_init"
        assert types[-1] == "result"
        assert "stream_delta" in types
        assert "assistant" in types

    @pytest.mark.asyncio
    async def test_tool_use_then_tool_result(self) -> None:
        registry = _make_registry()
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(
                        tool_call={"id": "c1", "name": "echo", "arguments": {"text": "a"}},
                    ),
                    ModelStreamEvent(message_stop={"finish_reason": "tool_calls", "usage": {}}),
                ],
                [
                    ModelStreamEvent(content_delta="ok"),
                    ModelStreamEvent(message_stop={"finish_reason": "stop", "usage": {}}),
                ],
            ]
        )
        cfg = QueryEngineConfig(
            cwd=".",
            llm=object(),
            tools=registry,
            executor=ToolExecutor(registry=registry, service_manager=None),
            deps=deps,
            system_prompt="test agent",
        )
        engine = QueryEngine(cfg)

        frames: list[SDKMessage] = []
        async for msg in engine.submit_message("run echo"):
            frames.append(msg)

        types = [f.type for f in frames]
        assert "tool_use" in types
        assert "tool_result" in types
        # tool_use must precede its tool_result
        assert types.index("tool_use") < types.index("tool_result")

        tool_use = next(f for f in frames if f.type == "tool_use")
        assert tool_use.data["name"] == "echo"
        assert tool_use.data["input"] == {"text": "a"}

        result_frame = next(f for f in frames if f.type == "result")
        assert result_frame.data["reason"] == "completed"

    @pytest.mark.asyncio
    async def test_history_retained_between_turns(self) -> None:
        """``submit_message`` should append the user + assistant turns."""
        registry = _make_registry()
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(content_delta="a1"),
                    ModelStreamEvent(message_stop={"finish_reason": "stop", "usage": {}}),
                ],
                [
                    ModelStreamEvent(content_delta="a2"),
                    ModelStreamEvent(message_stop={"finish_reason": "stop", "usage": {}}),
                ],
            ]
        )
        cfg = QueryEngineConfig(
            cwd=".",
            llm=object(),
            tools=registry,
            executor=ToolExecutor(registry=registry, service_manager=None),
            deps=deps,
            system_prompt="test agent",
        )
        engine = QueryEngine(cfg)

        async for _ in engine.submit_message("q1"):
            pass
        async for _ in engine.submit_message("q2"):
            pass

        roles = [m["role"] for m in engine.mutable_messages]
        # user, assistant, user, assistant (tool_results would be present only if tool calls happened).
        assert roles.count("user") == 2
        assert roles.count("assistant") >= 2

    @pytest.mark.asyncio
    async def test_abort_short_circuits(self) -> None:
        registry = _make_registry()
        deps = _make_deps(
            [
                [
                    ModelStreamEvent(content_delta="x"),
                    ModelStreamEvent(message_stop={"finish_reason": "stop", "usage": {}}),
                ]
            ]
        )
        cfg = QueryEngineConfig(
            cwd=".",
            llm=object(),
            tools=registry,
            executor=ToolExecutor(registry=registry, service_manager=None),
            deps=deps,
            system_prompt="test agent",
        )
        engine = QueryEngine(cfg)
        engine.abort()  # set before the stream even starts

        frames = [m async for m in engine.submit_message("x")]
        types = [f.type for f in frames]
        assert types[-1] == "result"
        result = frames[-1]
        assert result.data["reason"] == "aborted_streaming"


# ---------------------------------------------------------------------------
# System-prompt hygiene: no hard-coded persona text
# ---------------------------------------------------------------------------


class TestPromptOwnership:
    @pytest.mark.asyncio
    async def test_engine_respects_persona_override(self, tmp_path) -> None:
        """Persona text comes from the caller or a template file, never Python.

        With the ContextManager, the engine delegates context assembly.
        We create a minimal template variant and verify that (a) the
        auto-generated capabilities block appears and (b) a caller persona
        override takes effect.
        """
        from leagent.prompts import PromptBuilder
        from leagent.prompts.registry import PromptRegistry

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        (tpl_dir / "ownership.md").write_text(
            "---\nname: ownership\nlayers:\n  - persona\n  - capabilities\n---\n\n",
            encoding="utf-8",
        )
        prompt_builder = PromptBuilder(
            registry=PromptRegistry(templates_dir=tpl_dir)
        )

        registry = _make_registry()
        cfg = QueryEngineConfig(
            cwd=".",
            llm=object(),
            tools=registry,
            executor=ToolExecutor(registry=registry, service_manager=None),
            deps=_make_deps([[ModelStreamEvent(message_stop={"finish_reason": "stop"})]]),
            system_prompt="",
            prompt_variant="ownership",
            prompt_builder=prompt_builder,
        )
        engine = QueryEngine(cfg)
        turn = await engine._context.prepare_turn("", task_id=uuid4())
        prompt = turn.built_prompt.system_text
        assert "Available tools:" in prompt
        forbidden = ["You are LeAgent", "intelligent assistant", "Excel"]
        for needle in forbidden:
            assert needle not in prompt, f"hardcoded persona leaked: {needle!r}"

        cfg_override = QueryEngineConfig(
            cwd=".",
            llm=object(),
            tools=registry,
            executor=ToolExecutor(registry=registry, service_manager=None),
            deps=_make_deps([[ModelStreamEvent(message_stop={"finish_reason": "stop"})]]),
            system_prompt="CALLER PERSONA",
            prompt_variant="ownership",
            prompt_builder=prompt_builder,
        )
        engine2 = QueryEngine(cfg_override)
        turn2 = await engine2._context.prepare_turn("", task_id=uuid4(), persona_override="CALLER PERSONA")
        assert turn2.built_prompt.system_text.startswith("CALLER PERSONA")


# ---------------------------------------------------------------------------
# finish_reason="length" recovery without stream_error
# ---------------------------------------------------------------------------


class TestLengthTruncationRecovery:
    @pytest.mark.asyncio
    async def test_length_without_stream_error_triggers_recovery(self) -> None:
        """When the provider returns finish_reason='length' without an error
        payload (e.g. DeepSeek), the loop should retry with a doubled
        max_output_tokens instead of silently completing."""
        turn_idx = {"n": 0}

        async def _call_model(
            *,
            messages,
            system_prompt,
            tools,
            tool_use_context,
            temperature=None,
            max_output_tokens=None,
        ):
            idx = turn_idx["n"]
            turn_idx["n"] += 1
            if idx == 0:
                yield ModelStreamEvent(content_delta="partial code...")
                yield ModelStreamEvent(
                    message_stop={
                        "finish_reason": "length",
                        "usage": {"total_tokens": 4000},
                    }
                )
            else:
                yield ModelStreamEvent(content_delta="Here is the full answer.")
                yield ModelStreamEvent(
                    message_stop={
                        "finish_reason": "stop",
                        "usage": {"total_tokens": 6000},
                    }
                )

        deps = QueryDeps(
            call_model=_call_model,
            microcompact=_identity_compact,
            autocompact=_identity_compact,
        )
        registry = _make_registry()
        ctx = _make_ctx(registry)
        params = QueryParams(
            messages=[{"role": "user", "content": "generate code"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_output_tokens=4096,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        assistants = [e for e in events if isinstance(e, AssistantMessage)]
        terminals = [e for e in events if isinstance(e, Terminal)]

        assert turn_idx["n"] == 2, "should have retried after length truncation"
        assert len(terminals) == 1
        assert terminals[0].reason == TerminalReason.COMPLETED
        assert any("full answer" in a.content for a in assistants)

    @pytest.mark.asyncio
    async def test_length_recovery_bounded_by_max_retries(self) -> None:
        """Recovery from finish_reason='length' stops after 2 attempts."""

        async def _always_length(
            *,
            messages,
            system_prompt,
            tools,
            tool_use_context,
            temperature=None,
            max_output_tokens=None,
        ):
            yield ModelStreamEvent(content_delta="truncated")
            yield ModelStreamEvent(
                message_stop={
                    "finish_reason": "length",
                    "usage": {"total_tokens": 4000},
                }
            )

        deps = QueryDeps(
            call_model=_always_length,
            microcompact=_identity_compact,
            autocompact=_identity_compact,
        )
        registry = _make_registry()
        ctx = _make_ctx(registry)
        params = QueryParams(
            messages=[{"role": "user", "content": "generate code"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_output_tokens=4096,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        terminals = [e for e in events if isinstance(e, Terminal)]
        assert len(terminals) == 1
        assert terminals[0].reason == TerminalReason.COMPLETED
        assistants = [e for e in events if isinstance(e, AssistantMessage)]
        assert any(
            "maximum output length" in a.content.lower()
            or "interrupted" in a.content.lower()
            for a in assistants
        )
        assert terminals[0].meta.get("truncation_exhausted") is True

    @pytest.mark.asyncio
    async def test_length_truncation_injects_recovery_hint_for_raw_tool_args(
        self,
    ) -> None:
        """When length truncation breaks tool JSON, retry messages include staging hint."""
        captured_messages: list[list[dict[str, Any]]] = []

        async def _call_model(
            *,
            messages,
            system_prompt,
            tools,
            tool_use_context,
            temperature=None,
            max_output_tokens=None,
        ):
            captured_messages.append(list(messages))
            if len(captured_messages) == 1:
                yield ModelStreamEvent(
                    tool_call={
                        "id": "call_trunc",
                        "name": "tool_argument_blob",
                        "arguments": {
                            "__raw__": (
                                '{"action":"create_and_finalize",'
                                '"chunk_base64":"PCFET0NUWVBFIGh0bWw'
                            ),
                        },
                    }
                )
                yield ModelStreamEvent(
                    message_stop={
                        "finish_reason": "length",
                        "usage": {"total_tokens": 4000},
                    }
                )
            else:
                yield ModelStreamEvent(content_delta="ok")
                yield ModelStreamEvent(
                    message_stop={"finish_reason": "stop", "usage": {}}
                )

        deps = QueryDeps(
            call_model=_call_model,
            microcompact=_identity_compact,
            autocompact=_identity_compact,
        )
        registry = _make_registry()
        ctx = _make_ctx(registry)
        params = QueryParams(
            messages=[{"role": "user", "content": "publish html"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_output_tokens=4096,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        assert len(captured_messages) >= 2
        retry_msgs = captured_messages[1]
        hint_msgs = [
            m
            for m in retry_msgs
            if m.get("role") == "user"
            and "tool_argument_blob" in str(m.get("content", ""))
            and "create_and_finalize" in str(m.get("content", ""))
        ]
        assert hint_msgs, "expected chunked-staging hint on recovery retry"

    @pytest.mark.asyncio
    async def test_length_with_stream_error_still_recovers(self) -> None:
        """The original stream_error path still triggers recovery."""
        turn_idx = {"n": 0}

        async def _call_model(
            *,
            messages,
            system_prompt,
            tools,
            tool_use_context,
            temperature=None,
            max_output_tokens=None,
        ):
            idx = turn_idx["n"]
            turn_idx["n"] += 1
            if idx == 0:
                yield ModelStreamEvent(content_delta="partial")
                yield ModelStreamEvent(
                    message_stop={
                        "finish_reason": "length",
                        "usage": {"total_tokens": 4000},
                        "error": "max_output_tokens reached",
                    }
                )
            else:
                yield ModelStreamEvent(content_delta="done")
                yield ModelStreamEvent(
                    message_stop={"finish_reason": "stop", "usage": {}}
                )

        deps = QueryDeps(
            call_model=_call_model,
            microcompact=_identity_compact,
            autocompact=_identity_compact,
        )
        registry = _make_registry()
        ctx = _make_ctx(registry)
        params = QueryParams(
            messages=[{"role": "user", "content": "test"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_output_tokens=4096,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        terminals = [e for e in events if isinstance(e, Terminal)]
        assert turn_idx["n"] == 2
        assert terminals[-1].reason == TerminalReason.COMPLETED


class TestCanvasLengthSalvage:
    def test_prepare_canvas_length_salvage_closes_html(self) -> None:
        body = "<!DOCTYPE html><html><body>" + ("x" * 600)
        tool_calls = [
            {
                "id": "c1",
                "name": "canvas_publish",
                "arguments": {
                    "title": "Page",
                    "mode": "html",
                    "html": body,
                },
            }
        ]
        salvage = _prepare_canvas_length_salvage(tool_calls)
        assert salvage is not None
        assert salvage.incomplete is True
        assert salvage.html_closed_by_runtime is True
        html = tool_calls[0]["arguments"]["html"]
        assert "</html>" in html.lower()

    def test_canvas_intent_bumps_max_output_tokens(self) -> None:
        assert resolve_canvas_intent_max_output_tokens(
            "make a landing page",
            base=8192,
        ) == CANVAS_INTENT_MAX_OUTPUT_TOKENS
        assert CANVAS_INTENT_MAX_OUTPUT_TOKENS >= 32_768
        assert resolve_canvas_intent_max_output_tokens(
            "summarize this PDF",
            base=8192,
        ) == 8192
        assert resolve_canvas_intent_max_output_tokens(
            "@skill:Frontend_Design#frontend-design 优化一下设计",
            base=8192,
        ) == CANVAS_INTENT_MAX_OUTPUT_TOKENS
        assert resolve_canvas_intent_max_output_tokens(
            "美化一下这个页面",
            base=8192,
        ) == CANVAS_INTENT_MAX_OUTPUT_TOKENS

    def test_canvas_intent_sticky_from_prior_canvas_publish(self) -> None:
        prior = [
            {"role": "user", "content": "做一个网页"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "c1",
                        "name": "canvas_publish",
                        "arguments": {"mode": "html"},
                    }
                ],
            },
            {"role": "tool", "content": '{"preview_path":"/api/v1/canvas/preview?token=x"}'},
        ]
        assert resolve_canvas_intent_max_output_tokens(
            "再改一下排版",
            base=8192,
            messages=prior,
        ) == CANVAS_INTENT_MAX_OUTPUT_TOKENS
        assert resolve_canvas_intent_max_output_tokens(
            "再改一下排版",
            base=8192,
            messages=[{"role": "user", "content": "hello"}],
        ) == 8192

    def test_recovery_hint_for_canvas_without_raw_args(self) -> None:
        registry = _make_registry()
        ctx = _make_ctx(registry)
        state = QueryState(
            messages=[{"role": "user", "content": "webpage"}],
            tool_use_context=ctx,
            auto_compact_tracking=AutoCompactTrackingState(),
        )
        params = QueryParams(
            messages=state.messages,
            system_prompt="test",
            tool_use_context=ctx,
            deps=_make_deps([[]]),
            max_output_tokens=4096,
        )
        recovered = _build_length_recovery_state(
            state,
            params,
            [
                {
                    "id": "c1",
                    "name": "canvas_publish",
                    "arguments": {"title": "t", "mode": "html"},
                }
            ],
        )
        hint_msgs = [
            m
            for m in recovered.messages
            if m.get("role") == "user" and "html_paths" in str(m.get("content", ""))
        ]
        assert hint_msgs
        assert "tool_argument_blob" in str(hint_msgs[0].get("content", ""))
        assert recovered.max_output_tokens_recovery_count == 1

    def test_second_recovery_sets_force_sharded_html(self) -> None:
        registry = _make_registry()
        ctx = _make_ctx(registry)
        state = QueryState(
            messages=[{"role": "user", "content": "webpage"}],
            tool_use_context=ctx,
            auto_compact_tracking=AutoCompactTrackingState(),
            max_output_tokens_recovery_count=1,
        )
        params = QueryParams(
            messages=state.messages,
            system_prompt="test",
            tool_use_context=ctx,
            deps=_make_deps([[]]),
            max_output_tokens=4096,
        )
        _build_length_recovery_state(
            state,
            params,
            [
                {
                    "id": "c1",
                    "name": "canvas_publish",
                    "arguments": {"title": "t", "mode": "html"},
                }
            ],
        )
        assert ctx.extra.get("force_sharded_html") is True

    @pytest.mark.asyncio
    async def test_length_with_salvaged_canvas_publish_executes_tool(self) -> None:
        """Salvageable canvas_publish on length must dispatch, not regenerate."""
        stub = _CanvasPublishStub()
        html = (
            "<!DOCTYPE html><html><head><title>Hi</title></head>"
            "<body>" + ("section " * 80) + "</body></html>"
        )
        turn_idx = {"n": 0}
        captured_max: list[int | None] = []

        async def _call_model(
            *,
            messages,
            system_prompt,
            tools,
            tool_use_context,
            temperature=None,
            max_output_tokens=None,
        ):
            captured_max.append(max_output_tokens)
            idx = turn_idx["n"]
            turn_idx["n"] += 1
            if idx == 0:
                yield ModelStreamEvent(
                    tool_call={
                        "id": "call_canvas",
                        "name": "canvas_publish",
                        "arguments": {
                            "title": "Landing",
                            "mode": "html",
                            "html": html,
                        },
                    }
                )
                yield ModelStreamEvent(
                    message_stop={
                        "finish_reason": "length",
                        "usage": {"total_tokens": 4000},
                    }
                )
            else:
                yield ModelStreamEvent(content_delta="Published.")
                yield ModelStreamEvent(
                    message_stop={"finish_reason": "stop", "usage": {}}
                )

        deps = QueryDeps(
            call_model=_call_model,
            microcompact=_identity_compact,
            autocompact=_identity_compact,
        )
        registry = _make_registry(stub)
        ctx = _make_ctx(registry)
        params = QueryParams(
            messages=[{"role": "user", "content": "make a landing page"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_output_tokens=4096,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        assert len(stub.calls) == 1, "salvaged canvas_publish should execute once"
        assert stub.calls[0]["html"].endswith("</html>")
        tool_results = [e for e in events if isinstance(e, ToolResultMessage)]
        assert tool_results
        assert tool_results[0].success is True
        terminals = [e for e in events if isinstance(e, Terminal)]
        assert terminals[-1].reason == TerminalReason.COMPLETED
        # First call used base tokens; no regenerate bump before tool exec.
        assert captured_max[0] == 4096

    @pytest.mark.asyncio
    async def test_length_canvas_without_html_injects_hint_on_regenerate(self) -> None:
        captured_messages: list[list[dict[str, Any]]] = []

        async def _call_model(
            *,
            messages,
            system_prompt,
            tools,
            tool_use_context,
            temperature=None,
            max_output_tokens=None,
        ):
            captured_messages.append(list(messages))
            if len(captured_messages) == 1:
                yield ModelStreamEvent(
                    tool_call={
                        "id": "call_canvas",
                        "name": "canvas_publish",
                        "arguments": {"title": "Landing", "mode": "html"},
                    }
                )
                yield ModelStreamEvent(
                    message_stop={
                        "finish_reason": "length",
                        "usage": {"total_tokens": 4000},
                    }
                )
            else:
                yield ModelStreamEvent(content_delta="ok")
                yield ModelStreamEvent(
                    message_stop={"finish_reason": "stop", "usage": {}}
                )

        deps = QueryDeps(
            call_model=_call_model,
            microcompact=_identity_compact,
            autocompact=_identity_compact,
        )
        registry = _make_registry(_CanvasPublishStub())
        ctx = _make_ctx(registry)
        params = QueryParams(
            messages=[{"role": "user", "content": "publish html"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_output_tokens=4096,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        assert len(captured_messages) >= 2
        retry_msgs = captured_messages[1]
        hint_msgs = [
            m
            for m in retry_msgs
            if m.get("role") == "user"
            and "html_paths" in str(m.get("content", ""))
            and "tool_argument_blob" in str(m.get("content", ""))
        ]
        assert hint_msgs, "expected canvas routing hint on regenerate"

    @pytest.mark.asyncio
    async def test_force_sharded_blocks_inline_after_recovery(self) -> None:
        stub = _CanvasPublishStub()
        html = (
            "<!DOCTYPE html><html><body>" + ("y" * 600) + "</body></html>"
        )
        turn_idx = {"n": 0}

        async def _call_model(
            *,
            messages,
            system_prompt,
            tools,
            tool_use_context,
            temperature=None,
            max_output_tokens=None,
        ):
            idx = turn_idx["n"]
            turn_idx["n"] += 1
            if idx == 0:
                yield ModelStreamEvent(
                    tool_call={
                        "id": "call_canvas",
                        "name": "canvas_publish",
                        "arguments": {
                            "title": "Landing",
                            "mode": "html",
                            "html": html,
                        },
                    }
                )
                yield ModelStreamEvent(
                    message_stop={"finish_reason": "tool_calls", "usage": {}}
                )
            else:
                yield ModelStreamEvent(content_delta="switched to html_files")
                yield ModelStreamEvent(
                    message_stop={"finish_reason": "stop", "usage": {}}
                )

        deps = QueryDeps(
            call_model=_call_model,
            microcompact=_identity_compact,
            autocompact=_identity_compact,
        )
        registry = _make_registry(stub)
        ctx = _make_ctx(registry)
        ctx.extra["force_sharded_html"] = True
        params = QueryParams(
            messages=[{"role": "user", "content": "webpage"}],
            system_prompt="test",
            tool_use_context=ctx,
            deps=deps,
            max_output_tokens=4096,
        )

        events: list[Any] = []
        async for item in query(params):
            events.append(item)

        assert stub.calls == []
        tool_results = [e for e in events if isinstance(e, ToolResultMessage)]
        assert tool_results
        assert tool_results[0].success is False
        assert "blocked" in (tool_results[0].content or "").lower()
        terminals = [e for e in events if isinstance(e, Terminal)]
        assert terminals[-1].reason == TerminalReason.COMPLETED
