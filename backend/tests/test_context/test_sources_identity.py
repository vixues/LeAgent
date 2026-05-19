from __future__ import annotations

import pytest

from leagent.context.sources.base import ResolveContext
from leagent.context.sources.identity import IdentitySource
from leagent.context.sources.capabilities import CapabilitiesSource
from leagent.context.sources.environment import EnvironmentSource
from leagent.context.types import RenderTarget


class _MockVariant:
    body = "You are Agent X."
    key = "test:default"
    policies: list[str] = []
    layers = ["persona"]
    budget_chars: dict[str, int] = {}
    tags: list[str] = []


class _MockRegistry:
    def get(self, variant, template_variant="default"):
        return _MockVariant()


class _MockTool:
    name = "read_file"
    description = "Read a file"
    category = "util"
    is_read_only = True


class _MockToolRegistry:
    def get_enabled_tools(self):
        return [_MockTool()]

    def get_tools_for_llm(self, **kw):
        return []


@pytest.mark.asyncio
async def test_identity_resolves_from_registry():
    ctx = ResolveContext(
        prompt_registry=_MockRegistry(),
        variant="test",
        template_variant="default",
    )
    block = await IdentitySource().resolve(ctx)
    assert block is not None
    assert "Agent X" in block.body


@pytest.mark.asyncio
async def test_identity_persona_override():
    ctx = ResolveContext(
        persona_override="Custom persona.",
        prompt_registry=_MockRegistry(),
    )
    block = await IdentitySource().resolve(ctx)
    assert block is not None
    assert "Custom persona." in block.body


@pytest.mark.asyncio
async def test_capabilities_lists_tools():
    ctx = ResolveContext(tools=_MockToolRegistry())
    block = await CapabilitiesSource().resolve(ctx)
    assert block is not None
    assert "read_file" in block.body


@pytest.mark.asyncio
async def test_environment_returns_xml():
    ctx = ResolveContext(cwd="/tmp/test")
    block = await EnvironmentSource().resolve(ctx)
    assert block is not None
    assert "<environment>" in block.body
    assert "<cwd>" in block.body
    assert block.render_target == RenderTarget.SYSTEM
