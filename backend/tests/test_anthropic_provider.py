"""Offline tests for the Anthropic LLM provider.

These never hit the network: we exercise the pure-Python surface
(``_split_messages``, ``_build_request_body``, ``_parse_response``,
``_process_stream_event``, constructor defaults, error handling,
thinking support, and streaming tool assembly).
"""

from __future__ import annotations

import json

import pytest

from leagent.llm.base import ChatMessage, MessageRole, StreamChunk, TokenUsage, ToolCall, ToolDefinition
from leagent.llm.providers.anthropic import AnthropicProvider
from leagent.exceptions.llm import (
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestAnthropicProviderDefaults:
    def test_default_attributes(self) -> None:
        p = AnthropicProvider(api_key="k")
        assert p.name == "anthropic"
        assert p.supports_streaming is True
        assert p.supports_tools is True
        assert p.supports_embeddings is False
        assert p.supports_vision is True
        assert p.base_url == "https://api.anthropic.com/v1"
        assert p.default_model == "claude-sonnet-4-20250514"

    def test_accepts_overrides(self) -> None:
        p = AnthropicProvider(
            api_key="k",
            base_url="https://proxy.example/v1",
            default_model="claude-opus-4-7",
            timeout=60.0,
        )
        assert p.base_url == "https://proxy.example/v1"
        assert p.default_model == "claude-opus-4-7"
        assert p.timeout == 60.0

    def test_headers(self) -> None:
        p = AnthropicProvider(api_key="sk-ant-test")
        headers = p._get_headers()
        assert headers["x-api-key"] == "sk-ant-test"
        assert headers["anthropic-version"] == "2023-06-01"


# ---------------------------------------------------------------------------
# Message splitting
# ---------------------------------------------------------------------------

class TestAnthropicMessageSplitting:
    def test_system_prompt_extracted(self) -> None:
        p = AnthropicProvider(api_key="k")
        msgs = [
            ChatMessage.system("You are helpful"),
            ChatMessage.user("Hello"),
        ]
        system, chat = p._split_messages(msgs)
        assert system == "You are helpful"
        assert len(chat) == 1
        assert chat[0]["role"] == "user"
        assert chat[0]["content"] == "Hello"

    def test_tool_result_message(self) -> None:
        p = AnthropicProvider(api_key="k")
        msgs = [ChatMessage.tool("result data", "call_123")]
        _, chat = p._split_messages(msgs)
        assert chat[0]["role"] == "user"
        assert chat[0]["content"][0]["type"] == "tool_result"
        assert chat[0]["content"][0]["tool_use_id"] == "call_123"
        assert chat[0]["content"][0]["content"] == "result data"

    def test_assistant_with_tool_calls(self) -> None:
        p = AnthropicProvider(api_key="k")
        tc = ToolCall(id="tc_1", name="echo", arguments='{"text":"hi"}')
        msgs = [ChatMessage.assistant(content="Let me use a tool", tool_calls=[tc])]
        _, chat = p._split_messages(msgs)
        assert chat[0]["role"] == "assistant"
        blocks = chat[0]["content"]
        assert blocks[0] == {"type": "text", "text": "Let me use a tool"}
        assert blocks[1]["type"] == "tool_use"
        assert blocks[1]["id"] == "tc_1"
        assert blocks[1]["name"] == "echo"
        assert blocks[1]["input"] == {"text": "hi"}

    def test_plain_user_message(self) -> None:
        p = AnthropicProvider(api_key="k")
        msgs = [ChatMessage.user("Hello")]
        _, chat = p._split_messages(msgs)
        assert chat[0] == {"role": "user", "content": "Hello"}


# ---------------------------------------------------------------------------
# Request body construction
# ---------------------------------------------------------------------------

class TestAnthropicBuildRequestBody:
    def test_basic_body(self) -> None:
        p = AnthropicProvider(api_key="k")
        msgs = [ChatMessage.system("sys"), ChatMessage.user("hi")]
        body = p._build_request_body(
            messages=msgs, model="claude-sonnet-4-20250514",
            temperature=0.5, max_tokens=1000, tools=None,
            tool_choice=None, stop=None,
        )
        assert body["model"] == "claude-sonnet-4-20250514"
        assert body["max_tokens"] == 1000
        assert body["system"] == "sys"
        assert body["stream"] is False

    def test_tools_and_tool_choice(self) -> None:
        p = AnthropicProvider(api_key="k")
        tools = [ToolDefinition(name="echo", description="Echo", parameters={"type": "object"})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            messages=msgs, model="claude-sonnet-4-20250514",
            temperature=0.5, max_tokens=1000, tools=tools,
            tool_choice="required", stop=None,
        )
        assert body["tools"][0]["name"] == "echo"
        assert body["tool_choice"] == {"type": "any"}

    def test_tool_choice_auto(self) -> None:
        p = AnthropicProvider(api_key="k")
        tools = [ToolDefinition(name="t", description="d", parameters={})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            messages=msgs, model="m", temperature=0.5,
            max_tokens=100, tools=tools, tool_choice="auto", stop=None,
        )
        assert body["tool_choice"] == {"type": "auto"}

    def test_tool_choice_none(self) -> None:
        p = AnthropicProvider(api_key="k")
        tools = [ToolDefinition(name="t", description="d", parameters={})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            messages=msgs, model="m", temperature=0.5,
            max_tokens=100, tools=tools, tool_choice="none", stop=None,
        )
        assert body["tool_choice"] == {"type": "none"}

    def test_tool_choice_named(self) -> None:
        p = AnthropicProvider(api_key="k")
        tools = [ToolDefinition(name="echo", description="d", parameters={})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            messages=msgs, model="m", temperature=0.5,
            max_tokens=100, tools=tools, tool_choice="echo", stop=None,
        )
        assert body["tool_choice"] == {"type": "tool", "name": "echo"}

    def test_thinking_parameter(self) -> None:
        p = AnthropicProvider(api_key="k")
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            messages=msgs, model="claude-opus-4-7",
            temperature=0.5, max_tokens=4096, tools=None,
            tool_choice=None, stop=None,
            thinking={"type": "adaptive"},
        )
        assert body["thinking"] == {"type": "adaptive"}

    def test_stop_sequences(self) -> None:
        p = AnthropicProvider(api_key="k")
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            messages=msgs, model="m", temperature=0.5,
            max_tokens=100, tools=None, tool_choice=None,
            stop=["END", "STOP"],
        )
        assert body["stop_sequences"] == ["END", "STOP"]


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestAnthropicResponseParsing:
    def test_parse_text_response(self) -> None:
        p = AnthropicProvider(api_key="k")
        data = {
            "content": [{"type": "text", "text": "Hello!"}],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        resp = p._parse_response(data, "claude-sonnet-4-20250514")
        assert resp.content == "Hello!"
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"
        assert resp.stop_reason == "end_turn"
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.completion_tokens == 5

    def test_parse_tool_use_response(self) -> None:
        p = AnthropicProvider(api_key="k")
        data = {
            "content": [
                {"type": "text", "text": "I'll use a tool"},
                {"type": "tool_use", "id": "tc_1", "name": "echo", "input": {"text": "hi"}},
            ],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 15},
        }
        resp = p._parse_response(data, "claude-sonnet-4-20250514")
        assert resp.content == "I'll use a tool"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "tc_1"
        assert resp.tool_calls[0].name == "echo"
        assert json.loads(resp.tool_calls[0].arguments) == {"text": "hi"}
        assert resp.finish_reason == "tool_calls"
        assert resp.stop_reason == "tool_use"

    def test_parse_thinking_response(self) -> None:
        p = AnthropicProvider(api_key="k")
        data = {
            "content": [
                {"type": "thinking", "thinking": "Let me think step by step..."},
                {"type": "text", "text": "The answer is 42."},
            ],
            "model": "claude-opus-4-7",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 50},
        }
        resp = p._parse_response(data, "claude-opus-4-7")
        assert resp.content == "The answer is 42."
        assert resp.reasoning_content == "Let me think step by step..."

    def test_parse_max_tokens_stop(self) -> None:
        p = AnthropicProvider(api_key="k")
        data = {
            "content": [{"type": "text", "text": "partial..."}],
            "model": "m",
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 5, "output_tokens": 100},
        }
        resp = p._parse_response(data, "m")
        assert resp.finish_reason == "length"
        assert resp.stop_reason == "max_tokens"


