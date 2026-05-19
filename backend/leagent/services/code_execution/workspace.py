"""Per-session scratch workspace used as ``cwd`` by the subprocess sandbox.

The workspace gives user code a private writable directory that is
reset between sessions and bounded in size. Everything outside the
workspace is read-only from the sandbox's point of view (enforced by
``cwd`` + no mount tricks; real filesystem protection relies on OS
permissions, not on sandbox heuristics).

Each workspace owns:

* A unique directory under the manager's root (``<root>/<session_id>``).
* A best-effort on-disk quota enforced by :meth:`Workspace.enforce_quota`
  after each execution. Enforcement scans the directory size and raises
  :class:`WorkspaceQuotaExceeded` when the limit is exceeded. The
  caller (usually the sandbox) decides whether to truncate outputs or
  fail the step.

:class:`WorkspaceManager` keeps an in-memory LRU per ``(user_id,
session_id)`` so the agent can reuse the same workspace across turns.
It is safe to recreate the manager on restart — unknown directories are
not automatically reclaimed so administrators can inspect them.
"""

from __future__ import annotations

import os
import re
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import structlog

logger = structlog.get_logger(__name__)


_SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]")


class WorkspaceQuotaExceeded(RuntimeError):
    """Raised when a workspace exceeds its allowed on-disk size."""


@dataclass
class Workspace:
    """Single writable directory handed to one sandbox execution."""

    root: Path
    session_id: str
    created_at: float
    max_bytes: int = 64 * 1024 * 1024  # 64 MB
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return self.root

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def size_bytes(self) -> int:
        total = 0
        for dirpath, _, filenames in os.walk(self.root):
            for name in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    continue
        return total

    def enforce_quota(self) -> int:
        size = self.size_bytes()
        if size > self.max_bytes:
            raise WorkspaceQuotaExceeded(
                f"Workspace '{self.session_id}' exceeded {self.max_bytes} bytes (used {size})"
            )
        return size

    def list_files(self) -> list[Path]:
        if not self.root.exists():
            return []
        return sorted(p for p in self.root.rglob("*") if p.is_file())

    def write_bytes(self, rel_path: str, data: bytes) -> Path:
        safe = self._safe_rel(rel_path)
        target = self.root / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def write_text(self, rel_path: str, text: str) -> Path:
        return self.write_bytes(rel_path, text.encode("utf-8"))

    def reset(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root, ignore_errors=True)
        self.ensure()

    def _safe_rel(self, rel_path: str) -> Path:
        candidate = Path(rel_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"Unsafe workspace-relative path: {rel_path!r}")
        return candidate


class WorkspaceManager:
    """Creates and caches per-session :class:`Workspace` instances.

    Parameters
    ----------
    root:
        Filesystem root under which all workspaces live.
    max_workspace_bytes:
        Per-workspace quota (bytes) threaded into :attr:`Workspace.max_bytes`.
    idle_ttl_sec:
        Workspaces untouched for this many seconds are eligible for GC.
    """

    def __init__(
        self,
        root: str | os.PathLike[str],
        *,
        max_workspace_bytes: int = 64 * 1024 * 1024,
        idle_ttl_sec: float = 3600.0,
    ) -> None:
        self._root = Path(root)
        self._max_bytes = max_workspace_bytes
        self._idle_ttl = idle_ttl_sec
        self._lock = threading.RLock()
        self._cache: dict[str, Workspace] = {}
        self._last_seen: dict[str, float] = {}
        self._root.mkdir(parents=True, exist_ok=True)

    def _key(self, user_id: str | None, session_id: str | None) -> str:
        uid = _safe(user_id or "anon")
        sid = _safe(session_id or uuid.uuid4().hex)
        return f"{uid}__{sid}"

    def get(
        self,
        *,
        user_id: str | None,
        session_id: str | None,
        metadata: dict[str, str] | None = None,
    ) -> Workspace:
        key = self._key(user_id, session_id)
        now = time.time()
        with self._lock:
            ws = self._cache.get(key)
            if ws is None:
                ws = Workspace(
                    root=self._root / key,
                    session_id=key,
                    created_at=now,
                    max_bytes=self._max_bytes,
                    metadata=dict(metadata or {}),
                )
                ws.ensure()
                self._cache[key] = ws
            self._last_seen[key] = now
            return ws

    def release(self, workspace: Workspace) -> None:
        with self._lock:
            self._last_seen[workspace.session_id] = time.time()

    def discard(self, user_id: str | None, session_id: str | None) -> None:
        key = self._key(user_id, session_id)
        with self._lock:
            ws = self._cache.pop(key, None)
            self._last_seen.pop(key, None)
        if ws is not None:
            ws.reset()
            try:
                ws.path.rmdir()
            except OSError:
                pass

    def gc(self, *, include_disk: bool = True) -> list[str]:
        now = time.time()
        to_reap: list[str] = []
        with self._lock:
            for key, last in list(self._last_seen.items()):
                if now - last > self._idle_ttl:
                    to_reap.append(key)
            for key in to_reap:
                ws = self._cache.pop(key, None)
                self._last_seen.pop(key, None)
                if ws is not None:
                    shutil.rmtree(ws.path, ignore_errors=True)
            if include_disk:
                for path in self._root.iterdir():
                    if not path.is_dir() or path.name in self._cache:
                        continue
                    try:
                        mtime = path.stat().st_mtime
                    except OSError:
                        continue
                    if now - mtime > self._idle_ttl:
                        shutil.rmtree(path, ignore_errors=True)
                        to_reap.append(path.name)
        if to_reap:
            logger.info("workspace_gc", reaped=len(to_reap))
        return to_reap

    def iter_workspaces(self) -> Iterable[Workspace]:
        with self._lock:
            return list(self._cache.values())


def _safe(token: str) -> str:
    return _SAFE_ID_RE.sub("_", token)[:64] or "_"
