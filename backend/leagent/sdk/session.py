"""AgentSession — the ergonomic multi-turn SDK handle.

An ``AgentSession`` wraps a :class:`~leagent.sdk.AgentRuntime` +
per-session state (engine, context, memory) into a stateful object
that SDK consumers can hold across multiple turns.

Usage::

    from leagent.sdk import AgentRuntime

    runtime = AgentRuntime.from_service_manager(sm)
    session = runtime.session("default_agent", session_id=sid, user_id=uid)

    result = await session.turn("What can you help me with?")
    print(result.text)

    # Inspect context and memory:
    print(session.context_info)
    episodes = await session.memory.export_episodes(user_id=uid)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from leagent.sdk.events import AgentEvent, AgentResult

if TYPE_CHECKING:
    import asyncio
    from collections.abc import AsyncIterator

    from leagent.memory.agent_memory import AgentMemory
    from leagent.runtime.runtime import AgentRuntime


@dataclass
class ContextInspector:
    """Read-only window into the session's context assembly state."""

    agent_name: str = ""
    session_id: str = ""
    recipe: str = ""
    source_ids: list[str] = field(default_factory=list)
    last_budget_chars: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "recipe": self.recipe,
            "source_ids": self.source_ids,
            "last_budget_chars": self.last_budget_chars,
        }


@dataclass
class MemoryInspector:
    """Read-only window into the session's memory state.

    Provides convenience methods that delegate to the underlying
    :class:`AgentMemory` without exposing write operations.
    """

    _memory: AgentMemory | None = None

    @property
    def available(self) -> bool:
        return self._memory is not None

    async def recall(
        self,
        query: str,
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        limit: int = 8,
    ) -> Any:
        if self._memory is None:
            return None
        return await self._memory.recall(
            query, user_id=user_id, session_id=session_id, limit=limit,
        )

    async def export_episodes(
        self, *, user_id: UUID, limit: int = 100,
    ) -> list[Any]:
        if self._memory is None:
            return []
        return await self._memory.export_episodes(user_id=user_id, limit=limit)

    async def export_facts(
        self, *, user_id: UUID, limit: int = 100,
    ) -> list[Any]:
        if self._memory is None:
            return []
        return await self._memory.export_facts(user_id=user_id, limit=limit)

    def write_status(self) -> dict[str, Any]:
        if self._memory is None:
            return {"available": False}
        return self._memory.memory_write_status()


class AgentSession:
    """Stateful multi-turn session handle.

    Wraps a runtime + engine so callers don't need to thread
    ``session_id``/``user_id``/``engine`` through every call.
    """

    def __init__(
        self,
        runtime: AgentRuntime,
        agent: Any,
        *,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        cwd: str = ".",
        tool_extra: dict[str, Any] | None = None,
        abort_event: asyncio.Event | None = None,
    ) -> None:
        self._runtime = runtime
        self._agent = agent
        self._session_id = session_id
        self._user_id = user_id
        self._cwd = cwd
        self._tool_extra = tool_extra
        self._abort_event = abort_event
        self._engine: Any = None
        self._turn_count = 0

        definition = runtime.resolve(agent)
        self._context_info = ContextInspector(
            agent_name=definition.name,
            session_id=str(session_id or ""),
            recipe=definition.resolved_recipe(),
        )

        mem = runtime.context.agent_memory if definition.memory.enabled else None
        self._memory_info = MemoryInspector(_memory=mem)

    @property
    def context(self) -> ContextInspector:
        """Read-only context inspector."""
        return self._context_info

    @property
    def memory(self) -> MemoryInspector:
        """Read-only memory inspector."""
        return self._memory_info

    @property
    def turn_count(self) -> int:
        return self._turn_count

    def _get_or_build_engine(self) -> Any:
        if self._engine is None:
            self._engine = self._runtime.build_engine(
                self._agent,
                session_id=self._session_id,
                user_id=self._user_id,
                cwd=self._cwd,
                tool_extra=self._tool_extra,
                abort_event=self._abort_event,
            )
        return self._engine

    async def stream(
        self, prompt: str | dict[str, Any],
    ) -> AsyncIterator[AgentEvent]:
        """Run a turn and stream events."""
        engine = self._get_or_build_engine()
        self._turn_count += 1
        async for event in self._runtime.stream(
            self._agent, prompt, engine=engine,
            session_id=self._session_id,
            user_id=self._user_id,
        ):
            yield event

    async def turn(
        self,
        prompt: str | dict[str, Any],
        *,
        collect_events: bool = False,
    ) -> AgentResult:
        """Run a turn to completion and return the aggregate result."""
        engine = self._get_or_build_engine()
        self._turn_count += 1
        return await self._runtime.run(
            self._agent, prompt, engine=engine,
            session_id=self._session_id,
            user_id=self._user_id,
            collect_events=collect_events,
        )

    async def resume(
        self,
        checkpoint_id: str,
        prompt: str | dict[str, Any],
    ) -> AsyncIterator[AgentEvent]:
        """Resume this session from a persisted checkpoint and stream events.

        Rebuilds the engine from the checkpoint's message history (replacing
        the session's in-process engine) so a paused turn survives restarts.
        """
        self._turn_count += 1
        async for event in self._runtime.resume(
            self._agent,
            checkpoint_id,
            prompt,
            user_id=self._user_id,
            cwd=self._cwd,
            tool_extra=self._tool_extra,
            abort_event=self._abort_event,
        ):
            yield event

    def abort(self) -> None:
        """Signal the running turn to abort."""
        if self._abort_event is not None:
            self._abort_event.set()
        if self._engine is not None and hasattr(self._engine, "abort"):
            self._engine.abort()


__all__ = [
    "AgentSession",
    "ContextInspector",
    "MemoryInspector",
]
