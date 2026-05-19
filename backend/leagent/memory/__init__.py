"""Agent memory package for LeAgent.

This package hosts the cognitive memory stack used by the agent runtime —
**not** the conversation transcript (that lives in
:mod:`leagent.services.session`).

The module is organised around three kinds of long-lived memory, plus a
short-lived scratchpad and a retrieval pipeline:

* :class:`~leagent.memory.episodic.EpisodicStore` — "what happened in
  past turns": one row per user/assistant turn with a distilled summary.
* :class:`~leagent.memory.semantic.SemanticStore` — stable facts and
  preferences the agent should remember about the user / workspace.
* :class:`~leagent.memory.procedural.ProceduralStore` — outcomes of
  structured procedures (tool chains, workflows) keyed by a canonical
  signature, so the agent can re-use what worked before.
* :class:`~leagent.memory.working_scratchpad.WorkingScratchpad` —
  ephemeral, per-task Redis scratchpad (tool history, reasoning notes).
* :class:`~leagent.memory.recall.RetrievalPipeline` — hybrid
  semantic / lexical recall over the three cognitive stores.
* :class:`~leagent.memory.agent_memory.AgentMemory` — the public façade
  the agent runtime consumes. Everything else is an implementation detail.

All of the above are built incrementally by the tasks in the
``session-manager-redis-upgrade`` plan. This ``__init__`` re-exports them
as they land so downstream callers keep a single import site.
"""

from __future__ import annotations

from leagent.memory.agent_memory import AgentMemory, RecallHandle
from leagent.memory.embeddings import (
    EmbeddingProvider,
    LLMServiceEmbeddingProvider,
    NullEmbeddingProvider,
)
from leagent.memory.episodic import EpisodicStore
from leagent.memory.formation import (
    FormationDecision,
    FormationPolicy,
    FormationTarget,
    TriggerKind,
    TurnObservation,
)
from leagent.memory.procedural import ProceduralStore, build_signature
from leagent.memory.recall import RecallOptions, RetrievalPipeline
from leagent.memory.semantic import SemanticStore
from leagent.memory.types import (
    Episode,
    Fact,
    MemoryKind,
    Procedure,
    RecallBundle,
    RecallEntry,
)
from leagent.memory.working_scratchpad import ToolInvocation, WorkingScratchpad

__all__ = [
    "AgentMemory",
    "EmbeddingProvider",
    "Episode",
    "EpisodicStore",
    "Fact",
    "FormationDecision",
    "FormationPolicy",
    "FormationTarget",
    "LLMServiceEmbeddingProvider",
    "MemoryKind",
    "NullEmbeddingProvider",
    "Procedure",
    "ProceduralStore",
    "RecallBundle",
    "RecallEntry",
    "RecallHandle",
    "RecallOptions",
    "RetrievalPipeline",
    "SemanticStore",
    "ToolInvocation",
    "TriggerKind",
    "TurnObservation",
    "WorkingScratchpad",
    "build_signature",
]

try:
    from leagent.memory.compact import build_autocompact, build_microcompact

    __all__ += ["build_autocompact", "build_microcompact"]
except ImportError:  # pragma: no cover
    pass
