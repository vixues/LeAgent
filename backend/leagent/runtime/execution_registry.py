"""In-process registry for :class:`ExecutionRun` handles."""

from __future__ import annotations

from leagent.runtime.execution_run import ExecutionRun


class ExecutionRunRegistry:
    """Track active runs for observability and cross-scope linking."""

    def __init__(self) -> None:
        self._runs: dict[str, ExecutionRun] = {}
        self._prompt_index: dict[str, str] = {}

    def register(self, run: ExecutionRun) -> ExecutionRun:
        self._runs[run.run_id] = run
        if run.prompt_id:
            self._prompt_index[run.prompt_id] = run.run_id
        return run

    def get(self, run_id: str) -> ExecutionRun | None:
        return self._runs.get(run_id)

    def remove(self, run_id: str) -> None:
        run = self._runs.pop(run_id, None)
        if run is not None and run.prompt_id:
            self._prompt_index.pop(run.prompt_id, None)

    def list_for_session(self, session_id: str) -> list[ExecutionRun]:
        return [r for r in self._runs.values() if r.session_id == session_id]

    def get_by_prompt_id(self, prompt_id: str) -> ExecutionRun | None:
        run_id = self._prompt_index.get(prompt_id)
        if run_id is not None:
            return self._runs.get(run_id)
        return None

    def get_active_chat_turn(self, session_id: str) -> ExecutionRun | None:
        """Return the most recently registered chat-turn run for *session_id*."""
        matches = [
            r
            for r in self._runs.values()
            if r.session_id == session_id and r.scope.value == "chat_turn"
        ]
        if not matches:
            return None
        return max(matches, key=lambda r: r.registered_at)


_registry: ExecutionRunRegistry | None = None


def get_execution_run_registry() -> ExecutionRunRegistry:
    global _registry
    if _registry is None:
        _registry = ExecutionRunRegistry()
    return _registry


__all__ = ["ExecutionRunRegistry", "get_execution_run_registry"]
