"""ContextSource protocol and the ResolveContext handle.

Every source implements :class:`ContextSource` — an async resolver that
turns runtime state into a :class:`ContextBlock`. The protocol is
deliberately minimal: identity + scope metadata + one async method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID

from leagent.context.types import ContextBlock, ContextScope, RenderTarget

if TYPE_CHECKING:
    from leagent.context.file_state import FileState
    from leagent.context.working_set import WorkingSet
    from leagent.memory.agent_memory import AgentMemory
    from leagent.memory.working_scratchpad import WorkingScratchpad
    from leagent.sdk.protocols import RecallProvider
    from leagent.services.session import SessionManager
    from leagent.skills.manager import SkillsManager
    from leagent.tools.base import ToolPermissionContext
    from leagent.code.artifacts import SessionArtifactStore
    from leagent.code.operations import OperationJournal
    from leagent.tools.registry import ToolRegistry


@dataclass
class ResolveContext:
    """Runtime handle threaded into every source's ``resolve()``."""

    cwd: str = "."
    query: str = ""
    variant: str = "default_agent"
    template_variant: str = "default"
    persona_override: str = ""
    append_extra: str = ""
    workflow_hint: str = ""
    template_vars: dict[str, Any] = field(default_factory=dict)
    agent_id: str = "default"

    tools: "ToolRegistry | None" = None
    permission_context: "ToolPermissionContext | None" = None
    skills_manager: "SkillsManager | None" = None

    agent_memory: "AgentMemory | None" = None
    recall_handle: "RecallProvider | None" = None
    recall_limit: int = 5

    session_manager: "SessionManager | None" = None
    session_id: UUID | None = None
    user_id: UUID | None = None
    task_id: UUID | None = None

    file_state: "FileState | None" = None
    working_scratchpad: "WorkingScratchpad | None" = None
    working_set: "WorkingSet | None" = None

    # Settings pulled from ContextSettings
    project_memory_denylist: list[str] = field(default_factory=list)
    project_memory_allowlist: list[str] = field(default_factory=list)
    respect_git_boundary: bool = True
    recall_attachment_limit: int = 5
    tool_history_attachment_limit: int = 5
    recent_reads_attachment_limit: int = 5

    # Code-project binding for this turn, mirrored from
    # ``ToolContext.extra['project_roots']`` so prompt layers can
    # surface the active root without re-reading the engine config.
    project_roots: list[str] = field(default_factory=list)

    # registry reference for template lookups
    prompt_registry: Any = None

    # Persistent artifact metadata store for cross-turn awareness
    artifact_store: "SessionArtifactStore | None" = None

    # Ordered operation log for the current session
    operation_journal: "OperationJournal | None" = None


@runtime_checkable
class ContextSource(Protocol):
    """Protocol every context source must satisfy."""

    id: str
    kind: str  # "identity" | "state"
    scope: ContextScope
    priority: int
    weight: float
    render_target: RenderTarget

    def invalidation_key(self, ctx: ResolveContext) -> str:
        """Return a cache key; same key = same output."""
        ...

    async def resolve(self, ctx: ResolveContext) -> ContextBlock | None:
        """Produce the block or ``None`` to skip."""
        ...
