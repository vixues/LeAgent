"""In-process registry for :class:`ExecutionRun` handles."""

from __future__ import annotations

from typing import Any

from leagent.runtime.execution_run import ExecutionRun


class ExecutionRunRegistry:
    """Track active runs for observability and cross-scope linking."""

    def __init__(self) -> None:
        self._runs: dict[str, ExecutionRun] = {}

    def register(self, run: ExecutionRun) -> ExecutionRun:
        self._runs[run.run_id] = run
        return run

    def get(self, run_id: str) -> ExecutionRun | None:
        return self._runs.get(run_id)

    def remove(self, run_id: str) -> None:
        self._runs.pop(run_id, None)

    def list_for_session(self, session_id: str) -> list[ExecutionRun]:
        return [r for r in self._runs.values() if r.session_id == session_id]


_registry: ExecutionRunRegistry | None = None


def get_execution_run_registry() -> ExecutionRunRegistry:
    global _registry
    if _registry is None:
        _registry = ExecutionRunRegistry()
    return _registry


__all__ = ["ExecutionRunRegistry", "get_execution_run_registry"]
