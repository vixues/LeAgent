"""Tests for task-based LLM routing via LLMService."""

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
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.registry import ProviderRegistry
from leagent.llm.service import LLMService


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


def _catalog_with_chat(provider: str, model: str) -> ModelRegistry:
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


def test_complete_passes_through_generation_kwargs() -> None:
    """LLMService must not duplicate temperature/max_tokens/tool_choice in kwargs."""

    async def _run() -> None:
        registry = ProviderRegistry()
        recording = _RecordingProvider()
        registry.register("mock", recording)
        catalog = _catalog_with_chat("mock", "qwen-max")
        service = LLMService(registry=registry, model_registry=catalog)

        messages = [ChatMessage.user("ping")]
        await service.complete(
            messages,
            task="chat",
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
