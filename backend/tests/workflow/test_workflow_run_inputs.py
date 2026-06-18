"""Workflow-level inputs must reach generation nodes (TPL-IMG-01)."""

from __future__ import annotations

import pytest

from leagent.bootstrap.tools import bootstrap_tools
from leagent.tools.executor import ToolExecutor
from leagent.tools.registry import get_registry
from leagent.workflow.engine.caching import build_cache_set
from leagent.workflow.engine.executor import WorkflowExecutor
from leagent.workflow.io import load
from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.template_service import TemplateService


@pytest.fixture
async def workflow_executor_with_tools():
    await bootstrap_tools()
    await bootstrap_nodes()
    reg = get_registry()
    return WorkflowExecutor(
        tool_registry=reg,
        tool_executor=ToolExecutor(registry=reg, service_manager=None),
        cache_set=build_cache_set("none"),
    )


@pytest.mark.asyncio
async def test_tpl_img01_run_panel_prompt_reaches_image_gen(
    workflow_executor_with_tools: WorkflowExecutor,
    monkeypatch: pytest.MonkeyPatch,
):
    """Custom ``input_data.prompt`` is resolved into Art.ImageGen's generation call."""
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    svc = TemplateService()
    svc.load()
    raw = svc.get_template("TPL-IMG-01")
    assert raw is not None
    doc = load(raw)

    captured: list[str] = []

    from leagent.llm.generation import service as gen_svc

    orig_generate = gen_svc.GenerationService.generate

    async def capture_generate(self, *, kind, prompt, provider=None, max_retries=0, **params):
        if kind == "image":
            captured.append(str(prompt))
        return await orig_generate(
            self, kind=kind, prompt=prompt, provider=provider, max_retries=max_retries, **params
        )

    monkeypatch.setattr(gen_svc.GenerationService, "generate", capture_generate)

    custom = "CUSTOM_RUN_PANEL_PROMPT_XYZZY"
    result = await workflow_executor_with_tools.execute(
        doc,
        inputs={"prompt": custom, "style": "pixel_art"},
    )

    assert result.success, result.errors
    assert captured, "expected at least one image generation call"
    assert any(custom in p for p in captured), captured
