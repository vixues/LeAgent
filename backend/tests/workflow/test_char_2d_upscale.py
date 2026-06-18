"""TPL-CHAR-2D-01 upscale path and editor control round-trip."""

from __future__ import annotations

import pytest

from leagent.bootstrap.tools import bootstrap_tools
from leagent.tools.executor import ToolExecutor
from leagent.tools.registry import get_registry
from leagent.workflow.base import WorkflowStatus
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
async def test_char_2d_template_upscale_completes(
    workflow_executor_with_tools: WorkflowExecutor,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    svc = TemplateService()
    svc.load()
    doc = load(svc.get_template("TPL-CHAR-2D-01"))
    assert doc is not None

    result = await workflow_executor_with_tools.execute(
        doc,
        inputs={"character_name": "TestHero", "prompt": "armored ranger with green cloak"},
    )

    assert result.status == WorkflowStatus.COMPLETED, result.errors
    assert not result.errors

    upscale_runs = [h for h in result.execution_history if h.node_id == "upscale"]
    assert upscale_runs, "expected Production Upscale to run"
    assert upscale_runs[-1].status == WorkflowStatus.COMPLETED
    assert upscale_runs[-1].error is None

    preview_runs = [h for h in result.execution_history if h.node_id == "preview"]
    assert preview_runs and preview_runs[-1].status == WorkflowStatus.COMPLETED

    concept_runs = [h for h in result.execution_history if h.node_id == "concept"]
    assert len(concept_runs) >= 2, "refine loop should re-run concept at least twice"
    file_ids = {
        h.metadata.get("file_id")
        for h in concept_runs
        if h.metadata.get("file_id")
    }
    assert len(file_ids) >= 2, "each concept pass should register a distinct file"
    refine_iters = [h.metadata.get("refine_iteration") for h in concept_runs if h.metadata]
    assert 0 in refine_iters and any(i and i > 0 for i in refine_iters if i is not None)


@pytest.mark.asyncio
async def test_char_2d_upscale_fails_without_source_image(
    workflow_executor_with_tools: WorkflowExecutor,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    svc = TemplateService()
    svc.load()
    raw = svc.get_template("TPL-CHAR-2D-01")
    assert raw is not None
    # Wire upscale to the gate score slot (float) instead of the asset — passes
    # static validation but resolves to no MediaRef at runtime (broken editor save).
    raw["nodes"]["upscale"]["inputs"]["image"] = ["gate", 0]
    doc = load(raw)

    result = await workflow_executor_with_tools.execute(
        doc,
        inputs={"character_name": "TestHero", "prompt": "armored ranger"},
    )

    upscale_runs = [h for h in result.execution_history if h.node_id == "upscale"]
    assert upscale_runs
    assert upscale_runs[-1].status == WorkflowStatus.FAILED
    assert upscale_runs[-1].error and "missing source image" in upscale_runs[-1].error.lower()


@pytest.mark.asyncio
async def test_char_2d_refine_loop_requires_gate_control(
    workflow_executor_with_tools: WorkflowExecutor,
    monkeypatch: pytest.MonkeyPatch,
):
    """Without per-node control (editor-save bug), the refine loop never runs."""
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    svc = TemplateService()
    svc.load()
    raw = svc.get_template("TPL-CHAR-2D-01")
    assert raw is not None
    raw["nodes"]["gate"].pop("control", None)
    raw["nodes"]["refine"].pop("control", None)
    doc = load(raw)

    result = await workflow_executor_with_tools.execute(doc, inputs={})
    refine_runs = [h for h in result.execution_history if h.node_id == "refine"]
    assert not refine_runs


@pytest.mark.asyncio
async def test_char_2d_refine_loop_runs_with_gate_control(
    workflow_executor_with_tools: WorkflowExecutor,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    svc = TemplateService()
    svc.load()
    doc = load(svc.get_template("TPL-CHAR-2D-01"))

    result = await workflow_executor_with_tools.execute(doc, inputs={})
    refine_runs = [h for h in result.execution_history if h.node_id == "refine"]
    assert refine_runs