# ---------------------------------------------------------------------------
# Streaming event processing
# ---------------------------------------------------------------------------

class TestAnthropicStreamEvents:
    def test_text_delta(self) -> None:
        p = AnthropicProvider(api_key="k")
        event = {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}
        chunk = p._process_stream_event(event, "m", {})
        assert chunk is not None
        assert chunk.content == "Hello"

    def test_tool_use_assembly(self) -> None:
        p = AnthropicProvider(api_key="k")
        pending: dict[int, dict] = {}

        # 1. content_block_start with tool_use
        event_start = {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "tc_1", "name": "echo"},
        }
        result = p._process_stream_event(event_start, "m", pending)
        assert result is None
        assert 1 in pending
        assert pending[1]["name"] == "echo"

        # 2. input_json_delta accumulates
        event_delta1 = {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"te'},
        }
        result = p._process_stream_event(event_delta1, "m", pending)
        assert result is None

        event_delta2 = {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": 'xt":"hi"}'},
        }
        result = p._process_stream_event(event_delta2, "m", pending)
        assert result is None

        # 3. content_block_stop emits assembled tool call
        event_stop = {"type": "content_block_stop", "index": 1}
        chunk = p._process_stream_event(event_stop, "m", pending)
        assert chunk is not None
        assert len(chunk.tool_calls_delta) == 1
        tc = chunk.tool_calls_delta[0]
        assert tc["id"] == "tc_1"
        assert tc["function"]["name"] == "echo"
        assert tc["function"]["arguments"] == '{"text":"hi"}'
        assert 1 not in pending

    def test_thinking_delta(self) -> None:
        p = AnthropicProvider(api_key="k")
        event = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "thinking_delta", "thinking": "step 1"},
        }
        chunk = p._process_stream_event(event, "m", {})
        assert chunk is not None
        assert chunk.raw_delta == {"reasoning_content": "step 1"}

    def test_message_delta_stop(self) -> None:
        p = AnthropicProvider(api_key="k")
        event = {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 50},
        }
        chunk = p._process_stream_event(event, "m", {})
        assert chunk is not None
        assert chunk.finish_reason == "stop"
        assert chunk.usage is not None
        assert chunk.usage.completion_tokens == 50

    def test_message_delta_tool_use_stop(self) -> None:
        p = AnthropicProvider(api_key="k")
        event = {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 30},
        }
        chunk = p._process_stream_event(event, "m", {})
        assert chunk is not None
        assert chunk.finish_reason == "tool_calls"

    def test_message_start_usage(self) -> None:
        p = AnthropicProvider(api_key="k")
        event = {
            "type": "message_start",
            "message": {"usage": {"input_tokens": 100, "output_tokens": 0}},
        }
        chunk = p._process_stream_event(event, "m", {})
        assert chunk is not None
        assert chunk.usage is not None
        assert chunk.usage.prompt_tokens == 100

    def test_unknown_event_returns_none(self) -> None:
        p = AnthropicProvider(api_key="k")
        event = {"type": "ping"}
        chunk = p._process_stream_event(event, "m", {})
        assert chunk is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestAnthropicErrorHandling:
    def test_429_raises_rate_limit(self) -> None:
        p = AnthropicProvider(api_key="k")
        with pytest.raises(LLMRateLimitError):
            p._handle_error(429, {"error": {"message": "rate limited"}}, "m")

    def test_408_raises_timeout(self) -> None:
        p = AnthropicProvider(api_key="k")
        with pytest.raises(LLMTimeoutError):
            p._handle_error(408, {"error": {"message": "timeout"}}, "m")

    def test_other_error_raises_service_error(self) -> None:
        p = AnthropicProvider(api_key="k")
        with pytest.raises(LLMServiceError, match="Anthropic API error 500"):
            p._handle_error(500, {"error": {"message": "internal"}}, "m")


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

class TestAnthropicRegistryWiring:
    def test_providers_package_exports_anthropic(self) -> None:
        from leagent.llm.providers import AnthropicProvider as Exported
        assert Exported is AnthropicProvider

    def test_provider_config_constructs_anthropic(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        pc = ProviderConfig(
            name="anthropic-test",
            type="anthropic",
            enabled=True,
            api_key="test-key",
            base_url="",
            models=[{"name": "claude-opus-4-7", "tier": "tier1"}],
            timeout=30,
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, AnthropicProvider)
        assert provider.api_key == "test-key"
        assert provider.default_model == "claude-opus-4-7"
