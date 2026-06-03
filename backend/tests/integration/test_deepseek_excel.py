"""Optional live DeepSeek test: ``QueryEngine`` + Excel fixture.

Skipped when ``DEEPSEEK_API_KEY`` is unset.

    uv run pytest tests/integration/test_deepseek_excel.py -m live -v
"""

from __future__ import annotations

import pytest

from tests.integration.conftest import drive_query_engine, requires_live_deepseek

pytestmark = [pytest.mark.integration, pytest.mark.live, requires_live_deepseek]


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


@pytest.mark.asyncio
async def test_deepseek_analyses_excel(
    excel_analysis_manifest,  # type: ignore[no-untyped-def]
    deepseek_llm,
    full_tool_registry,
) -> None:
    from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
    from leagent.tools.executor import ToolExecutor

    manifest = excel_analysis_manifest
    llm = deepseek_llm
    registry = full_tool_registry
    executor = ToolExecutor(registry=registry, service_manager=None)

    engine = QueryEngine(
        QueryEngineConfig(
            cwd=str(manifest.path.parent),
            llm=llm,
            tools=registry,
            executor=executor,
            system_prompt=EXCEL_ANALYSIS_SYSTEM_PROMPT,
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

    trace = await drive_query_engine(engine, user_prompt, timeout=180.0)

    # -- Process-level assertions ---------------------------------------
    assert trace.final_reason == "completed", (
        f"QueryEngine did not finish cleanly: reason={trace.final_reason}, "
        f"tool_uses={trace.tool_uses}"
    )
    assert trace.tool_uses, "Agent never called a tool — expected at least excel_reader."
    joined_results = trace.joined_tool_results
    assert str(manifest.path) in joined_results or "Sales" in joined_results

    # -- Answer-content assertions (loose, case-insensitive) ------------
    final = trace.final_text.lower()
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
