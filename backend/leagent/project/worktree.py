"""Git worktree management for isolated agent coding sessions.

Codex-style parallelism: when a session runs with
``workspace_mode = "worktree"``, the agent works on a dedicated git
worktree + branch instead of the user's checkout. Changes flow back
through the change-review queue (diff → approve/merge → reject), so
multiple sessions can work on the same repository without clobbering
each other or the user's working tree.

Layout: worktrees live under ``LEAGENT_HOME/worktrees/<repo>-<sid8>``
with branches named ``leagent/<sid8>-<suffix>``.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_BRANCH_PREFIX = "leagent"


class WorktreeError(RuntimeError):
    """Raised when a git worktree operation fails."""


@dataclass
class WorktreeInfo:
    """One live agent worktree."""

    session_id: str
    project_root: str  # the user's original checkout
    worktree_path: str
    branch: str
    base_branch: str
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "project_root": self.project_root,
            "worktree_path": self.worktree_path,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "created_at": self.created_at,
        }


async def _git(
    *args: str,
    cwd: str | Path,
    check: bool = True,
) -> tuple[int, str, str]:
    """Run one git command, returning ``(returncode, stdout, stderr)``."""
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    out_raw, err_raw = await proc.communicate()
    out = out_raw.decode("utf-8", errors="replace")
    err = err_raw.decode("utf-8", errors="replace")
    rc = proc.returncode if proc.returncode is not None else -1
    if check and rc != 0:
        raise WorktreeError(
            f"git {' '.join(args)} failed ({rc}): {err.strip() or out.strip()}"
        )
    return rc, out, err


async def is_git_repo(path: str | Path) -> bool:
    try:
        rc, out, _ = await _git(
            "rev-parse", "--is-inside-work-tree", cwd=path, check=False,
        )
        return rc == 0 and out.strip() == "true"
    except (FileNotFoundError, OSError):
        return False


async def current_branch(path: str | Path) -> str:
    _, out, _ = await _git("rev-parse", "--abbrev-ref", "HEAD", cwd=path)
    return out.strip()


def _worktrees_home() -> Path:
    home = os.environ.get("LEAGENT_HOME") or str(Path.home() / ".leagent")
    return Path(home) / "worktrees"


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text).strip("-") or "repo"


class WorktreeManager:
    """Create / diff / merge / remove agent worktrees."""

    async def create(
        self,
        project_root: str | Path,
        session_id: str,
        *,
        base_branch: str | None = None,
    ) -> WorktreeInfo:
        """Create a worktree + branch for a session off ``project_root``."""
        root = Path(project_root).resolve()
        if not await is_git_repo(root):
            raise WorktreeError(
                f"{root} is not a git repository; worktree mode requires git."
            )
        base = base_branch or await current_branch(root)
        sid8 = _slug(str(session_id))[:8]
        suffix = uuid.uuid4().hex[:6]
        branch = f"{_BRANCH_PREFIX}/{sid8}-{suffix}"
        wt_dir = _worktrees_home() / f"{_slug(root.name)}-{sid8}-{suffix}"
        wt_dir.parent.mkdir(parents=True, exist_ok=True)

        await _git(
            "worktree", "add", "-b", branch, str(wt_dir), base, cwd=root,
        )
        info = WorktreeInfo(
            session_id=str(session_id),
            project_root=str(root),
            worktree_path=str(wt_dir),
            branch=branch,
            base_branch=base,
        )
        logger.info(
            "worktree_created",
            session_id=str(session_id),
            branch=branch,
            path=str(wt_dir),
        )
        return info

    async def _track_new_files(self, info: WorktreeInfo) -> None:
        """Mark untracked files intent-to-add so they appear in diffs."""
        await _git("add", "-N", ".", cwd=info.worktree_path, check=False)

    async def diff(self, info: WorktreeInfo) -> str:
        """Full diff of the worktree (committed + uncommitted) vs the base branch."""
        await self._track_new_files(info)
        _, out, _ = await _git(
            "diff", info.base_branch, cwd=info.worktree_path, check=False,
        )
        return out

    async def diff_stats(self, info: WorktreeInfo) -> dict[str, int]:
        """``{files_changed, additions, deletions}`` vs the base branch."""
        await self._track_new_files(info)
        _, out, _ = await _git(
            "diff", "--numstat", info.base_branch,
            cwd=info.worktree_path, check=False,
        )
        files = additions = deletions = 0
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            files += 1
            try:
                additions += int(parts[0])
                deletions += int(parts[1])
            except ValueError:
                pass  # binary files report "-"
        return {"files_changed": files, "additions": additions, "deletions": deletions}

    async def changed_files(self, info: WorktreeInfo) -> list[str]:
        await self._track_new_files(info)
        _, out, _ = await _git(
            "diff", "--name-only", info.base_branch,
            cwd=info.worktree_path, check=False,
        )
        return [ln.strip() for ln in out.splitlines() if ln.strip()]

    async def commit_all(self, info: WorktreeInfo, message: str) -> bool:
        """Stage and commit everything in the worktree. Returns ``False`` if clean."""
        await _git("add", "-A", cwd=info.worktree_path)
        rc, out, _ = await _git(
            "status", "--porcelain", cwd=info.worktree_path,
        )
        if not out.strip():
            return False
        await _git(
            "-c", "user.name=LeAgent",
            "-c", "user.email=agent@leagent.local",
            "commit", "-m", message,
            cwd=info.worktree_path,
        )
        return True

    async def merge_into_base(self, info: WorktreeInfo, *, message: str) -> None:
        """Commit pending changes, then merge the branch into the base checkout.

        The merge runs in the user's original checkout. Raises
        :class:`WorktreeError` (after ``merge --abort``) on conflicts.
        """
        await self.commit_all(info, message)
        root = info.project_root
        head = await current_branch(root)
        if head != info.base_branch:
            raise WorktreeError(
                f"Base checkout is on {head!r}, expected {info.base_branch!r}; "
                "switch branches before merging this review."
            )
        rc, _, err = await _git(
            "merge", "--no-ff", "-m", message, info.branch, cwd=root, check=False,
        )
        if rc != 0:
            await _git("merge", "--abort", cwd=root, check=False)
            raise WorktreeError(f"Merge failed: {err.strip()[:500]}")
        logger.info("worktree_merged", branch=info.branch, base=info.base_branch)

    async def remove(self, info: WorktreeInfo, *, delete_branch: bool = True) -> None:
        await _git(
            "worktree", "remove", "--force", info.worktree_path,
            cwd=info.project_root, check=False,
        )
        if delete_branch:
            await _git(
                "branch", "-D", info.branch, cwd=info.project_root, check=False,
            )
        logger.info("worktree_removed", branch=info.branch)


class WorktreeRegistry:
    """In-process map of active worktrees per session.

    ``select_project_root`` consults this registry: when a session has
    ``workspace_mode = worktree`` for a project root, every ``project_*``
    tool transparently operates inside the worktree instead of the
    user's checkout.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: session_id -> {resolved project_root -> WorktreeInfo}
        self._by_session: dict[str, dict[str, WorktreeInfo]] = {}

    def register(self, info: WorktreeInfo) -> None:
        with self._lock:
            self._by_session.setdefault(info.session_id, {})[info.project_root] = info

    def resolve(self, session_id: str | None, project_root: str | Path) -> WorktreeInfo | None:
        """Return the worktree bound to ``(session, project_root)``, if any."""
        if session_id is None:
            return None
        key = str(Path(project_root).resolve())
        with self._lock:
            return self._by_session.get(str(session_id), {}).get(key)

    def for_session(self, session_id: str) -> list[WorktreeInfo]:
        with self._lock:
            return list(self._by_session.get(str(session_id), {}).values())

    def find_by_path(self, worktree_path: str) -> WorktreeInfo | None:
        with self._lock:
            for infos in self._by_session.values():
                for info in infos.values():
                    if info.worktree_path == worktree_path:
                        return info
        return None

    def unregister(self, session_id: str, project_root: str) -> None:
        with self._lock:
            infos = self._by_session.get(str(session_id))
            if infos:
                infos.pop(str(Path(project_root).resolve()), None)
                if not infos:
                    self._by_session.pop(str(session_id), None)


_MANAGER: WorktreeManager | None = None
_REGISTRY: WorktreeRegistry | None = None


def get_worktree_manager() -> WorktreeManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = WorktreeManager()
    return _MANAGER


def get_worktree_registry() -> WorktreeRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = WorktreeRegistry()
    return _REGISTRY


def reset_worktree_registry() -> None:
    """Testing hook."""
    global _REGISTRY
    _REGISTRY = None
