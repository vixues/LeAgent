"""Tests for LLM base models, ModelRouter, and ProviderRegistry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from leagent.exceptions.llm import LLMRateLimitError, LLMServiceError, ModelNotFoundError
from leagent.llm.base import (
    ChatMessage,
    LLMResponse,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    TokenUsage,
)
from leagent.llm.registry import ProviderInfo, ProviderRegistry
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.model_spec import ModelSpec, ModelTask
from leagent.llm.service import LLMService
from leagent.llm.task_resolver import TaskResolver


# ===========================================================================
# TokenUsage
# ===========================================================================


class TestTokenUsage:
    def test_defaults(self) -> None:
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_explicit_values(self) -> None:
        usage = TokenUsage(prompt_tokens=100, completion_tokens=200, total_tokens=300)
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 200
        assert usage.total_tokens == 300


# ===========================================================================
# ChatMessage
# ===========================================================================


class TestChatMessage:
    def test_user_factory(self) -> None:
        msg = ChatMessage.user("Hello")
        assert msg.role.value == "user"
        assert msg.content == "Hello"

    def test_system_factory(self) -> None:
        msg = ChatMessage.system("System prompt")
        assert msg.role.value == "system"

    def test_assistant_factory(self) -> None:
        msg = ChatMessage.assistant("Hi there!")
        assert msg.role.value == "assistant"

    def test_tool_factory(self) -> None:
        msg = ChatMessage.tool("result", "call-1")
        assert msg.role.value == "tool"
        assert msg.tool_call_id == "call-1"

    def test_to_openai_format_user(self) -> None:
        msg = ChatMessage.user("Hello")
        fmt = msg.to_openai_format()
        assert fmt["role"] == "user"
        assert fmt["content"] == "Hello"

    def test_to_openai_format_with_tool_calls(self) -> None:
        tc = ToolCall(id="call-1", name="my_tool", arguments='{"x": 1}')
        msg = ChatMessage.assistant(tool_calls=[tc])
        fmt = msg.to_openai_format()
        assert "tool_calls" in fmt
        assert fmt["tool_calls"][0]["function"]["name"] == "my_tool"


# ===========================================================================
# LLMResponse
# ===========================================================================


class TestLLMResponse:
    def test_has_tool_calls_false(self) -> None:
        resp = LLMResponse(content="hello")
        assert not resp.has_tool_calls()

    def test_has_tool_calls_true(self) -> None:
        tc = ToolCall(id="1", name="t", arguments="{}")
        resp = LLMResponse(content=None, tool_calls=[tc])
        assert resp.has_tool_calls()

    def test_to_agent_dict(self) -> None:
        resp = LLMResponse(
            content="response text",
            model="gpt-4",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
        )
        d = resp.to_agent_dict()
        assert d["content"] == "response text"
        assert d["model"] == "gpt-4"
        assert d["usage"]["prompt_tokens"] == 10

    def test_to_message_creates_assistant(self) -> None:
        resp = LLMResponse(content="answer")
        msg = resp.to_message()
        assert msg.role.value == "assistant"
        assert msg.content == "answer"


# ===========================================================================
# StreamChunk
# ===========================================================================


class TestStreamChunk:
    def test_defaults(self) -> None:
        chunk = StreamChunk()
        assert chunk.content == ""
        assert chunk.finish_reason is None

    def test_with_content(self) -> None:
        chunk = StreamChunk(content="hello", finish_reason="stop")
        assert chunk.content == "hello"
        assert chunk.finish_reason == "stop"


# ===========================================================================
# ToolDefinition
# ===========================================================================


class TestToolDefinition:
    def test_to_openai_format(self) -> None:
        td = ToolDefinition(
            name="my_tool",
            description="Does something",
            parameters={"type": "object", "properties": {}},
        )
        fmt = td.to_openai_format()
        assert fmt["type"] == "function"
        assert fmt["function"]["name"] == "my_tool"


# ===========================================================================
# ProviderRegistry
# ===========================================================================


class TestProviderRegistry:
    def _mock_provider(self, name: str = "mock") -> MagicMock:
        provider = MagicMock()
        provider.name = name
        provider.health_check = AsyncMock(return_value=True)
        return provider

    def test_register_provider(self) -> None:
        reg = ProviderRegistry()
        prov = self._mock_provider("openai")
        reg.register("openai", prov)
        assert reg.has_provider("openai")

    def test_get_provider(self) -> None:
        reg = ProviderRegistry()
        prov = self._mock_provider("openai")
        reg.register("openai", prov)
        got = reg.get_provider("openai")
        assert got is prov

    def test_duplicate_registration_raises(self) -> None:
        reg = ProviderRegistry()
        reg.register("openai", self._mock_provider())
        with pytest.raises(ValueError, match="already registered"):
            reg.register("openai", self._mock_provider())

    def test_get_unknown_raises(self) -> None:
        reg = ProviderRegistry()
        with pytest.raises(ModelNotFoundError):
            reg.get_provider("nonexistent")

    def test_unregister(self) -> None:
        reg = ProviderRegistry()
        reg.register("openai", self._mock_provider())
        reg.unregister("openai")
        assert not reg.has_provider("openai")

    def test_list_providers(self) -> None:
        reg = ProviderRegistry()
        reg.register("prov_a", self._mock_provider("prov_a"))
        reg.register("prov_b", self._mock_provider("prov_b"))
        names = reg.list_providers()
        assert "prov_a" in names
        assert "prov_b" in names

    @pytest.mark.asyncio
    async def test_health_check_aggregation(self) -> None:
        reg = ProviderRegistry()
        prov_a = self._mock_provider("a")
        prov_b = self._mock_provider("b")
        prov_b.health_check = AsyncMock(return_value=False)

        reg.register("a", prov_a)
        reg.register("b", prov_b)
        results = await reg.test_all_connections()
        health_map = {r.provider_name: r.is_healthy for r in results}
        assert health_map["a"] is True
        assert health_map["b"] is False


# ===========================================================================
# TaskResolver
# ===========================================================================


def _minimal_catalog(provider: str = "mock", model: str = "gpt-4") -> ModelRegistry:
    catalog = ModelRegistry()
    catalog.load_from_config(
        {
            "version": 2,
            "providers": [
                {
                    "name": provider,
                    "type": "openai",
                    "enabled": True,
                    "models": [
                        {
                            "name": model,
                            "kind": "chat",
                            "capabilities": {
                                "input": ["text"],
                                "output": ["text"],
                                "tool_call": True,
                            },
                            "context_window": 128000,
                        }
                    ],
                }
            ],
            "routing": {"tasks": {"chat": {"provider": provider, "model": model}}},
        }
    )
    return catalog


class TestTaskResolver:
    def _resolver(self) -> TaskResolver:
        reg = ProviderRegistry()
        mock_prov = MagicMock()
        mock_prov.name = "mock"
        reg.register("mock", mock_prov)
        return TaskResolver(reg, _minimal_catalog())

    def test_resolve_chat_task_binding(self) -> None:
        resolved = self._resolver().resolve(ModelTask.CHAT)
        assert resolved.provider == "mock"
        assert resolved.model == "gpt-4"
        assert resolved.task == ModelTask.CHAT

    def test_explicit_user_model(self) -> None:
        resolved = self._resolver().resolve(
            ModelTask.CHAT,
            user_provider="mock",
            user_model="gpt-4",
        )
        assert resolved.reason == "user_explicit"

    def test_unknown_model_raises(self) -> None:
        with pytest.raises(ModelNotFoundError):
            self._resolver().resolve(
                ModelTask.CHAT,
                user_provider="mock",
                user_model="missing",
            )


class TestLLMServiceRetries:
    @pytest.mark.asyncio
    async def test_with_transient_retries_rate_limit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from leagent.llm.service import _with_transient_retries

        monkeypatch.setattr("leagent.llm.service.asyncio.sleep", AsyncMock())
        calls = {"n": 0}

        async def operation() -> LLMResponse:
            calls["n"] += 1
            if calls["n"] == 1:
                raise LLMRateLimitError(model="mock-model", retry_after=0.01)
            return LLMResponse(content="ok")

        result = await _with_transient_retries(operation, operation_name="test.complete")
        assert result.content == "ok"
        assert calls["n"] == 2


class TestClampMaxTokens:
    def test_clamp_reduces_output_when_prompt_is_large(self) -> None:
        from unittest.mock import patch

        registry = ProviderRegistry()
        resolver = TaskResolver(registry, ModelRegistry())
        messages = [ChatMessage.user("hello")]
        spec = ModelSpec(name="qwen-local", provider="local", context_window=32768)
        with patch(
            "tiktoken.get_encoding",
            return_value=MagicMock(encode=lambda _text: [0] * 24577),
        ):
            clamped = resolver.clamp_max_tokens(messages, spec=spec, requested=8192)
        assert clamped == 8127

    def test_clamp_unchanged_for_million_token_context(self) -> None:
        from unittest.mock import patch

        registry = ProviderRegistry()
        resolver = TaskResolver(registry, ModelRegistry())
        messages = [ChatMessage.user("hello")]
        spec = ModelSpec(name="deepseek-v4-pro", provider="deepseek", context_window=1_000_000)
        with patch(
            "tiktoken.get_encoding",
            return_value=MagicMock(encode=lambda _text: [0] * 24577),
        ):
            clamped = resolver.clamp_max_tokens(messages, spec=spec, requested=8192)
        assert clamped == 8192
