"""Smoke tests for domain playbook templates in the chat workflow catalog."""

from __future__ import annotations

import pytest

from leagent.bootstrap.tools import bootstrap_tools
from leagent.chat_workflow.compile import compile_chat_workflow_to_document
from leagent.chat_workflow.schema import parse_chat_workflow_spec
from leagent.chat_workflow.templates import build_chat_workflow_template_catalog
from leagent.tools.registry import get_registry

EXPECTED_PLAYBOOK_IDS = frozenset({
    "document_editing",
    "data_analysis",
    "game_engine",
    "copywriting_design",
})


@pytest.fixture(scope="module")
async def bootstrapped_registry():
    await bootstrap_tools()
    return get_registry()


@pytest.mark.asyncio
async def test_playbook_catalog_has_four_entries(bootstrapped_registry) -> None:
    catalog = build_chat_workflow_template_catalog(bootstrapped_registry)
    playbooks = [row for row in catalog if row.get("category") == "playbook"]
    assert len(playbooks) == 4
    assert {row["playbook_id"] for row in playbooks} == EXPECTED_PLAYBOOK_IDS


@pytest.mark.asyncio
async def test_playbook_templates_compile_to_workflow_documents(
    bootstrapped_registry,
) -> None:
    catalog = build_chat_workflow_template_catalog(bootstrapped_registry)
    playbooks = [row for row in catalog if row.get("category") == "playbook"]

    for row in playbooks:
        spec = parse_chat_workflow_spec(row["spec"], registry=bootstrapped_registry)
        doc = compile_chat_workflow_to_document(spec)
        assert doc["start_id"] == "start"
        assert "end" in doc["nodes"]
        for step in spec.steps:
            assert step.id in doc["nodes"]
            assert doc["nodes"][step.id]["class_type"] == "ToolCallNode"
