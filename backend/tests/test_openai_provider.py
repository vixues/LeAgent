"""Offline tests for the OpenAI LLM provider.

These never hit the network: we exercise the pure-Python surface
(``_parse_stream_chunk``, ``_parse_response``, ``_build_request_body``,
constructor defaults, error handling, structured outputs, reasoning_effort).
"""

from __future__ import annotations

import pytest

from leagent.llm.base import ChatMessage, StreamChunk, TokenUsage, ToolCall, ToolDefinition
from leagent.llm.providers.openai import OpenAIProvider, _context_retry_max_tokens
from leagent.exceptions.llm import (
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    ModelNotFoundError,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestOpenAIProviderDefaults:
    def test_default_attributes(self) -> None:
        p = OpenAIProvider(api_key="k")
        assert p.name == "openai"
        assert p.supports_streaming is True
        assert p.supports_tools is True
        assert p.supports_embeddings is True
        assert p.supports_structured_output is True
        assert p.supports_vision is True
        assert p.base_url == "https://api.openai.com/v1"
        assert p.default_model == "gpt-4o"

    def test_accepts_overrides(self) -> None:
        p = OpenAIProvider(
            api_key="k",
            base_url="https://proxy.example/v1",
            default_model="gpt-5.5",
            timeout=7.5,
            organization="org-123",
        )
        assert p.base_url == "https://proxy.example/v1"
        assert p.default_model == "gpt-5.5"
        assert p.timeout == 7.5
        assert p.organization == "org-123"

    def test_trailing_slash_stripped_from_base_url(self) -> None:
        p = OpenAIProvider(api_key="k", base_url="https://api.openai.com/v1/")
        assert p.base_url == "https://api.openai.com/v1"


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------

class TestOpenAIHeaders:
    def test_headers_include_auth(self) -> None:
        p = OpenAIProvider(api_key="sk-test")
        headers = p._get_headers()
        assert headers["Authorization"] == "Bearer sk-test"
        assert headers["Content-Type"] == "application/json"

    def test_headers_include_organization(self) -> None:
        p = OpenAIProvider(api_key="sk-test", organization="org-abc")
        headers = p._get_headers()
        assert headers["OpenAI-Organization"] == "org-abc"

    def test_headers_no_auth_when_empty_key(self) -> None:
        p = OpenAIProvider(api_key="")
        headers = p._get_headers()
        assert "Authorization" not in headers


# ---------------------------------------------------------------------------
# Request body construction
# ---------------------------------------------------------------------------

class TestOpenAIBuildRequestBody:
    def test_basic_body(self) -> None:
        p = OpenAIProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "gpt-4o", 0.5, 100, None, None, None)
        assert body["model"] == "gpt-4o"
        assert body["temperature"] == 0.5
        assert body["max_tokens"] == 100
        assert len(body["messages"]) == 1
        assert "stream" not in body

    def test_stream_body(self) -> None:
        p = OpenAIProvider(api_key="k")
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "gpt-4o", 0.5, 100, None, None, None, stream=True)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}

    def test_tools_in_body(self) -> None:
        p = OpenAIProvider(api_key="k")
        tools = [ToolDefinition(name="echo", description="Echo", parameters={"type": "object"})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "gpt-4o", 0.5, 100, tools, "auto", None)
        assert body["tools"][0]["type"] == "function"
        assert body["tools"][0]["function"]["name"] == "echo"
        assert body["tool_choice"] == "auto"

    def test_tool_choice_named_function(self) -> None:
        p = OpenAIProvider(api_key="k")
        tools = [ToolDefinition(name="echo", description="Echo", parameters={"type": "object"})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "gpt-4o", 0.5, 100, tools, "echo", None)
        assert body["tool_choice"] == {"type": "function", "function": {"name": "echo"}}

    def test_stop_sequences(self) -> None:
        p = OpenAIProvider(api_key="k")
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "gpt-4o", 0.5, 100, None, None, ["END"])
        assert body["stop"] == ["END"]

    def test_response_format_structured_output(self) -> None:
        p = OpenAIProvider(api_key="k")
        msgs = [ChatMessage.user("hi")]
        fmt = {
            "type": "json_schema",
            "json_schema": {
                "name": "response",
                "strict": True,
                "schema": {"type": "object", "properties": {"answer": {"type": "string"}}},
            },
        }
        body = p._build_request_body(msgs, "gpt-4o", 0.5, 100, None, None, None, response_format=fmt)
        assert body["response_format"] == fmt

    def test_reasoning_effort(self) -> None:
        p = OpenAIProvider(api_key="k")
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "o3-mini", 0.5, 100, None, None, None, reasoning_effort="high")
        assert body["reasoning_effort"] == "high"

    def test_response_format_and_reasoning_not_in_kwargs(self) -> None:
        """response_format and reasoning_effort are popped from kwargs, not duplicated."""
        p = OpenAIProvider(api_key="k")
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            msgs, "gpt-4o", 0.5, 100, None, None, None,
            response_format={"type": "json_object"},
            reasoning_effort="medium",
        )
        assert body["response_format"] == {"type": "json_object"}
        assert body["reasoning_effort"] == "medium"
        # Ensure they don't appear twice (would if not popped)
        count_rf = sum(1 for k in body if k == "response_format")
        count_re = sum(1 for k in body if k == "reasoning_effort")
        assert count_rf == 1
        assert count_re == 1


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestOpenAIResponseParsing:
    def test_parse_basic_response(self) -> None:
        p = OpenAIProvider(api_key="k")
        data = {
            "model": "gpt-4o",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        resp = p._parse_response(data)
        assert resp.content == "Hello!"
        assert resp.model == "gpt-4o"
        assert resp.finish_reason == "stop"
        assert resp.usage.prompt_tokens == 5
        assert resp.usage.completion_tokens == 2
        assert resp.tool_calls == []

    def test_parse_tool_call_response(self) -> None:
        p = OpenAIProvider(api_key="k")
        data = {
            "model": "gpt-4o",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "echo", "arguments": '{"text":"hi"}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        resp = p._parse_response(data)
        assert resp.content is None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "echo"
        assert resp.tool_calls[0].id == "call_1"
        assert resp.finish_reason == "tool_calls"

    def test_parse_usage_with_cache_tokens(self) -> None:
        p = OpenAIProvider(api_key="k")
        data = {
            "model": "gpt-4o",
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
                "prompt_tokens_details": {"cached_tokens": 80},
                "completion_tokens_details": {"reasoning_tokens": 5},
            },
        }
        resp = p._parse_response(data)
        assert resp.usage.prompt_cache_hit_tokens == 80
        assert resp.usage.reasoning_tokens == 5


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------

class TestOpenAIStreamParsing:
    def _parse(self, provider: OpenAIProvider, payload: dict) -> StreamChunk:
        return provider._parse_stream_chunk(payload, provider.default_model)

    def test_plain_content_delta(self) -> None:
        p = OpenAIProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "gpt-4o",
            "choices": [{"delta": {"content": "Hello"}, "finish_reason": None}],
        })
        assert chunk.content == "Hello"
        assert chunk.tool_calls_delta == []
        assert chunk.finish_reason is None

    def test_thinking_delta_mapped_to_reasoning_content(self) -> None:
        """Custom OpenAI-compatible gateways often use ``delta.thinking``."""
        p = OpenAIProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "custom-reasoner",
            "choices": [{"delta": {"thinking": "step 1"}, "finish_reason": None}],
        })
        assert chunk.content == ""
        assert chunk.raw_delta == {"reasoning_content": "step 1"}

    def test_reasoning_alias_delta(self) -> None:
        p = OpenAIProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "custom-reasoner",
            "choices": [{"delta": {"reasoning": "plan"}, "finish_reason": None}],
        })
        assert chunk.raw_delta == {"reasoning_content": "plan"}

    def test_parse_response_extracts_thinking_field(self) -> None:
        p = OpenAIProvider(api_key="k")
        data = {
            "model": "custom-reasoner",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "Final answer",
                    "thinking": "Internal reasoning",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        resp = p._parse_response(data)
        assert resp.reasoning_content == "Internal reasoning"
        assert resp.content == "Final answer"

    def test_parse_response_extracts_think_tags(self) -> None:
        p = OpenAIProvider(api_key="k", parse_think_tags=True)
        data = {
            "model": "custom-reasoner",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "<think>step by step</think>\nFinal answer",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        resp = p._parse_response(data)
        assert resp.reasoning_content == "step by step"
        assert resp.content == "Final answer"

    def test_parse_response_leaves_think_tags_by_default(self) -> None:
        p = OpenAIProvider(api_key="k")
        data = {
            "model": "gpt-4o",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "<think>official provider text</think>\nFinal answer",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        resp = p._parse_response(data)
        assert resp.reasoning_content is None
        assert resp.content == "<think>official provider text</think>\nFinal answer"

    def test_deepseek_does_not_enable_think_tag_parser(self) -> None:
        from leagent.llm.providers.deepseek import DeepSeekProvider

        p = DeepSeekProvider(api_key="k")
        data = {
            "model": "deepseek-v4-pro",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "<think>leave official stream untouched</think>\nFinal answer",
                    "reasoning_content": "official reasoning",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        resp = p._parse_response(data)
        assert p.parse_think_tags is False
        assert resp.reasoning_content == "official reasoning"
        assert resp.content == "<think>leave official stream untouched</think>\nFinal answer"

    def test_null_content_coalesced(self) -> None:
        p = OpenAIProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "gpt-4o",
            "choices": [{"delta": {"content": None}, "finish_reason": None}],
        })
        assert chunk.content == ""

    def test_tool_call_delta(self) -> None:
        p = OpenAIProvider(api_key="k")
        tc = [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "echo", "arguments": ""}}]
        chunk = self._parse(p, {
            "model": "gpt-4o",
            "choices": [{"delta": {"tool_calls": tc}, "finish_reason": None}],
        })
        assert chunk.tool_calls_delta == tc

    def test_finish_reason_propagates(self) -> None:
        p = OpenAIProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "gpt-4o",
            "choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
        })
        assert chunk.finish_reason == "stop"

    def test_usage_only_chunk(self) -> None:
        p = OpenAIProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "gpt-4o",
            "choices": [],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        })
        assert chunk.usage is not None
        assert chunk.usage.prompt_tokens == 10
        assert chunk.usage.completion_tokens == 20

    def test_reasoning_content_in_raw_delta(self) -> None:
        p = OpenAIProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "o3-mini",
            "choices": [{"delta": {"content": "", "reasoning_content": "thinking..."}, "finish_reason": None}],
        })
        assert chunk.raw_delta == {"reasoning_content": "thinking..."}

    def test_empty_choices_is_safe(self) -> None:
        p = OpenAIProvider(api_key="k")
        chunk = self._parse(p, {"model": "gpt-4o", "choices": []})
        assert chunk.content == ""
        assert chunk.tool_calls_delta == []

    @pytest.mark.asyncio
    async def test_think_tags_stream_as_reasoning_content(self) -> None:
        p = OpenAIProvider(api_key="k", parse_think_tags=True)
        chunks = [
            c
            async for c in p._split_think_chunk(
                StreamChunk(content="<think>plan</think>answer", model="local"),
                in_think=False,
                pending="",
            )
        ]
        clean = []
        for chunk in chunks:
            raw = dict(chunk.raw_delta or {})
            raw.pop("__in_think", None)
            raw.pop("__pending_think_tag", None)
            chunk.raw_delta = raw or None
            clean.append(chunk)
        assert clean[0].raw_delta == {"reasoning_content": "plan"}
        assert clean[0].content == ""
        assert clean[1].content == "answer"
        assert clean[1].raw_delta is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestOpenAIErrorHandling:
    def test_401_raises_service_error(self) -> None:
        p = OpenAIProvider(api_key="k")
        with pytest.raises(LLMServiceError, match="Invalid API key"):
            p._handle_error(401, {"error": {"message": "bad key"}}, "gpt-4o")

    def test_404_raises_model_not_found(self) -> None:
        p = OpenAIProvider(api_key="k")
        with pytest.raises(ModelNotFoundError):
            p._handle_error(404, {"error": {"message": "not found"}}, "gpt-999")

    def test_429_raises_rate_limit(self) -> None:
        p = OpenAIProvider(api_key="k")
        with pytest.raises(LLMRateLimitError):
            p._handle_error(429, {"error": {"message": "rate limited"}}, "gpt-4o")

    def test_500_raises_service_error(self) -> None:
        p = OpenAIProvider(api_key="k")
        with pytest.raises(LLMServiceError, match="Server error"):
            p._handle_error(500, {"error": {"message": "internal"}}, "gpt-4o")

    def test_generic_error(self) -> None:
        p = OpenAIProvider(api_key="k")
        with pytest.raises(LLMServiceError, match="API error.*400"):
            p._handle_error(400, {"error": {"message": "bad request"}}, "gpt-4o")

    def test_context_error_computes_retry_max_tokens(self) -> None:
        body = {
            "error": {
                "message": (
                    "This model's maximum context length is 32768 tokens. "
                    "However, you requested 8192 output tokens and your prompt "
                    "contains at least 24577 input tokens, for a total of at least 32769 tokens."
                )
            }
        }
        assert _context_retry_max_tokens(body, 8192) == 8063
