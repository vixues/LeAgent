"""Tests for git worktree management + workspace_mode=worktree redirection."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from leagent.project.worktree import (
    WorktreeError,
    WorktreeManager,
    WorktreeRegistry,
    get_worktree_registry,
    is_git_repo,
    reset_worktree_registry,
)

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git binary required",
)


@pytest.fixture(autouse=True)
def _fresh_registry():
    reset_worktree_registry()
    yield
    reset_worktree_registry()


@pytest.fixture()
def git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tiny git repo with one commit; worktrees land under tmp LEAGENT_HOME."""
    monkeypatch.setenv("LEAGENT_HOME", str(tmp_path / "leagent-home"))
    repo = tmp_path / "repo"
    repo.mkdir()

    def run(*args: str) -> None:
        subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True,
            env={"GIT_TERMINAL_PROMPT": "0", "HOME": str(tmp_path), "PATH": __import__("os").environ["PATH"]},
        )

    run("init", "-b", "main")
    run("config", "user.name", "Test")
    run("config", "user.email", "test@example.com")
    (repo / "hello.txt").write_text("hello\n")
    run("add", "-A")
    run("commit", "-m", "init")
    return repo


@pytest.mark.asyncio
async def test_is_git_repo(git_repo: Path, tmp_path: Path):
    assert await is_git_repo(git_repo)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not await is_git_repo(plain)


@pytest.mark.asyncio
async def test_create_worktree_and_diff_flow(git_repo: Path):
    manager = WorktreeManager()
    sid = str(uuid4())
    info = await manager.create(git_repo, sid)

    assert Path(info.worktree_path).is_dir()
    assert info.branch.startswith("leagent/")
    assert info.base_branch == "main"

    # No changes yet.
    stats = await manager.diff_stats(info)
    assert stats == {"files_changed": 0, "additions": 0, "deletions": 0}

    # Make a change inside the worktree only.
    (Path(info.worktree_path) / "feature.py").write_text("print('new')\n")
    stats = await manager.diff_stats(info)
    assert stats["files_changed"] == 1
    assert stats["additions"] == 1

    diff = await manager.diff(info)
    assert "feature.py" in diff
    assert "+print('new')" in diff

    files = await manager.changed_files(info)
    assert files == ["feature.py"]

    # The user's checkout is untouched.
    assert not (git_repo / "feature.py").exists()


@pytest.mark.asyncio
async def test_merge_into_base(git_repo: Path):
    manager = WorktreeManager()
    info = await manager.create(git_repo, str(uuid4()))
    (Path(info.worktree_path) / "merged.txt").write_text("merged\n")

    await manager.merge_into_base(info, message="leagent: test merge")

    assert (git_repo / "merged.txt").read_text() == "merged\n"

    await manager.remove(info)
    assert not Path(info.worktree_path).exists()


@pytest.mark.asyncio
async def test_merge_conflict_aborts(git_repo: Path):
    manager = WorktreeManager()
    info = await manager.create(git_repo, str(uuid4()))

    # Conflicting edits to the same file on both sides.
    (Path(info.worktree_path) / "hello.txt").write_text("worktree version\n")
    (git_repo / "hello.txt").write_text("main version\n")
    subprocess.run(["git", "add", "-A"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@x", "commit", "-m", "main edit"],
        cwd=git_repo, check=True, capture_output=True,
    )

    with pytest.raises(WorktreeError, match="Merge failed"):
        await manager.merge_into_base(info, message="leagent: conflict")

    # Base checkout is left clean after the aborted merge.
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=git_repo,
        check=True, capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""


@pytest.mark.asyncio
async def test_create_rejects_non_git_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEAGENT_HOME", str(tmp_path / "home"))
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    with pytest.raises(WorktreeError, match="not a git repository"):
        await WorktreeManager().create(plain, str(uuid4()))


# ---------------------------------------------------------------------------
# Registry + select_project_root redirection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_registry_resolve_roundtrip(git_repo: Path):
    manager = WorktreeManager()
    sid = str(uuid4())
    info = await manager.create(git_repo, sid)

    registry = WorktreeRegistry()
    registry.register(info)
    assert registry.resolve(sid, git_repo) is info
    assert registry.resolve(str(uuid4()), git_repo) is None
    assert registry.for_session(sid) == [info]

    registry.unregister(sid, info.project_root)
    assert registry.resolve(sid, git_repo) is None


@pytest.mark.asyncio
async def test_select_project_root_redirects_to_worktree(git_repo: Path):
    from leagent.project.fs import select_project_root
    from leagent.tools.base import ToolContext

    manager = WorktreeManager()
    sid = str(uuid4())
    info = await manager.create(git_repo, sid)
    get_worktree_registry().register(info)

    ctx = ToolContext(user_id=None, session_id=sid)
    ctx.extra["project_roots"] = [str(git_repo)]

    root = select_project_root(ctx)
    assert str(root) == info.worktree_path
    # Worktree path folded into project_roots for the deeper sandbox.
    assert info.worktree_path in [str(r) for r in ctx.extra["project_roots"]]


@pytest.mark.asyncio
async def test_select_project_root_direct_without_worktree(git_repo: Path):
    from leagent.project.fs import select_project_root
    from leagent.tools.base import ToolContext

    ctx = ToolContext(user_id=None, session_id=str(uuid4()))
    ctx.extra["project_roots"] = [str(git_repo)]
    root = select_project_root(ctx)
    assert root == git_repo.resolve()
