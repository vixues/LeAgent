"""Durable agent-run debug/eval traces (separate from checkpoints & chat SSOT)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field

from leagent.db.models.base import BaseModel, utc_now


class AgentTrace(BaseModel, table=True):
    """One row per :class:`~leagent.runtime.execution_run.ExecutionRun`."""

    __tablename__ = "agent_traces"

    trace_id: str = Field(index=True, unique=True, max_length=64)
    parent_trace_id: Optional[str] = Field(default=None, index=True, max_length=64)
    session_id: Optional[str] = Field(default=None, index=True, max_length=100)
    user_id: Optional[str] = Field(default=None, index=True, max_length=100)
    scope: str = Field(default="chat_turn", index=True, max_length=32)
    agent_name: str = Field(default="", max_length=200)
    model: str = Field(default="", index=True, max_length=200)
    status: str = Field(default="running", index=True, max_length=32)
    terminal_reason: Optional[str] = Field(default=None, max_length=64)
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: Optional[datetime] = Field(default=None)
    latency_ms: float = Field(default=0.0)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    cache_read_tokens: int = Field(default=0)
    cache_miss_tokens: int = Field(default=0)
    total_cost_usd: float = Field(default=0.0)
    tool_call_count: int = Field(default=0)
    llm_call_count: int = Field(default=0)
    experiment_id: Optional[str] = Field(default=None, index=True, max_length=64)
    prompt_hash: Optional[str] = Field(default=None, max_length=64)
    tags: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    error: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    scores: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    root_span_id: Optional[str] = Field(default=None, max_length=64)


class AgentTraceSpan(BaseModel, table=True):
    """Append-only span within an agent trace."""

    __tablename__ = "agent_trace_spans"

    span_id: str = Field(index=True, max_length=64)
    parent_span_id: Optional[str] = Field(default=None, index=True, max_length=64)
    trace_id: str = Field(index=True, max_length=64)
    seq: int = Field(default=0, index=True)
    kind: str = Field(default="event", index=True, max_length=32)
    name: str = Field(default="", max_length=300)
    status: str = Field(default="ok", max_length=32)
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: Optional[datetime] = Field(default=None)
    latency_ms: float = Field(default=0.0)
    attrs: Optional[str] = Field(default=None, sa_column=Column(Text))
    input_preview: Optional[str] = Field(default=None, sa_column=Column(Text))
    output_preview: Optional[str] = Field(default=None, sa_column=Column(Text))
    payload_ref: Optional[str] = Field(default=None, max_length=500)


class AgentTraceExperiment(BaseModel, table=True):
    """Same-prompt multi-model comparison experiment."""

    __tablename__ = "agent_trace_experiments"

    experiment_id: str = Field(index=True, unique=True, max_length=64)
    name: str = Field(default="", max_length=200)
    prompt: str = Field(default="", sa_column=Column(Text))
    session_id: Optional[str] = Field(default=None, index=True, max_length=100)
    model_ids: str = Field(default="[]", sa_column=Column(Text))
    created_by: Optional[str] = Field(default=None, max_length=100)
    status: str = Field(default="pending", index=True, max_length=32)
    error: Optional[str] = Field(default=None, sa_column=Column(Text))


__all__ = ["AgentTrace", "AgentTraceSpan", "AgentTraceExperiment"]
