"""Tests for :class:`ContextManager.prepare_turn`."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.context import ContextManager
from leagent.context.types import RenderTarget


class _MockVariant:
    body = "You are test agent."
    key = "test:default"
    policies: list[str] = []
    layers = ["persona"]
    budget_chars: dict[str, int] = {}
    tags: list[str] = []


class _MockRegistry:
    def get(self, variant: str, template_variant: str = "default") -> _MockVariant:
        return _MockVariant()


@pytest.mark.asyncio
async def test_prepare_turn_returns_turn_context() -> None:
    mgr = ContextManager(
        cwd=".",
        prompt_registry=_MockRegistry(),
        variant="default_agent",
    )
    turn = await mgr.prepare_turn("hello", task_id=uuid4())
    assert turn.built_prompt.system_text
    assert turn.ledger is not None
    assert isinstance(turn.attachment_messages, list)


@pytest.mark.asyncio
async def test_prepare_turn_system_text_contains_persona() -> None:
    mgr = ContextManager(
        cwd=".",
        prompt_registry=_MockRegistry(),
        variant="default_agent",
    )
    turn = await mgr.prepare_turn("hello", task_id=uuid4())
    assert "test agent" in turn.built_prompt.system_text


@pytest.mark.asyncio
async def test_clone_produces_independent_file_state() -> None:
    mgr = ContextManager(
        cwd=".",
        prompt_registry=_MockRegistry(),
    )
    child = mgr.clone()
    assert child.file_state is not mgr.file_state


@pytest.mark.asyncio
async def test_environment_snapshot_available() -> None:
    mgr = ContextManager(
        cwd=".",
        prompt_registry=_MockRegistry(),
    )
    turn = await mgr.prepare_turn("hello", task_id=uuid4())
    assert turn.environment is not None
    assert turn.environment.cwd == "."
