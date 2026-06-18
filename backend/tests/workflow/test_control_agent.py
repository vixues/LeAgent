"""Tests for Control Agent workflow node and prompt composer."""

from __future__ import annotations

import pytest

from leagent.prompts.control_agent import (
    compose_control_messages,
    try_parse_json_payload,
)
from leagent.workflow.base import WorkflowState
from leagent.workflow.io import HiddenHolder
from leagent.workflow.nodes.builtin.control_agent import ControlAgentNode


def test_compose_control_messages_prompt_generate_mode() -> None:
    state = WorkflowState(
        workflow_id="wf",
        inputs={"prompt": "female warrior, cel-shaded"},
    )
    system, user = compose_control_messages(
        mode="prompt_generate",
        instruction="",
        system_template="",
        context_template="",
        output_contract="",
        examples="",
        context=None,
        state=state,
        target="Art.ImageGen",
    )
    assert "Control Agent" in system
    assert "female warrior" in user
    assert "Output contract" in user


def test_try_parse_json_payload_fenced() -> None:
    raw = 'Here you go:\n```json\n{"prompt":"hello","tags":["a"]}\n```'
    parsed = try_parse_json_payload(raw)
    assert parsed == {"prompt": "hello", "tags": ["a"]}


@pytest.mark.asyncio
async def test_control_agent_single_shot_llm() -> None:
    state = WorkflowState(workflow_id="wf", inputs={"brief": "sunset city"})

    class _FakeLLM:
        async def complete(self, messages, **kwargs):
            from types import SimpleNamespace

            assert messages[0].role == "system"
            assert "sunset city" in messages[1].content or "Instruction" in messages[1].content
            assert kwargs.get("provider") == "openai"
            assert kwargs.get("model") == "gpt-4o-mini"
            return SimpleNamespace(content='{"prompt":"neon sunset skyline"}')

    class _Ctx:
        llm_service = _FakeLLM()

    node = ControlAgentNode()
    out = await node.execute(
        hidden=HiddenHolder(
            unique_id="ctrl-1",
            workflow_state=state,
            tool_context=_Ctx(),
        ),
        mode="prompt_generate",
        instruction="Brief: ${input.brief}",
        model="openai/gpt-4o-mini",
        response_format="json",
        apply_to_state=True,
    )
    assert out.error is None
    text, data, success = out.as_tuple()
    assert success is True
    assert data["prompt"] == "neon sunset skyline"
    assert state.get("prompt") == "neon sunset skyline"
    assert out.metadata.get("single_shot") is True
