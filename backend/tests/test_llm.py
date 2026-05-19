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
from leagent.llm.router import ModelRouter, ModelTier, RoutingDecision, TierConfig
from leagent.llm.service import LLMService


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
# ModelRouter
# ===========================================================================


class TestModelRouter:
    def _registry(self) -> ProviderRegistry:
        reg = ProviderRegistry()
        mock_prov = MagicMock()
        mock_prov.name = "mock"
        reg.register("mock", mock_prov)
        return reg

    def _router(self) -> ModelRouter:
        reg = self._registry()
        router = ModelRouter(registry=reg)
        router.configure_tier(
            ModelTier.TIER1.value,
            provider="mock",
            model="gpt-4",
            fallback_tier=ModelTier.TIER2.value,
        )
        router.configure_tier(
            ModelTier.TIER2.value,
            provider="mock",
            model="gpt-3.5-turbo",
        )
        return router

    def test_explicit_tier_routing(self) -> None:
        router = self._router()
        decision = router.route("any task", explicit_tier=ModelTier.TIER2.value)
        assert decision.tier == ModelTier.TIER2
        assert decision.reason == "explicit_tier"

    def test_tier1_keyword_routing(self) -> None:
        router = self._router()
        decision = router.route("please analyze and plan this complex task")
        assert decision.tier == ModelTier.TIER1

    def test_tier2_keyword_routing(self) -> None:
        router = self._router()
        decision = router.route("classify this text quickly")
        assert decision.tier == ModelTier.TIER2

    def test_large_context_triggers_tier1(self) -> None:
        router = self._router()
        msgs = [ChatMessage.user("x" * 2000) for _ in range(50)]
        decision = router.route("handle this task", messages=msgs)
        assert decision.tier == ModelTier.TIER1

    def test_low_complexity_default_routes_to_tier2(self) -> None:
        router = self._router()
        decision = router.route("some unclassified task description")
        assert decision.tier == ModelTier.TIER2
        assert decision.reason == "low_complexity_heuristic"

    def test_complex_unclassified_task_defaults_to_tier1(self) -> None:
        router = self._router()
        decision = router.route(
            "Please review this production architecture and migration risk in detail."
        )
        assert decision.tier == ModelTier.TIER1

    def test_no_tiers_configured_raises(self) -> None:
        reg = self._registry()
        router = ModelRouter(registry=reg)
        with pytest.raises(LLMServiceError):
            router.route("some task")

    def test_unknown_explicit_tier_raises(self) -> None:
        router = self._router()
        with pytest.raises(ModelNotFoundError):
            router.route("task", explicit_tier="nonexistent_tier")

    def test_list_tiers(self) -> None:
        router = self._router()
        tiers = router.list_tiers()
        assert ModelTier.TIER1.value in tiers
        assert ModelTier.TIER2.value in tiers

    def test_count_tokens(self) -> None:
        router = self._router()
        tokens = router.count_tokens("Hello, world!")
        assert tokens > 0

    def test_count_message_tokens(self) -> None:
        router = self._router()
        msgs = [ChatMessage.user("Hello"), ChatMessage.assistant("Hi!")]
        total = router.count_message_tokens(msgs)
        assert total > 0


class TestLLMServiceRetries:
    @pytest.mark.asyncio
    async def test_direct_complete_retries_rate_limit(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("leagent.llm.service.asyncio.sleep", AsyncMock())

        provider = MagicMock()
        provider._get_default_model.return_value = "mock-model"
        provider.complete = AsyncMock(
            side_effect=[
                LLMRateLimitError(model="mock-model", retry_after=0.01),
                LLMResponse(content="ok"),
            ]
        )
        registry = ProviderRegistry()
        registry.register("mock", provider)
        router = ModelRouter(registry=registry)
        service = LLMService(registry=registry, router=router)

        response = await service.complete(
            [ChatMessage.user("hello")],
            provider="mock",
        )

        assert response.content == "ok"
        assert provider.complete.await_count == 2
