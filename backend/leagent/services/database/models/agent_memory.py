"""SQLModel ORM tables for the agent memory stack.

The agent memory stack (``leagent.memory``) owns three durable stores that
each correspond to one of these tables:

* :class:`AgentEpisode` — one row per past user/assistant turn. The
  episodic store summarises what happened and persists the summary here so
  the agent can recall it on later turns.
* :class:`AgentFact` — stable user/workspace-level facts or preferences
  ("Prefers metric units", "Works in the Shanghai office"). Semantic store
  upserts these through :meth:`SemanticStore.upsert_fact`.
* :class:`AgentProcedure` — outcomes of multi-step tool chains or
  workflows, keyed by a canonical signature. The procedural store writes a
  record every time a workflow finishes, then recalls the best scoring
  match when a similar task shows up.

Every row carries an embedding reference (``vector_id``) that points into a
Milvus collection; the raw vectors live out-of-process. Keeping the text /
metadata / embedding IDs in Postgres gives us a durable index even when
Milvus is cold.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel, Text, UniqueConstraint

from leagent.services.database.models.base import BaseModel


class AgentEpisode(BaseModel, table=True):
    """One past-turn episode the agent may recall in the future.

    The ``session_id`` is required and indexed so recall can scope to a
    single conversation. The ``embedding_id`` is populated by the episodic
    store after Milvus upsert; ``summary`` is the dense text the recall
    pipeline scores against in the BM25 / ILIKE fallback path.
    """

    __tablename__ = "agent_episodes"

    session_id: UUID = Field(foreign_key="chat_sessions.id", index=True, nullable=False)
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)
    flow_id: Optional[UUID] = Field(default=None, foreign_key="flows.id", index=True)

    # The distilled text; short (<~1 KB) by convention.
    summary: str = Field(sa_column=Column(Text, nullable=False))
    # Full transcript snapshot for reference / auditing; may be large.
    transcript: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Structured tags for lexical filtering (intent, topic, artefacts…).
    tags: Optional[str] = Field(default=None, sa_column=Column(Text))  # JSON

    # Milvus vector reference (collection row id). ``None`` means the vector
    # write failed — the row is still usable by the lexical fallback.
    vector_id: Optional[str] = Field(default=None, max_length=128, index=True)
    embedding_model: Optional[str] = Field(default=None, max_length=100)

    # Quality signal for recency+quality ranking.
    importance: float = Field(default=0.0, nullable=False)
    # Token count of the summary, used when budgeting recall into a prompt.
    token_count: Optional[int] = Field(default=None)
    # Recall counters — incremented by ``RetrievalPipeline`` to inform
    # ``importance`` over time.
    recall_count: int = Field(default=0, nullable=False)
    last_recalled_at: Optional[datetime] = Field(default=None)


class AgentFact(BaseModel, table=True):
    """A durable semantic fact the agent should remember.

    Facts are scoped to a single user and optionally a workspace. The
    ``(user_id, workspace_id, key)`` tuple is a natural upsert key — writing
    a new value for the same key replaces the previous row.
    """

    __tablename__ = "agent_facts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "workspace_id",
            "key",
            name="uq_agent_facts_user_workspace_key",
        ),
    )

    user_id: UUID = Field(foreign_key="users.id", index=True, nullable=False)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)

    # Stable, application-defined slug (e.g. "preferences.units",
    # "contact.default_email"). Human-readable by convention.
    key: str = Field(max_length=200, nullable=False, index=True)
    # Free-form natural-language value.
    value: str = Field(sa_column=Column(Text, nullable=False))

    # Confidence score in the range [0, 1]. Facts below a threshold are
    # treated as "hints" rather than authoritative memory.
    confidence: float = Field(default=0.8, nullable=False)
    # Free-form source label (e.g. "user_stated", "inferred",
    # "tool:calendar_sync").
    source: Optional[str] = Field(default=None, max_length=100)

    vector_id: Optional[str] = Field(default=None, max_length=128, index=True)
    embedding_model: Optional[str] = Field(default=None, max_length=100)


class AgentProcedure(BaseModel, table=True):
    """Outcome of a tool chain / workflow execution.

    ``signature`` is a canonical hash of "what the procedure did" —
    typically ``sha256(task_kind + sorted(tool_names))`` — so similar tasks
    collapse onto the same row even if their parameters differ. Each invocation
    bumps ``run_count`` and updates the success stats, giving the agent a
    cheap heuristic for "have I done this before, and did it work?"
    """

    __tablename__ = "agent_procedures"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "workspace_id",
            "signature",
            name="uq_agent_procedures_user_workspace_signature",
        ),
    )

    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)

    # Human-readable label for debugging and LLM rendering.
    name: str = Field(max_length=200, nullable=False)
    # Stable hash (hex) that groups equivalent procedures.
    signature: str = Field(max_length=128, nullable=False, index=True)
    # The LLM-facing description of the procedure (inputs, tools, notes).
    description: str = Field(sa_column=Column(Text, nullable=False))

    # Success stats — written on every recording.
    run_count: int = Field(default=0, nullable=False)
    success_count: int = Field(default=0, nullable=False)
    # Short task-output snippet from hooks (up to ~200 chars today); use Text
    # so future summaries are not capped by an arbitrary VARCHAR limit.
    last_outcome: Optional[str] = Field(default=None, sa_column=Column(Text))
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text))
    last_duration_ms: Optional[int] = Field(default=None)
    last_run_at: Optional[datetime] = Field(default=None)

    vector_id: Optional[str] = Field(default=None, max_length=128, index=True)
    embedding_model: Optional[str] = Field(default=None, max_length=100)


# Explicit ORM-only SQLModel classes. SQLModel auto-registers them with the
# metadata when imported, which is what alembic's ``env.py`` relies on.
__all__ = [
    "AgentEpisode",
    "AgentFact",
    "AgentProcedure",
]
