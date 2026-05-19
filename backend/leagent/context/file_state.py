"""LRU file-state cache with pin semantics and token budgeting.

Tracks files the agent has read during a session. Pinned files are never
evicted; unpinned entries are evicted LRU-first when *max_entries* or
*max_tokens* is reached.
"""

from __future__ import annotations

import copy
import os
from collections import OrderedDict
from pathlib import Path

from leagent.context.types import FileReadRecord

__all__ = ["FileState"]


class FileState:
    """Session-scoped cache of files the agent has read."""

    def __init__(
        self,
        *,
        max_entries: int = 64,
        max_tokens: int = 16_000,
    ) -> None:
        self._records: OrderedDict[str, FileReadRecord] = OrderedDict()
        self._max_entries = max_entries
        self._max_tokens = max_tokens

    # -- mutation -----------------------------------------------------------

    def record_read(self, path: str | Path, *, tokens: int = 0) -> FileReadRecord:
        resolved = str(Path(path).resolve())
        try:
            stat = os.stat(resolved)
            rec = FileReadRecord(
                path=resolved,
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                tokens=tokens,
                pinned=self._records[resolved].pinned if resolved in self._records else False,
            )
        except OSError:
            rec = FileReadRecord(
                path=resolved, mtime_ns=0, size=0, tokens=tokens,
                pinned=self._records[resolved].pinned if resolved in self._records else False,
            )
        self._records[resolved] = rec
        self._records.move_to_end(resolved)
        self._evict()
        return rec

    def touch(self, path: str | Path) -> None:
        resolved = str(Path(path).resolve())
        if resolved in self._records:
            self._records.move_to_end(resolved)

    def pin(self, path: str | Path) -> None:
        resolved = str(Path(path).resolve())
        if resolved in self._records:
            self._records[resolved].pinned = True

    def unpin(self, path: str | Path) -> None:
        resolved = str(Path(path).resolve())
        if resolved in self._records:
            self._records[resolved].pinned = False

    def forget(self, path: str | Path) -> None:
        self._records.pop(str(Path(path).resolve()), None)

    # -- introspection -----------------------------------------------------

    def has_record(self, path: str | Path) -> bool:
        return str(Path(path).resolve()) in self._records

    def get(self, path: str | Path) -> FileReadRecord | None:
        return self._records.get(str(Path(path).resolve()))

    def has_changed(self, path: str | Path) -> bool:
        resolved = str(Path(path).resolve())
        rec = self._records.get(resolved)
        if rec is None:
            return True
        try:
            stat = os.stat(resolved)
        except OSError:
            return True
        return stat.st_mtime_ns != rec.mtime_ns or stat.st_size != rec.size

    def paths(self) -> list[str]:
        return list(self._records.keys())

    def recent_paths(self, *, limit: int = 5) -> list[str]:
        keys = list(self._records.keys())
        return keys[-limit:] if limit < len(keys) else keys

    def pinned_paths(self) -> list[str]:
        return [k for k, v in self._records.items() if v.pinned]

    @property
    def total_tokens(self) -> int:
        return sum(r.tokens for r in self._records.values())

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, path: object) -> bool:
        if not isinstance(path, (str, Path)):
            return False
        return self.has_record(path)

    # -- eviction ----------------------------------------------------------

    def _evict(self) -> None:
        while len(self._records) > self._max_entries or self.total_tokens > self._max_tokens:
            evicted = False
            for key in list(self._records.keys()):
                if not self._records[key].pinned:
                    del self._records[key]
                    evicted = True
                    break
            if not evicted:
                break

    # -- merge --------------------------------------------------------------

    def merge_from(self, other: FileState, *, prefer_other: bool = True) -> None:
        """Merge paths from another cache into this one (for sub-agent fork).

        When a path exists on both sides, keep the other's record if
        ``prefer_other`` is True or if the other's ``mtime_ns`` is newer.
        """
        if other is self:
            return
        for path, rec in other._records.items():
            if path not in self._records:
                self._records[path] = copy.copy(rec)
            else:
                cur = self._records[path]
                take_other = prefer_other or rec.mtime_ns >= cur.mtime_ns
                if take_other:
                    self._records[path] = copy.copy(rec)
            self._records.move_to_end(path)
        self._evict()

    # -- cloning -----------------------------------------------------------

    def clone(self) -> FileState:
        new = FileState(max_entries=self._max_entries, max_tokens=self._max_tokens)
        new._records = OrderedDict(
            (k, copy.copy(v)) for k, v in self._records.items()
        )
        return new

    # -- persistence -------------------------------------------------------

    def snapshot(self) -> list[dict[str, object]]:
        return [
            {
                "path": rec.path,
                "mtime_ns": rec.mtime_ns,
                "size": rec.size,
                "tokens": rec.tokens,
                "pinned": rec.pinned,
            }
            for rec in self._records.values()
        ]

    @classmethod
    def from_snapshot(
        cls,
        data: list[dict[str, object]] | None,
        *,
        max_entries: int = 64,
        max_tokens: int = 16_000,
    ) -> FileState:
        cache = cls(max_entries=max_entries, max_tokens=max_tokens)
        for entry in data or []:
            path = str(entry.get("path", ""))
            if not path:
                continue
            cache._records[path] = FileReadRecord(
                path=path,
                mtime_ns=int(entry.get("mtime_ns") or 0),
                size=int(entry.get("size") or 0),
                tokens=int(entry.get("tokens") or 0),
                pinned=bool(entry.get("pinned", False)),
            )
        return cache
