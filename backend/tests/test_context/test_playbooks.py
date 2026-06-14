"""Tests for runtime playbook attachment."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.context import ContextManager
from leagent.prompts.playbooks import (
    playbook_ids_from_context,
    playbook_ids_from_message_extensions,
)
from leagent.prompts.registry import get_prompt_registry


def test_playbook_ids_from_context_dedupes() -> None:
    ids = playbook_ids_from_context(
        playbook_ids=["data_analysis"],
        tool_extra={"playbook_id": "document_editing"},
        metadata={"playbook_ids": ["data_analysis", "game_engine"]},
    )
    assert ids == ["data_analysis", "document_editing", "game_engine"]


def test_playbook_ids_from_message_extensions() -> None:
    ids = playbook_ids_from_message_extensions(
        {"playbook_id": "copywriting_design", "chat_workflow": {}},
    )
    assert ids == ["copywriting_design"]


@pytest.mark.asyncio
async def test_prepare_turn_includes_playbook_when_requested() -> None:
    registry = get_prompt_registry(refresh=True)
    mgr = ContextManager(
        variant="default_agent",
        template_variant="default",
        prompt_registry=registry,
    )
    turn = await mgr.prepare_turn(
        "profile this csv",
        task_id=uuid4(),
        playbook_ids=["data_analysis"],
    )
    assert "Data Analysis playbook" in turn.built_prompt.system_text


@pytest.mark.asyncio
async def test_prepare_turn_omits_playbook_without_ids() -> None:
    registry = get_prompt_registry(refresh=True)
    mgr = ContextManager(
        variant="default_agent",
        template_variant="default",
        prompt_registry=registry,
    )
    turn = await mgr.prepare_turn("hello", task_id=uuid4())
    assert "Data Analysis playbook" not in turn.built_prompt.system_text
