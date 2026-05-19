"""Tests for ModelRouter (tier routing and provider kwargs)."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from leagent.llm.base import (
    ChatMessage,
    LLMProvider,
    LLMResponse,
    StreamChunk,
    ToolDefinition,
)
from leagent.llm.registry import ProviderRegistry
from leagent.llm.router import ModelRouter


class _RecordingProvider(LLMProvider):
    """Minimal provider that records ``complete`` arguments."""

    name = "recording"

    def __init__(self) -> None:
        self.complete_calls: list[dict[str, Any]] = []

    def _get_default_model(self) -> str:
        return "dummy"

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.complete_calls.append(
            {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "tool_choice": tool_choice,
                "stop": stop,
                "extra_kwargs": dict(kwargs),
            }
        )
        return LLMResponse(content="ok", model=model)

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        yield StreamChunk(content="")


def test_complete_with_routing_no_duplicate_temperature_kwargs() -> None:
    """LLMService passes temperature/max_tokens/tool_choice in kwargs; router must not duplicate."""

    async def _run() -> None:
        registry = ProviderRegistry()
        recording = _RecordingProvider()
        registry.register("tier1_provider", recording)

        router = ModelRouter(registry=registry)
        router.configure_tier(
            tier="tier1",
            provider="tier1_provider",
            model="qwen-max",
            max_tokens=4096,
            temperature=0.1,
        )

        messages = [ChatMessage.user("ping")]
        await router.complete_with_routing(
            messages,
            explicit_tier="tier1",
            temperature=0.55,
            max_tokens=512,
            tool_choice="auto",
            custom_param="passed_through",
        )

        assert len(recording.complete_calls) == 1
        call = recording.complete_calls[0]
        assert call["temperature"] == 0.55
        assert call["max_tokens"] == 512
        assert call["tool_choice"] == "auto"
        assert "temperature" not in call["extra_kwargs"]
        assert "max_tokens" not in call["extra_kwargs"]
        assert "tool_choice" not in call["extra_kwargs"]
        assert call["extra_kwargs"].get("custom_param") == "passed_through"

    asyncio.run(_run())
