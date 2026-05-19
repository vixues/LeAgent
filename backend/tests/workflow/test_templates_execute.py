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


EXPECTED_TEMPLATE_IDS = tuple(f"TPL-{i:02d}" for i in range(1, 11))


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
async def test_template_catalog_has_ten_ids(workflow_executor_with_tools):
    del workflow_executor_with_tools  # noqa: ARG001
    svc = TemplateService()
    svc.load()
    ids = sorted(info["id"] for info in svc.list_templates())
    assert ids == list(EXPECTED_TEMPLATE_IDS)


@pytest.mark.parametrize("template_id", EXPECTED_TEMPLATE_IDS)
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
