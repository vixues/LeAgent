"""Smoke tests for the Folder code-project HTTP endpoints.

Covers:

- ``services/coding_projects/git.py`` async git wrapper against a real
  temp git repo (init + 2 commits + binary file).
- ``services/coding_projects/paths.py`` ownership / allow-list rejection
  via direct calls (the HTTP contract is exercised in
  :mod:`tests.test_chat_project_context` for chat plumbing).

The HTTP layer itself is shallow glue — covering the underlying
helpers gives strong confidence the endpoints will behave the
same way without needing a fully wired DB session.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

from leagent.project.git import (
    GitCommandError,
    git_diff_for_commit,
    git_init,
    git_log,
    git_show_file,
    git_status_porcelain,
    is_git_repo,
    run_git,
)
from leagent.project.paths import (
    ProjectPathSafetyError,
    assert_folder_owner,
    resolve_owned_project_folder,
    validate_project_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.fixture()
def git_project(tmp_path: Path) -> Path:
    if not shutil.which("git"):
        pytest.skip("git is not available on this system")

    project = tmp_path / "demo"
    project.mkdir()
    _git("init", "-b", "main", cwd=project)
    _git("config", "user.email", "test@example.com", cwd=project)
    _git("config", "user.name", "Test", cwd=project)

    (project / "README.md").write_text("# demo\n", encoding="utf-8")
    _git("add", ".", cwd=project)
    _git("commit", "-m", "initial", cwd=project)

    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (project / "binary.bin").write_bytes(b"\x00\x01\x02\x03")
    _git("add", ".", cwd=project)
    _git("commit", "-m", "add main + binary", cwd=project)

    # An untracked file so `git status` has something to report.
    (project / "scratch.txt").write_text("scratch\n", encoding="utf-8")

    return project


# ---------------------------------------------------------------------------
# git wrapper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_is_git_repo_true_for_real_repo(git_project: Path) -> None:
    assert await is_git_repo(git_project) is True


@pytest.mark.asyncio
async def test_is_git_repo_false_for_plain_dir(tmp_path: Path) -> None:
    assert await is_git_repo(tmp_path) is False


@pytest.mark.asyncio
async def test_git_log_returns_two_commits(git_project: Path) -> None:
    commits = await git_log(git_project, limit=10)
    assert len(commits) == 2
    head, prev = commits
    assert head.summary == "add main + binary"
    assert prev.summary == "initial"
    assert head.short and len(head.short) >= 7
    assert head.author_email == "test@example.com"


@pytest.mark.asyncio
async def test_git_log_supports_path_filter(git_project: Path) -> None:
    commits = await git_log(git_project, path="src/main.py", limit=10)
    assert len(commits) == 1
    assert commits[0].summary == "add main + binary"


@pytest.mark.asyncio
async def test_git_show_file_at_head(git_project: Path) -> None:
    commits = await git_log(git_project, limit=1)
    body = await git_show_file(git_project, commits[0].commit, "src/main.py")
    assert body.strip() == "print('hi')"


@pytest.mark.asyncio
async def test_git_diff_for_root_commit_falls_back(git_project: Path) -> None:
    """``<sha>^`` doesn't exist for the root commit; the helper must not raise."""
    commits = await git_log(git_project, limit=10)
    root = commits[-1]
    diff = await git_diff_for_commit(git_project, root.commit)
    assert "README.md" in diff


@pytest.mark.asyncio
async def test_git_status_picks_up_untracked(git_project: Path) -> None:
    entries = await git_status_porcelain(git_project)
    paths = {e.path: e.status_code for e in entries}
    assert "scratch.txt" in paths
    assert paths["scratch.txt"].startswith("??")


@pytest.mark.asyncio
async def test_git_init_is_idempotent(tmp_path: Path) -> None:
    if not shutil.which("git"):
        pytest.skip("git is not available")
    out1 = await git_init(tmp_path)
    out2 = await git_init(tmp_path)
    assert out1["status"] == "initialised"
    assert out2["status"] == "already-initialised"


@pytest.mark.asyncio
async def test_git_show_rejects_argv_starting_with_dash(git_project: Path) -> None:
    with pytest.raises(ValueError):
        await git_show_file(git_project, "--exec", "src/main.py")


@pytest.mark.asyncio
async def test_git_log_invalid_path_returns_empty(git_project: Path) -> None:
    """``git log -- <bogus>`` returns no rows rather than failing."""
    commits = await git_log(git_project, path="this/does/not/exist", limit=10)
    assert commits == []


@pytest.mark.asyncio
async def test_git_command_error_carries_streams(tmp_path: Path) -> None:
    """A plain (non-git) directory raises GitCommandError on rev-list."""
    # `is_git_repo` returns False here (check=False), so prove the error
    # surface separately by calling rev-list directly through run_git.
    if not shutil.which("git"):
        pytest.skip("git is not available")
    with pytest.raises(GitCommandError) as exc:
        await run_git(tmp_path, ("log", "--oneline"))
    assert exc.value.returncode != 0
    assert exc.value.stderr or exc.value.stdout


# ---------------------------------------------------------------------------
# safety
# ---------------------------------------------------------------------------


def test_assert_folder_owner_accepts_owner() -> None:
    user_id = uuid4()
    folder = type("F", (), {"user_id": user_id})()
    assert_folder_owner(folder, user_id)  # no raise


def test_assert_folder_owner_rejects_other() -> None:
    folder = type("F", (), {"user_id": uuid4()})()
    with pytest.raises(ProjectPathSafetyError):
        assert_folder_owner(folder, uuid4())


def test_resolve_owned_project_folder_requires_project_mode(tmp_path: Path) -> None:
    user_id = uuid4()
    folder = type(
        "F",
        (),
        {
            "user_id": user_id,
            "is_project": False,
            "project_path": str(tmp_path),
        },
    )()
    with pytest.raises(ProjectPathSafetyError):
        resolve_owned_project_folder(folder, user_id)


def test_resolve_owned_project_folder_happy_path(tmp_path: Path) -> None:
    user_id = uuid4()
    folder = type(
        "F",
        (),
        {
            "user_id": user_id,
            "is_project": True,
            "project_path": str(tmp_path),
        },
    )()
    resolved = resolve_owned_project_folder(folder, user_id)
    assert resolved == tmp_path.resolve()


def test_validate_project_path_rejects_file(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("x")
    with pytest.raises(ProjectPathSafetyError):
        validate_project_path(str(f))


