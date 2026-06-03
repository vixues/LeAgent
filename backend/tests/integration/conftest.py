"""Shared helpers for integration tests (offline scripted LLM + optional live API).

Offline tests replay canned ``ModelStreamEvent`` scripts — no network, no API key.

Optional live DeepSeek tests are marked ``live`` and skipped unless
``DEEPSEEK_API_KEY`` is set in the environment (never commit keys):

    export DEEPSEEK_API_KEY='your-key-here'
    export DEEPSEEK_BASE_URL='https://api.deepseek.com'
    export DEEPSEEK_MODEL='deepseek-v4-flash'
    uv run pytest tests/integration/ -m live -v
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import pytest

from leagent.agent.deps import ModelStreamEvent, QueryDeps
from leagent.agent.tool_use_context import ToolUseContext
from leagent.bootstrap.tools import register_default_tools
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.model_spec import ModelTask
from leagent.llm.providers.deepseek import DeepSeekProvider
from leagent.llm.registry import ProviderRegistry
from leagent.llm.service import LLMService
from leagent.llm.task_resolver import TaskResolver
from leagent.tools.registry import ToolRegistry


def deepseek_api_configured() -> bool:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return False
    # Reject obvious garbage / misconfigured env (e.g. pasted error JSON).
    return key.startswith("sk-") and len(key) >= 20


requires_live_deepseek = pytest.mark.skipif(
    not deepseek_api_configured(),
    reason="DEEPSEEK_API_KEY not set; live test skipped (offline tests need no key).",
)


@dataclass
class EngineTrace:
    """Collected events from one ``QueryEngine.submit_message`` run."""

    tool_uses: list[str] = field(default_factory=list)
    tool_inputs: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    assistant_chunks: list[str] = field(default_factory=list)
    final_reason: str | None = None

    @property
    def final_text(self) -> str:
        return "".join(self.assistant_chunks)

    @property
    def joined_tool_results(self) -> str:
        return "\n".join(
            str(r.get("content", "")) for r in self.tool_results
        )

    def used_tool(self, name: str) -> bool:
        return name in self.tool_uses

    def tool_use_count(self, name: str) -> int:
        return sum(1 for n in self.tool_uses if n == name)

    def parse_tool_json(self, tool_name: str) -> list[dict[str, Any]]:
        """Best-effort parse JSON bodies from tool results for *tool_name*."""
        out: list[dict[str, Any]] = []
        for tr in self.tool_results:
            if tr.get("name") != tool_name:
                continue
            raw = tr.get("content") or ""
            if not isinstance(raw, str):
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                out.append(parsed)
        return out


def _tool_calls_stop() -> ModelStreamEvent:
    return ModelStreamEvent(
        message_stop={"finish_reason": "tool_calls", "usage": {"total_tokens": 1}},
    )


def _text_stop() -> ModelStreamEvent:
    return ModelStreamEvent(
        message_stop={"finish_reason": "stop", "usage": {"total_tokens": 1}},
    )


def scripted_turn(*tool_calls: dict[str, Any]) -> list[ModelStreamEvent]:
    """One model turn that emits the given tool calls then stops."""
    events: list[ModelStreamEvent] = []
    for idx, tc in enumerate(tool_calls):
        events.append(
            ModelStreamEvent(
                tool_call={
                    "id": tc.get("id", f"call_{idx}"),
                    "name": tc["name"],
                    "arguments": tc.get("arguments", {}),
                },
            )
        )
    events.append(_tool_calls_stop())
    return events


def scripted_text_turn(text: str) -> list[ModelStreamEvent]:
    return [
        ModelStreamEvent(content_delta=text),
        _text_stop(),
    ]


def scripted_call_model(script: list[list[ModelStreamEvent]]):
    """Return a ``call_model`` coroutine that replays *script* per turn."""
    turn = {"n": 0}

    async def call_model(
        *,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]] | None,
        tool_use_context: ToolUseContext,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        model_tier: str = "tier1",
        model_provider: str | None = None,
        model_name: str | None = None,
    ) -> AsyncIterator[ModelStreamEvent]:
        del messages, system_prompt, tools, tool_use_context
        del temperature, max_output_tokens, model_tier, model_provider, model_name
        idx = min(turn["n"], len(script) - 1)
        turn["n"] += 1
        for ev in script[idx]:
            yield ev

    return call_model


def make_scripted_deps(script: list[list[ModelStreamEvent]]) -> QueryDeps:
    async def _identity(messages, tool_use_context, *args):  # noqa: ANN001
        return messages

    return QueryDeps(
        call_model=scripted_call_model(script),
        microcompact=_identity,
        autocompact=_identity,
    )


def build_deepseek_llm_service(
    *,
    model: str | None = None,
    temperature: float = 0.1,
) -> LLMService:
    """Construct a real ``LLMService`` backed by ``DeepSeekProvider``."""
    api_key = os.environ["DEEPSEEK_API_KEY"]
    base_url = os.getenv("DEEPSEEK_BASE_URL", DeepSeekProvider.DEFAULT_BASE_URL)
    resolved_model = model or os.getenv(
        "DEEPSEEK_MODEL", DeepSeekProvider.DEFAULT_MODEL,
    )

    registry = ProviderRegistry()
    provider = DeepSeekProvider(
        api_key=api_key,
        base_url=base_url,
        default_model=resolved_model,
    )
    registry.register(
        "deepseek",
        provider,
        metadata={"vendor": "deepseek", "model": resolved_model},
    )

    model_registry = ModelRegistry()
    model_registry.load_from_config(
        {
            "providers": [
                {
                    "name": "deepseek",
                    "enabled": True,
                    "models": [
                        {
                            "name": resolved_model,
                            "kind": "chat",
                            "capabilities": {
                                "input": ["text"],
                                "output": ["text"],
                                "tool_call": True,
                                "reasoning": True,
                            },
                        }
                    ],
                }
            ],
            "routing": {
                "tasks": {
                    task.value: {
                        "provider": "deepseek",
                        "model": resolved_model,
                        "temperature": temperature,
                    }
                    for task in (
                        ModelTask.CHAT,
                        ModelTask.FAST,
                        ModelTask.COMPRESSION,
                        ModelTask.TITLE,
                    )
                }
            },
        }
    )
    return LLMService(
        registry=registry,
        model_registry=model_registry,
        resolver=TaskResolver(registry, model_registry),
    )


def build_full_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_default_tools(registry=registry)
    return registry


async def drive_query_engine(
    engine: Any,
    user_prompt: str,
    *,
    timeout: float = 240.0,
) -> EngineTrace:
    """Run ``engine.submit_message`` and collect SDK messages."""
    trace = EngineTrace()

    async def _drive() -> None:
        async for msg in engine.submit_message(user_prompt):
            if msg.type == "tool_use":
                trace.tool_uses.append(str(msg.data.get("name")))
                raw_input = msg.data.get("input")
                if isinstance(raw_input, dict):
                    trace.tool_inputs.append(raw_input)
                else:
                    trace.tool_inputs.append({})
            elif msg.type == "tool_result":
                trace.tool_results.append(dict(msg.data))
            elif msg.type == "stream_delta":
                trace.assistant_chunks.append(str(msg.data.get("content", "")))
            elif msg.type == "assistant":
                if content := msg.data.get("content"):
                    trace.assistant_chunks.append(str(content))
            elif msg.type == "result":
                trace.final_reason = str(msg.data.get("reason"))

    await asyncio.wait_for(_drive(), timeout=timeout)
    return trace


@pytest.fixture(scope="module")
def deepseek_model() -> str:
    return os.getenv("DEEPSEEK_MODEL", DeepSeekProvider.DEFAULT_MODEL)


@pytest.fixture(scope="module")
def deepseek_llm(deepseek_model: str) -> LLMService:
    return build_deepseek_llm_service(model=deepseek_model)


@pytest.fixture(scope="module")
def full_tool_registry() -> ToolRegistry:
    return build_full_tool_registry()
