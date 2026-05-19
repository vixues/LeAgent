"""Working set: pinned files with head/tail excerpts for the LLM."""

from __future__ import annotations

from pathlib import Path

from leagent.context.types import WorkingSetEntry

__all__ = ["WorkingSet"]


class WorkingSet:
    """Tracks user-pinned (or auto-pinned) files and generates excerpts."""

    def __init__(
        self,
        *,
        head_lines: int = 20,
        tail_lines: int = 10,
    ) -> None:
        self._head_lines = head_lines
        self._tail_lines = tail_lines
        self._pinned: dict[str, WorkingSetEntry] = {}

    def pin(self, path: str | Path) -> WorkingSetEntry | None:
        resolved = str(Path(path).resolve())
        entry = self._build_entry(resolved)
        if entry is not None:
            self._pinned[resolved] = entry
        return entry

    def unpin(self, path: str | Path) -> None:
        self._pinned.pop(str(Path(path).resolve()), None)

    def refresh(self, path: str | Path) -> WorkingSetEntry | None:
        resolved = str(Path(path).resolve())
        if resolved not in self._pinned:
            return None
        entry = self._build_entry(resolved)
        if entry is not None:
            self._pinned[resolved] = entry
        return entry

    def entries(self) -> list[WorkingSetEntry]:
        return list(self._pinned.values())

    def paths(self) -> list[str]:
        return list(self._pinned.keys())

    def __len__(self) -> int:
        return len(self._pinned)

    def _build_entry(self, resolved: str) -> WorkingSetEntry | None:
        try:
            p = Path(resolved)
            if not p.is_file():
                return None
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return None

        total = len(lines)
        head = "\n".join(lines[: self._head_lines])
        tail_start = max(self._head_lines, total - self._tail_lines)
        tail = "\n".join(lines[tail_start:]) if tail_start < total else ""

        content = head + ("\n" + tail if tail else "")
        tokens = max(1, len(content) // 3)

        return WorkingSetEntry(
            path=resolved,
            excerpt_head=head,
            excerpt_tail=tail,
            total_lines=total,
            tokens=tokens,
        )
