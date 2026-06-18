"""Tests for workflow agent-node model overrides."""

from __future__ import annotations

from leagent.runtime import AgentBuilder
from leagent.workflow.nodes.agent_model import (
    apply_model_override,
    parse_agent_model_override,
)


def test_parse_agent_model_override_empty_uses_default() -> None:
    assert parse_agent_model_override(None) is None
    assert parse_agent_model_override("") is None
    assert parse_agent_model_override("auto") is None
    assert parse_agent_model_override("  ") is None


def test_parse_agent_model_override_provider_slash_model() -> None:
    assert parse_agent_model_override("deepseek/deepseek-chat") == (
        "deepseek",
        "deepseek-chat",
    )


def test_apply_model_override_updates_definition() -> None:
    definition = AgentBuilder("x").build()
    updated = apply_model_override(definition, "openai/gpt-4o-mini")
    assert updated.model.provider == "openai"
    assert updated.model.model == "gpt-4o-mini"
