"""Every curated YAML template runs to completion with empty caller inputs."""

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


CORE_TEMPLATE_IDS = tuple(f"TPL-{i:02d}" for i in range(1, 11))


def _all_template_ids() -> list[str]:
    """Return every YAML template id shipped in config/workflows/templates."""
    svc = TemplateService()
    svc.load()
    return sorted({info["id"] for info in svc.list_templates()})


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
async def test_template_catalog_contains_core_ids(workflow_executor_with_tools):
    del workflow_executor_with_tools  # noqa: ARG001
    svc = TemplateService()
    svc.load()
    ids = {info["id"] for info in svc.list_templates()}
    # The curated core TPL-01..TPL-10 must always be present; additional
    # domain templates (TPL-ART-01, TPL-GAME-ENGINE, ...) may be shipped too.
    assert set(CORE_TEMPLATE_IDS).issubset(ids), sorted(ids)
    assert "TPL-ART-01" in ids


@pytest.mark.parametrize("template_id", _all_template_ids())
@pytest.mark.asyncio
async def test_each_template_executes_with_empty_inputs(
    workflow_executor_with_tools: WorkflowExecutor,
    template_id: str,
):
    svc = TemplateService()
    svc.load()
    raw = svc.get_template(template_id)
    assert raw is not None, template_id
    doc = load(raw)
    result = await workflow_executor_with_tools.execute(doc, inputs={})
    assert result.status == WorkflowStatus.COMPLETED, (template_id, result.errors)
    assert not result.errors, template_id


@pytest.mark.asyncio
async def test_flagship_art_template_self_corrects_offline(
    workflow_executor_with_tools: WorkflowExecutor,
    monkeypatch: pytest.MonkeyPatch,
):
    """TPL-ART-01 runs the full self-correction loop end-to-end, offline.

    The deterministic offline backend is forced so the run is hermetic and
    credential-free; the quality gate fails the first concept image, the
    bounded IterativeRefine back-edge regenerates, the second image passes,
    and AssetExport collates image + video + 3D mesh into a manifest.
    """
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    svc = TemplateService()
    svc.load()
    raw = svc.get_template("TPL-ART-01")
    assert raw is not None
    doc = load(raw)

    result = await workflow_executor_with_tools.execute(doc, inputs={})

    assert result.status == WorkflowStatus.COMPLETED, result.errors
    assert not result.errors

    # The self-correction loop ran: image was generated more than once.
    image_runs = [h for h in result.execution_history if h.node_id == "image"]
    assert len(image_runs) >= 2, "expected the refine loop to regenerate the image"

    # The gate ultimately passed above the 0.7 bar.
    assert float(result.outputs["quality_score"]) >= 0.7

    # AssetExport produced an engine-ready manifest with all three asset kinds.
    manifest = result.outputs["manifest"]
    assert manifest["asset_count"] == 3
    kinds = {a["kind"] for a in manifest["assets"]}
    assert kinds == {"image", "video", "model3d"}
