"""ToolUseContext: the per-turn context handle passed into query() and tools.

Bundles everything a tool-calling turn needs (abort signal, tool
registry/executor, memory prefetch handle, file-state cache, etc.) so the
core loop can stay stateless.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from leagent.agent.hooks import HookManager
    from leagent.context.file_state import FileState
    from leagent.sdk.protocols import RecallProvider
    from leagent.tools.executor import ToolExecutor
    from leagent.tools.registry import ToolRegistry


@dataclass
class ToolUseContext:
    """Runtime context threaded through ``query()`` and tool calls."""

    abort_event: asyncio.Event
    tools: "ToolRegistry"
    executor: "ToolExecutor"
    file_state_cache: "FileState"
    recall_handle: "RecallProvider | None" = None
    hooks: "HookManager | None" = None

    session_id: UUID | None = None
    user_id: UUID | None = None
    task_id: UUID | None = None
    agent_id: str | None = None

    content_replacement_state: dict[str, Any] = field(default_factory=dict)
    query_tracking: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def aborted(self) -> bool:
        return self.abort_event.is_set()

    def raise_if_aborted(self) -> None:
        if self.aborted:
            raise asyncio.CancelledError("query aborted")
