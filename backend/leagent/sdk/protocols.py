"""Core SDK protocols — behavioural contracts for every subsystem pillar.

These ``Protocol`` definitions are the *only* types that upper-layer SDK
code depends on. Concrete implementations live in the subsystem packages
(``leagent.llm``, ``leagent.context``, ``leagent.memory``, etc.) and are
wired via :class:`~leagent.sdk.RuntimeContext`.  Any object that
structurally matches the protocol can be substituted (e.g. test doubles,
alternate backends).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    runtime_checkable,
)
from uuid import UUID

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from leagent.context.file_state import FileState as FileStateCache
    from leagent.llm.base import (
        ChatMessage,
        EmbeddingResponse,
        LLMResponse,
        StreamChunk,
        ToolDefinition,
    )
    from leagent.memory.types import (
        Episode,
        Fact,
        Procedure,
        RecallBundle,
        RecallEntry,
    )


# ── LLM pillar ─────────────────────────────────────────────────────────


@runtime_checkable
class LLMClient(Protocol):
    """High-level LLM facade consumed by the agent kernel.

    Maps to :class:`leagent.llm.service.LLMService`.
    """

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        task: str = "chat",
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        task: str = "chat",
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]: ...

    async def embed(
        self,
        texts: list[str],
        *,
        provider: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse: ...

    def count_tokens(self, text: str) -> int: ...

    def count_message_tokens(self, messages: list[ChatMessage]) -> int: ...


@runtime_checkable
class Provider(Protocol):
    """Single LLM provider (OpenAI, Anthropic, Ollama, …).

    Maps to :class:`leagent.llm.base.LLMProvider`.
    """

    name: str
    supports_streaming: bool
    supports_tools: bool
    supports_embeddings: bool

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]: ...

    async def health_check(self) -> bool: ...


# ── Context pillar ──────────────────────────────────────────────────────


@dataclass
class AssemblyRequest:
    """Narrow input to :class:`ContextAssembler`.

    Replaces the 25-field ``ResolveContext`` for SDK-layer callers.
    The concrete ``ContextManager`` may still accept the full
    ``ResolveContext`` internally via ``services``.
    """

    query: str = ""
    task_id: UUID | None = None
    session_id: UUID | None = None
    user_id: UUID | None = None
    agent_id: str = "default"
    cwd: str = "."
    persona_override: str = ""
    append_extra: str = ""
    workflow_hint: str = ""
    template_vars: dict[str, Any] = field(default_factory=dict)
    project_roots: list[str] = field(default_factory=list)
    max_budget_chars: int | None = None
    max_budget_tokens: int | None = None
    services: Any = None


@dataclass
class AssemblyResult:
    """Output of :meth:`ContextAssembler.assemble`."""

    system_prompt: str = ""
    attachment_messages: list[dict[str, Any]] = field(default_factory=list)
    token_estimate: int = 0
    source_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ContextAssembler(Protocol):
    """Protocol for per-turn context assembly.

    Maps to :class:`leagent.context.manager.ContextManager`.
    """

    async def assemble(self, request: AssemblyRequest) -> AssemblyResult: ...


# ── Memory pillar ───────────────────────────────────────────────────────


@runtime_checkable
class RecallProvider(Protocol):
    """Background memory-recall handle interface.

    Implementations kick off recall in the background via :meth:`start`
    while the model is generating, then resolve it via :meth:`consume`
    right before the system prompt is composed.
    """

    def start(
        self,
        query: str,
        *,
        recall_anchor: str | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 8,
        per_store_limit: int = 4,
        file_state: FileStateCache | None = None,
    ) -> None: ...

    async def consume(self) -> RecallBundle: ...

    def cancel(self) -> None: ...


@runtime_checkable
class EpisodicStoreProtocol(Protocol):
    """Episodic memory store contract."""

    async def record(self, episode: Episode) -> Episode: ...
    async def delete(self, episode_id: UUID) -> None: ...
    async def list_recent(
        self,
        *,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        limit: int = 20,
    ) -> list[Episode]: ...
    async def lexical_search(
        self,
        query: str,
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        limit: int = 5,
    ) -> list[RecallEntry]: ...
    async def semantic_search(
        self,
        vector: list[float],
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        limit: int = 5,
    ) -> list[RecallEntry]: ...


@runtime_checkable
class SemanticStoreProtocol(Protocol):
    """Semantic (fact) memory store contract."""

    async def upsert(self, fact: Fact) -> Fact: ...
    async def delete(self, fact_id: UUID) -> None: ...
    async def get_by_key(
        self,
        *,
        user_id: UUID,
        key: str,
        workspace_id: UUID | None = None,
    ) -> Fact | None: ...
    async def lexical_search(
        self,
        query: str,
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 5,
    ) -> list[RecallEntry]: ...
    async def semantic_search(
        self,
        vector: list[float],
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 5,
    ) -> list[RecallEntry]: ...


@runtime_checkable
class ProceduralStoreProtocol(Protocol):
    """Procedural memory store contract."""

    async def record(
        self,
        procedure: Procedure,
        *,
        outcome: str,
        success: bool,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> Procedure: ...
    async def get_by_signature(
        self,
        signature: str,
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> Procedure | None: ...
    async def lexical_search(
        self,
        query: str,
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 5,
    ) -> list[RecallEntry]: ...
    async def semantic_search(
        self,
        vector: list[float],
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 5,
    ) -> list[RecallEntry]: ...


@runtime_checkable
class MemoryStore(Protocol):
    """Unified agent memory facade.

    Maps to :class:`leagent.memory.agent_memory.AgentMemory`.
    """

    async def record_episode(self, episode: Episode) -> Episode: ...

    async def upsert_fact(self, fact: Fact) -> Fact: ...

    async def record_procedure(
        self,
        procedure: Procedure,
        *,
        outcome: str,
        success: bool,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> Procedure: ...

    async def recall(
        self,
        query: str,
        *,
        recall_anchor: str | None = None,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 8,
        per_store_limit: int = 4,
        include_episodic: bool = True,
        include_semantic: bool = True,
        include_procedural: bool = True,
        file_state: FileStateCache | None = None,
    ) -> RecallBundle: ...


# ── Checkpoint / durable execution ──────────────────────────────────────


@dataclass
class Checkpoint:
    """Snapshot of a run's state at a turn boundary.

    Enables LangGraph-style interrupt → resume without losing progress.
    """

    checkpoint_id: str
    session_id: str
    agent_name: str
    turn: int
    messages: list[dict[str, Any]] = field(default_factory=list)
    reason: str = "awaiting_user_input"
    usage: dict[str, int] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class CheckpointStore(Protocol):
    """Persistence backend for run checkpoints."""

    async def save(self, checkpoint: Checkpoint) -> None: ...
    async def load(self, checkpoint_id: str) -> Checkpoint | None: ...
    async def delete(self, checkpoint_id: str) -> None: ...
    async def list_for_session(self, session_id: str) -> list[Checkpoint]: ...


# ── Kernel context types ────────────────────────────────────────────────


@dataclass
class RunContext:
    """Per-run context available inside the kernel loop.

    Replaces the ad-hoc ``ToolUseContext`` + ``AgentContext`` duck-typing
    with an explicit, documented object.
    """

    abort_event: asyncio.Event
    session_id: UUID | None = None
    user_id: UUID | None = None
    task_id: UUID | None = None
    agent_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def aborted(self) -> bool:
        return self.abort_event.is_set()

    def raise_if_aborted(self) -> None:
        if self.aborted:
            raise asyncio.CancelledError("run aborted")


@dataclass
class ToolContext:
    """Subset of :class:`RunContext` exposed to individual tool executions.

    Provides a stable, narrow contract between the kernel and tool
    implementations so tools never depend on the full run state.
    """

    abort_event: asyncio.Event
    session_id: UUID | None = None
    user_id: UUID | None = None
    task_id: UUID | None = None
    agent_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_run_context(cls, run: RunContext) -> ToolContext:
        return cls(
            abort_event=run.abort_event,
            session_id=run.session_id,
            user_id=run.user_id,
            task_id=run.task_id,
            agent_id=run.agent_id,
            extra=dict(run.extra),
        )

    @property
    def aborted(self) -> bool:
        return self.abort_event.is_set()

    def raise_if_aborted(self) -> None:
        if self.aborted:
            raise asyncio.CancelledError("tool execution aborted")


__all__ = [
    "AssemblyRequest",
    "AssemblyResult",
    "Checkpoint",
    "CheckpointStore",
    "ContextAssembler",
    "EpisodicStoreProtocol",
    "LLMClient",
    "MemoryStore",
    "ProceduralStoreProtocol",
    "Provider",
    "RecallProvider",
    "RunContext",
    "SemanticStoreProtocol",
    "ToolContext",
]
