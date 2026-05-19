"""Live integration test: DeepSeek + ``QueryEngine`` + Excel fixture.

Gated behind ``DEEPSEEK_API_KEY`` — the test is skipped automatically
on CI / dev machines without a key. Pass ``-m integration`` (or the
``--run-live`` opt-in) to run it explicitly.

The test drives one end-to-end turn:

1. Build a real ``LLMService`` wired to ``DeepSeekProvider``.
2. Bootstrap the standard tool registry (so ``excel_reader`` /
   ``code_execution`` / ``file_manager`` are all available).
3. Construct a ``QueryEngine`` with a tailored Excel-analysis system
   prompt (loaded inline here — the engine itself never hardcodes
   prompts).
4. Submit the fixture workbook path + a free-form question and
   collect the streaming SDK messages.

We then assert the model used at least one tool call AND produced a
final assistant message that mentions at least one of the ground-truth
answers baked into the fixture manifest. The assertions are loose on
purpose — LLM output is non-deterministic and we don't want CI to
bounce on cosmetic phrasing.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("DEEPSEEK_API_KEY"),
        reason="DEEPSEEK_API_KEY not set; live DeepSeek integration test skipped.",
    ),
]


# ---------------------------------------------------------------------------
# Prompt — supplied by the caller per the script_agent module contract.
# ---------------------------------------------------------------------------


EXCEL_ANALYSIS_SYSTEM_PROMPT = """\
You are a data-analysis agent. You have been given the absolute path
to an Excel workbook (``.xlsx``) and a user question about its
contents.

Operating rules:

1. Always read the file before answering. Use the ``excel_reader``
   tool first to list sheets, then read the relevant sheet(s).
2. If the question requires computation the tool doesn't give you
   directly (sums, averages, ratios, sorting), write and run a
   short Python snippet via the ``code_execution`` tool.
3. Cite the sheet name and the concrete cells / columns behind
   every numeric claim.
4. When you have enough data, stop calling tools and produce a
   concise, well-formatted final answer (plain prose; use bullet
   lists only when they genuinely help).

Never fabricate figures. If the workbook doesn't contain the
information needed, say so explicitly.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_llm_service():
    """Construct a real ``LLMService`` backed by ``DeepSeekProvider``."""
    from leagent.llm.providers.deepseek import DeepSeekProvider
    from leagent.llm.registry import ProviderRegistry
    from leagent.llm.router import ModelRouter, TierConfig
    from leagent.llm.service import LLMService

    api_key = os.environ["DEEPSEEK_API_KEY"]
    base_url = os.getenv("DEEPSEEK_BASE_URL", DeepSeekProvider.DEFAULT_BASE_URL)
    model = os.getenv("DEEPSEEK_MODEL", DeepSeekProvider.DEFAULT_MODEL)

    registry = ProviderRegistry()
    # Register the same provider under its canonical name and both tier
    # aliases so the router + QueryEngine both find it.
    for name in ("deepseek", "tier1", "tier2"):
        registry.register(
            name,
            DeepSeekProvider(api_key=api_key, base_url=base_url, default_model=model),
            metadata={"tier": name, "vendor": "deepseek", "model": model},
        )

    router = ModelRouter(
        registry=registry,
        tier_configs={
            "tier1": TierConfig(provider="tier1", model=model, temperature=0.1),
            "tier2": TierConfig(provider="tier2", model=model, temperature=0.1),
        },
    )
    return LLMService(registry=registry, router=router)


def _build_registry():
    from leagent.bootstrap.tools import register_default_tools
    from leagent.tools.registry import ToolRegistry

    registry = ToolRegistry()
    register_default_tools(registry=registry)
    return registry


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_analyses_excel(excel_analysis_manifest) -> None:  # type: ignore[no-untyped-def]
    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
    from leagent.tools.executor import ToolExecutor

    manifest = excel_analysis_manifest
    llm = _build_llm_service()
    registry = _build_registry()
    executor = ToolExecutor(registry=registry, service_manager=None)

    engine = QueryEngine(
        QueryEngineConfig(
            cwd=str(manifest.path.parent),
            llm=llm,
            tools=registry,
            executor=executor,
            system_prompt=EXCEL_ANALYSIS_SYSTEM_PROMPT,
            model_tier="tier1",
            temperature=0.1,
            max_turns=8,
            max_tool_calls_per_turn=4,
            agent_id="integration/deepseek_excel",
        )
    )

    user_prompt = (
        f"The workbook is at {manifest.path}. "
        f"It has sheets {list(manifest.sheets)}. "
        "What was the total 2024 revenue, which region performed best, "
        "and which single product has the highest unit price?"
    )

    tool_uses: list[str] = []
    tool_results: list[str] = []
    assistant_chunks: list[str] = []
    final_reason: str | None = None

    async def _drive() -> None:
        nonlocal final_reason
        async for msg in engine.submit_message(user_prompt):
            if msg.type == "tool_use":
                tool_uses.append(str(msg.data.get("name")))
            elif msg.type == "tool_result":
                content = str(msg.data.get("content", ""))
                tool_results.append(content)
            elif msg.type == "stream_delta":
                assistant_chunks.append(str(msg.data.get("content", "")))
            elif msg.type == "assistant":
                if content := msg.data.get("content"):
                    assistant_chunks.append(str(content))
            elif msg.type == "result":
                final_reason = str(msg.data.get("reason"))

    # 3-minute ceiling — DeepSeek streaming is usually well under that,
    # but network + tool dispatch can spike.
    await asyncio.wait_for(_drive(), timeout=180.0)

    # -- Process-level assertions ---------------------------------------
    assert final_reason == "completed", (
        f"QueryEngine did not finish cleanly: reason={final_reason}, "
        f"tool_uses={tool_uses}"
    )
    assert tool_uses, "Agent never called a tool — expected at least excel_reader."
    # We don't pin to a specific tool name (the model might pick
    # ``code_execution`` directly if it prefers) — just verify the
    # Excel path did end up in at least one tool result.
    joined_results = "\n".join(tool_results)
    assert str(manifest.path) in joined_results or "Sales" in joined_results

    # -- Answer-content assertions (loose, case-insensitive) ------------
    final = "".join(assistant_chunks).lower()
    assert final.strip(), "Assistant returned an empty final answer."

    # Total revenue: allow the model to format as ``6,819,000`` / ``6.82M`` etc.
    total = manifest.total_revenue
    total_variants = {
        str(total),
        f"{total:,}",
        f"{total/1_000_000:.2f}m",
        f"{total/1_000_000:.1f}m",
    }
    assert any(v.lower() in final for v in total_variants), (
        f"Expected one of {total_variants} in final answer, got: {final[:500]!r}"
    )
    assert manifest.best_region.lower() in final
    assert manifest.top_product.lower().split()[0] in final  # first token is enough
