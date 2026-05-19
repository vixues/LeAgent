from __future__ import annotations

import pytest
from pathlib import Path

from leagent.context.sources.base import ResolveContext
from leagent.context.sources.project_memory import ProjectMemorySource


@pytest.fixture
def project_dir(tmp_path):
    (tmp_path / "AGENTS.md").write_text("Project instructions.", encoding="utf-8")
    inner = tmp_path / "leagent"
    inner.mkdir(parents=True, exist_ok=True)
    (inner / "AGENTS.md").write_text("Internal dev docs.", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_denylist_blocks_leagent_agents_md(project_dir):
    ctx = ResolveContext(
        cwd=str(project_dir),
        project_memory_denylist=["**/leagent/AGENTS.md"],
        project_memory_allowlist=[],
        respect_git_boundary=False,
    )
    block = await ProjectMemorySource().resolve(ctx)
    if block is not None:
        assert "Internal dev docs." not in block.body


@pytest.mark.asyncio
async def test_non_denied_agents_md_included(project_dir):
    ctx = ResolveContext(
        cwd=str(project_dir),
        project_memory_denylist=["**/leagent/AGENTS.md"],
        project_memory_allowlist=[],
        respect_git_boundary=False,
    )
    block = await ProjectMemorySource().resolve(ctx)
    assert block is not None
    assert "Project instructions." in block.body
