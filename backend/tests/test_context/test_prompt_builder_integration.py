from __future__ import annotations

import pytest
from uuid import uuid4

from leagent.context import ContextManager
from leagent.context.types import RenderTarget


class _MockVariant:
    body = "You are test agent."
    key = "default_agent:default"
    policies: list[str] = []
    layers = ["persona"]
    budget_chars: dict[str, int] = {}
    tags: list[str] = []


class _MockRegistry:
    def get(self, variant, template_variant="default"):
        return _MockVariant()


class _Settings:
    project_memory_denylist = ["**/leagent/AGENTS.md", "**/backend/AGENTS.md"]
    project_memory_allowlist: list[str] = []
    respect_git_boundary = False
    file_state_max_entries = 64
    file_state_max_tokens = 16000
    working_set_excerpt_head_lines = 20
    working_set_excerpt_tail_lines = 10
    recall_attachment_limit = 5
    tool_history_attachment_limit = 5
    recent_reads_attachment_limit = 5
    freshness_half_life_seconds = 300.0


@pytest.fixture
def ctx_manager(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Project rules here.")
    inner = tmp_path / "leagent"
    inner.mkdir()
    (inner / "AGENTS.md").write_text("SECRET INTERNAL DOCS")
    return ContextManager(
        cwd=str(tmp_path),
        prompt_registry=_MockRegistry(),
        variant="default_agent",
        settings=_Settings(),
    )


@pytest.mark.asyncio
async def test_agents_md_never_in_system_text(ctx_manager):
    turn = await ctx_manager.prepare_turn("hello", task_id=uuid4())
    assert "SECRET INTERNAL DOCS" not in turn.built_prompt.system_text
    assert "Project rules here." in turn.built_prompt.system_text


@pytest.mark.asyncio
async def test_recall_renders_as_attachment_not_system(ctx_manager):
    turn = await ctx_manager.prepare_turn("hello", task_id=uuid4())
    for att in turn.attachment_messages:
        assert att["role"] == "user"
        assert "attachment" in str(att.get("metadata", {}))


@pytest.mark.asyncio
async def test_stable_hash_survives_recall_change(ctx_manager):
    t1 = await ctx_manager.prepare_turn("query1", task_id=uuid4())
    t2 = await ctx_manager.prepare_turn("query2", task_id=uuid4())
    assert t1.built_prompt.stable_hash == t2.built_prompt.stable_hash


@pytest.mark.asyncio
async def test_attachment_dedup(ctx_manager):
    t1 = await ctx_manager.prepare_turn("hello", task_id=uuid4())
    t2 = await ctx_manager.prepare_turn("hello", task_id=uuid4())
    assert len(t2.attachment_messages) <= len(t1.attachment_messages)
