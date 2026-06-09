"""Tests for :class:`~leagent.tools.code.deepseek_fim.DeepSeekFimTool`."""

from __future__ import annotations

from typing import Any

import pytest

from leagent.llm.providers.deepseek import DeepSeekProvider
from leagent.llm.registry import ProviderRegistry
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.service import LLMService
from leagent.tools.base import ToolContext
from leagent.code.fim import DeepSeekFimTool, _resolve_deepseek_provider


class _StubDeepSeek(DeepSeekProvider):
    """Avoids network; records FIM calls."""

    def __init__(self) -> None:
        super().__init__(
            api_key="sk-test",
            base_url="https://api.invalid.test",
            default_model="deepseek-v4-pro",
            timeout=5.0,
            max_retries=0,
        )
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fim_complete(  # type: ignore[override]
        self,
        prompt: str,
        suffix: str,
        *,
        model: str = "deepseek-v4-pro",
        max_tokens: int = 128,
        temperature: float = 1.0,
    ) -> str:
        self.calls.append((prompt, suffix, {"model": model, "max_tokens": max_tokens, "temperature": temperature}))
        return f"INFILL({len(prompt)},{len(suffix)})"


def _service_with_deepseek(stub: _StubDeepSeek) -> LLMService:
    reg = ProviderRegistry()
    reg.register("deepseek", stub)
    return LLMService(registry=reg, model_registry=ModelRegistry())


@pytest.mark.asyncio
async def test_resolve_deepseek_from_llm_service() -> None:
    stub = _StubDeepSeek()
    llm = _service_with_deepseek(stub)
    assert _resolve_deepseek_provider(llm) is stub


@pytest.mark.asyncio
async def test_fim_infill_inline() -> None:
    stub = _StubDeepSeek()
    llm = _service_with_deepseek(stub)
    tool = DeepSeekFimTool()
    ctx = ToolContext(user_id="u", session_id="sess-1", llm=llm)
    out = await tool.execute(
        {
            "action": "infill",
            "prefix": "def foo():\n    ",
            "suffix": "\n    return 1\n",
            "max_tokens": 64,
            "temperature": 0.1,
        },
        ctx,
    )
    assert out["ok"] is True
    assert "INFILL" in out["infill"]
    assert len(stub.calls) == 1
    assert stub.calls[0][0] == "def foo():\n    "
    assert stub.calls[0][1] == "\n    return 1\n"


@pytest.mark.asyncio
async def test_fim_buffer_protocol() -> None:
    stub = _StubDeepSeek()
    llm = _service_with_deepseek(stub)
    tool = DeepSeekFimTool()
    ctx = ToolContext(user_id="u", session_id="sess-2", llm=llm)

    up = await tool.execute(
        {
            "action": "buffer_upsert",
            "buffer_id": "buf_a",
            "prefix": "A",
            "suffix": "B",
            "path": "/tmp/x.py",
        },
        ctx,
    )
    assert up["ok"] is True

    got = await tool.execute({"action": "buffer_get", "buffer_id": "buf_a"}, ctx)
    assert got["exists"] is True
    assert got["prefix_chars"] == 1
    assert got["suffix_chars"] == 1

    inf = await tool.execute(
        {"action": "infill", "buffer_id": "buf_a", "use_buffer": True},
        ctx,
    )
    assert inf["ok"] is True
    assert stub.calls[-1][0] == "A" and stub.calls[-1][1] == "B"

    clr = await tool.execute({"action": "buffer_clear", "buffer_id": "buf_a"}, ctx)
    assert clr["cleared"] is True


@pytest.mark.asyncio
async def test_fim_no_deepseek_returns_structured_error() -> None:
    reg = ProviderRegistry()
    from leagent.llm.providers.openai import OpenAIProvider

    reg.register("openai", OpenAIProvider(api_key="k", base_url="https://x", default_model="gpt-4o-mini"))
    llm = LLMService(registry=reg, model_registry=ModelRegistry())
    tool = DeepSeekFimTool()
    ctx = ToolContext(user_id="u", session_id="s", llm=llm)
    out = await tool.execute(
        {"action": "infill", "prefix": "a", "suffix": "b"},
        ctx,
    )
    assert out.get("ok") is False
    assert "error" in out


@pytest.mark.asyncio
async def test_fim_run_coerces_failure_envelope() -> None:
    reg = ProviderRegistry()
    from leagent.llm.providers.openai import OpenAIProvider

    reg.register("openai", OpenAIProvider(api_key="k", base_url="https://x", default_model="gpt-4o-mini"))
    llm = LLMService(registry=reg, model_registry=ModelRegistry())
    tool = DeepSeekFimTool()
    ctx = ToolContext(user_id="u", session_id="s", llm=llm)
    res = await tool.run({"action": "infill", "prefix": "a", "suffix": "b"}, ctx)
    assert res.success is False
    assert isinstance(res.data, dict)
