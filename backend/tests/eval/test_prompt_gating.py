"""Relevance-gated policy sources — canvas_guide, document_fonts, and email_tool.

Asserts the gated sources are registered, inject their (existing) policy
markdown only for relevant turns, stay silent for irrelevant turns even when
all tools are enabled, and honour the runtime-harness opt-in levers
(``template_vars`` keys and ``workflow_hint``).
"""

from __future__ import annotations

import pytest

from leagent.context.sources import get_all_sources
from leagent.context.sources.base import ResolveContext
from leagent.prompts.registry import PromptRegistry


def _registry() -> PromptRegistry:
    return PromptRegistry()


# -- registration -----------------------------------------------------------


def test_gated_sources_registered():
    sources = get_all_sources()
    assert "canvas_guide" in sources
    assert "document_fonts" in sources
    assert "document_generation" in sources
    assert "email_tool" in sources


def test_default_agent_keeps_email_policy_gated():
    body = _registry().get("default_agent", variant="default").body
    assert "get_config" not in body
    assert "LEAGENT_SMTP" not in body


# -- canvas_guide gating ----------------------------------------------------


@pytest.mark.asyncio
async def test_canvas_guide_injects_for_visual_query():
    src = get_all_sources()["canvas_guide"]()
    block = await src.resolve(
        ResolveContext(
            query="build me a KPI dashboard with charts",
            prompt_registry=_registry(),
        )
    )
    assert block is not None
    # The canvas policy group is concatenated into the block.
    assert "canvas" in block.body.lower()
    assert block.metadata.get("gated") is True


@pytest.mark.asyncio
async def test_canvas_guide_silent_for_non_visual_query():
    from leagent.tools.registry import get_registry

    src = get_all_sources()["canvas_guide"]()
    # Irrelevant query stays silent even with all tools registered globally.
    block = await src.resolve(
        ResolveContext(
            query="summarise this PDF document",
            prompt_registry=_registry(),
            tools=get_registry(),
        )
    )
    assert block is None


@pytest.mark.asyncio
async def test_canvas_guide_honours_opt_in_and_workflow_hint():
    src = get_all_sources()["canvas_guide"]()
    by_optin = await src.resolve(
        ResolveContext(
            query="hello",
            prompt_registry=_registry(),
            template_vars={"canvas_guide": True},
        )
    )
    assert by_optin is not None

    by_hint = await src.resolve(
        ResolveContext(
            query="hello",
            prompt_registry=_registry(),
            workflow_hint="render a dashboard poster",
        )
    )
    assert by_hint is not None


# -- document_fonts gating --------------------------------------------------


@pytest.mark.asyncio
async def test_document_fonts_injects_for_doc_query():
    src = get_all_sources()["document_fonts"]()
    block = await src.resolve(
        ResolveContext(
            query="generate a PDF report in Chinese",
            prompt_registry=_registry(),
        )
    )
    assert block is not None
    assert "font" in block.body.lower()


@pytest.mark.asyncio
async def test_document_fonts_silent_for_unrelated_query():
    src = get_all_sources()["document_fonts"]()
    block = await src.resolve(
        ResolveContext(
            query="what's the weather today?",
            prompt_registry=_registry(),
        )
    )
    assert block is None


@pytest.mark.asyncio
async def test_document_fonts_opt_in():
    src = get_all_sources()["document_fonts"]()
    block = await src.resolve(
        ResolveContext(
            query="hello",
            prompt_registry=_registry(),
            template_vars={"enable_fonts": True},
        )
    )
    assert block is not None


# -- document_generation gating ----------------------------------------------


@pytest.mark.asyncio
async def test_document_generation_injects_for_report_query():
    src = get_all_sources()["document_generation"]()
    block = await src.resolve(
        ResolveContext(
            query="写一份季度经营分析报告并导出 PDF",
            prompt_registry=_registry(),
        )
    )
    assert block is not None
    assert "document_generate" in block.body
    assert block.metadata.get("gated") is True


@pytest.mark.asyncio
async def test_document_generation_silent_for_unrelated_query():
    src = get_all_sources()["document_generation"]()
    block = await src.resolve(
        ResolveContext(
            query="what's the weather today?",
            prompt_registry=_registry(),
        )
    )
    assert block is None


@pytest.mark.asyncio
async def test_document_generation_opt_in():
    src = get_all_sources()["document_generation"]()
    block = await src.resolve(
        ResolveContext(
            query="hello",
            prompt_registry=_registry(),
            template_vars={"enable_docgen": True},
        )
    )
    assert block is not None


# -- email_tool gating ------------------------------------------------------


@pytest.mark.asyncio
async def test_email_tool_injects_for_mail_settings_query():
    src = get_all_sources()["email_tool"]()
    block = await src.resolve(
        ResolveContext(
            query="查看当前邮件配置和 SMTP 设置",
            prompt_registry=_registry(),
        )
    )
    assert block is not None
    assert "email_send" in block.body
    assert block.metadata.get("gated") is True


@pytest.mark.asyncio
async def test_email_tool_silent_for_unrelated_query():
    src = get_all_sources()["email_tool"]()
    block = await src.resolve(
        ResolveContext(
            query="summarise this PDF document",
            prompt_registry=_registry(),
        )
    )
    assert block is None


@pytest.mark.asyncio
async def test_email_tool_opt_in():
    src = get_all_sources()["email_tool"]()
    block = await src.resolve(
        ResolveContext(
            query="hello",
            prompt_registry=_registry(),
            template_vars={"email_tool": True},
        )
    )
    assert block is not None
