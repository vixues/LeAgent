"""Tests for workflow prompt resolution from Start input bags."""

from __future__ import annotations

from leagent.workflow.base import WorkflowState
from leagent.workflow.nodes.prompt_resolve import resolve_node_prompt


def test_resolve_prompt_from_start_input_bag() -> None:
    state = WorkflowState(workflow_id="wf-test", inputs={"prompt": "Summarize the report"})
    bag = dict(state.inputs)
    assert resolve_node_prompt(bag, state) == "Summarize the report"


def test_resolve_prompt_template_with_state() -> None:
    state = WorkflowState(workflow_id="wf-test", inputs={"topic": "widgets"})
    assert resolve_node_prompt("${input.topic}", state) == "widgets"


def test_resolve_prompt_falls_back_to_state_when_bag_empty() -> None:
    state = WorkflowState(workflow_id="wf-test", inputs={"prompt": "from run panel"})
    assert resolve_node_prompt({}, state) == "from run panel"
