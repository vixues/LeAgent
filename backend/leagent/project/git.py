"""Async git subprocess wrapper used by the coding-project endpoints.

Why a dedicated wrapper? The HTTP layer needs structured, paginated
git output that's safe to call from FastAPI handlers. Using
``asyncio.create_subprocess_exec`` avoids the shell entirely (so
metacharacters in user-supplied paths can never execute), bounds
each call with a timeout, and parses ``--pretty=format`` records
deterministically.

The functions here intentionally do **not** mutate history. Writes
are limited to ``git_init`` (idempotent). The chat / coding agent
gets its commit/push capability through the curated ``project_shell``
tool, not via this module.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import structlog

logger = structlog.get_logger(__name__)


_GIT_TIMEOUT = 20.0
_GIT_LARGE_TIMEOUT = 45.0
_LOG_RECORD_SEP = "\x1f"  # ASCII unit separator
_LOG_LINE_SEP = "\x1e"  # ASCII record separator


class GitNotInstalledError(RuntimeError):
    """Raised when no ``git`` executable is on PATH."""


class GitCommandError(RuntimeError):
    """Raised when a git command exits non-zero.

    Carries ``returncode``, ``stdout`` (already-decoded) and
    ``stderr`` so HTTP handlers can surface a useful error to the
    UI without having to re-run the command in verbose mode.
    """

    def __init__(self, returncode: int, stdout: str, stderr: str, args: Sequence[str]):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.args = tuple(args)
        super().__init__(
            f"git {' '.join(args)} exited {returncode}: {stderr.strip() or stdout.strip()}"
        )


@dataclass(frozen=True)
class GitCommit:
    commit: str
    short: str
    author_name: str
    author_email: str
    date_iso: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "commit": self.commit,
            "short": self.short,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "date_iso": self.date_iso,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class GitStatusEntry:
    path: str
    status_code: str  # 2-char porcelain code, e.g. " M", "??", "MM"

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "status_code": self.status_code}


def _git_executable() -> str:
    exe = shutil.which("git")
    if not exe:
        raise GitNotInstalledError(
            "`git` is not installed or not on PATH on the server."
        )
    return exe


async def run_git(
    cwd: Path,
    args: Sequence[str],
    *,
    timeout: float = _GIT_TIMEOUT,
    check: bool = True,
) -> tuple[int, str, str]:
    """Run ``git <args>`` inside ``cwd``; return ``(returncode, stdout, stderr)``.

    ``shell=False`` is enforced — argv is passed unmodified so user
    input cannot break out via shell metacharacters. ``GIT_PAGER``
    and ``GIT_TERMINAL_PROMPT`` are stripped so commands never block
    on a credential prompt or pager.
    """
    exe = _git_executable()
    env = {
        **os.environ,
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
    }

    logger.debug("project_git_run", cwd=str(cwd), args=list(args), timeout=timeout)
    proc = await asyncio.create_subprocess_exec(
        exe,
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        raise GitCommandError(
            -1,
            "",
            f"git {' '.join(args)} timed out after {timeout:.1f}s",
            args,
        )

    stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
    stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
    if check and proc.returncode != 0:
        raise GitCommandError(proc.returncode or 1, stdout, stderr, args)
    return proc.returncode or 0, stdout, stderr


async def is_git_repo(cwd: Path) -> bool:
    """Return True iff ``cwd`` (or an ancestor inside the project) is a git work tree."""
    try:
        rc, _, _ = await run_git(
            cwd,
            ("rev-parse", "--is-inside-work-tree"),
            check=False,
        )
        return rc == 0
    except GitNotInstalledError:
        return False


async def git_init(cwd: Path) -> dict[str, str]:
    """Initialise a new repository in ``cwd``. Idempotent."""
    if await is_git_repo(cwd):
        return {"status": "already-initialised"}
    _, stdout, _ = await run_git(cwd, ("init",))
    return {"status": "initialised", "stdout": stdout.strip()}


async def git_log(
    cwd: Path,
    *,
    path: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[GitCommit]:
    """Return up to ``limit`` commits, optionally filtered to a single ``path``.

    Pagination is implemented with ``--skip`` so it works on any git
    version without needing ``git log --reverse``.
    """
    if limit <= 0:
        return []
    pretty = (
        f"--pretty=format:%H{_LOG_RECORD_SEP}%h{_LOG_RECORD_SEP}%an"
        f"{_LOG_RECORD_SEP}%ae{_LOG_RECORD_SEP}%aI{_LOG_RECORD_SEP}%s{_LOG_LINE_SEP}"
    )
    args: list[str] = [
        "log",
        f"-n{int(limit)}",
        f"--skip={int(max(0, offset))}",
        pretty,
        "--no-color",
    ]
    if path:
        args.extend(["--", path])
    _, stdout, _ = await run_git(cwd, args, timeout=_GIT_LARGE_TIMEOUT)

    commits: list[GitCommit] = []
    for chunk in stdout.split(_LOG_LINE_SEP):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        parts = chunk.split(_LOG_RECORD_SEP)
        if len(parts) < 6:
            continue
        commits.append(
            GitCommit(
                commit=parts[0],
                short=parts[1],
                author_name=parts[2],
                author_email=parts[3],
                date_iso=parts[4],
                summary=parts[5],
            )
        )
    return commits


async def git_show_file(cwd: Path, commit: str, path: str) -> str:
    """Return the contents of ``path`` at ``commit``."""
    if not commit or not path:
        raise ValueError("commit and path are required")
    if commit.startswith("-") or path.startswith("-"):
        raise ValueError("Refusing argv that begins with '-'.")
    _, stdout, _ = await run_git(
        cwd,
        ("show", f"{commit}:{path}"),
        timeout=_GIT_LARGE_TIMEOUT,
    )
    return stdout


async def git_diff_for_commit(
    cwd: Path,
    commit: str,
    *,
    path: Optional[str] = None,
) -> str:
    """Return the unified diff for ``commit`` (vs its parent).

    Falls back to ``git show --format=`` for the root commit (which
    has no parent and would otherwise error). The returned string is
    the raw diff, suitable for a simple +/- line renderer.
    """
    if not commit:
        raise ValueError("commit is required")
    if commit.startswith("-"):
        raise ValueError("Refusing argv that begins with '-'.")
    parent = f"{commit}^"
    args: list[str] = [
        "diff",
        "--no-color",
        f"{parent}..{commit}",
    ]
    if path:
        args.extend(["--", path])
    rc, stdout, stderr = await run_git(cwd, args, check=False, timeout=_GIT_LARGE_TIMEOUT)
    if rc == 0:
        return stdout
    # Root commit: ``<sha>^`` doesn't exist. Fall back to ``git show``.
    args2: list[str] = ["show", "--no-color", "--format=", commit]
    if path:
        args2.extend(["--", path])
    _, stdout2, _ = await run_git(cwd, args2, timeout=_GIT_LARGE_TIMEOUT)
    return stdout2


async def git_diff_worktree(cwd: Path, *, path: Optional[str] = None) -> str:
    """Return the working-tree diff vs HEAD."""
    args: list[str] = ["diff", "--no-color", "HEAD"]
    if path:
        args.extend(["--", path])
    rc, stdout, _ = await run_git(cwd, args, check=False, timeout=_GIT_LARGE_TIMEOUT)
    if rc != 0:
        return ""
    return stdout


async def git_status_porcelain(cwd: Path) -> list[GitStatusEntry]:
    """Return the working-tree status as a list of porcelain entries.

    Output format is ``XY <path>`` per line, where ``XY`` is the
    standard 2-character porcelain code (e.g. ``" M"``, ``"A "``,
    ``"??"`` for untracked, ``"MM"`` for both index+worktree).
    """
    if not await is_git_repo(cwd):
        return []
    rc, stdout, _ = await run_git(
        cwd,
        ("-c", "color.status=false", "status", "--porcelain"),
        check=False,
    )
    if rc != 0:
        return []
    entries: list[GitStatusEntry] = []
    for raw in stdout.splitlines():
        if len(raw) < 4:
            continue
        code = raw[:2]
        rest = raw[3:]
        # Renames look like "R  old -> new"; record the new path.
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        entries.append(GitStatusEntry(path=rest, status_code=code))
    return entries


__all__ = [
    "GitCommandError",
    "GitNotInstalledError",
    "GitCommit",
    "GitStatusEntry",
    "run_git",
    "is_git_repo",
    "git_init",
    "git_log",
    "git_show_file",
    "git_diff_for_commit",
    "git_diff_worktree",
    "git_status_porcelain",
]
