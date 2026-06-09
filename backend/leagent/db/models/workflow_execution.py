"""SQLModel database models for workflow executions."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel, Text

from leagent.db.models.base import UUIDMixin


class WorkflowExecution(UUIDMixin, SQLModel, table=True):
    """Persistent record of a workflow execution run."""

    __tablename__ = "workflow_executions"

    flow_id: Optional[UUID] = Field(default=None, foreign_key="flows.id", index=True)
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id", index=True)
    cron_job_id: Optional[UUID] = Field(default=None, index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)

    prompt_id: Optional[str] = Field(default=None, max_length=100, index=True)
    graph_hash: Optional[str] = Field(default=None, max_length=128)
    priority: int = Field(default=5)

    status: str = Field(default="pending", max_length=50, index=True)
    trigger_type: str = Field(default="manual", max_length=50)

    inputs: Optional[str] = Field(default=None, sa_column=Column(Text))
    outputs: Optional[str] = Field(default=None, sa_column=Column(Text))
    execution_history: Optional[str] = Field(default=None, sa_column=Column(Text))

    current_node: Optional[str] = Field(default=None, max_length=200)
    node_count: int = Field(default=0)
    error: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_stack: Optional[str] = Field(default=None, sa_column=Column(Text))

    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    duration_ms: int = Field(default=0)

    workflow_state_id: Optional[UUID] = Field(default=None)
    retry_count: int = Field(default=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class WorkflowExecutionRead(SQLModel):
    """Read schema for workflow executions."""

    id: UUID
    flow_id: Optional[UUID]
    user_id: Optional[UUID]
    cron_job_id: Optional[UUID]
    prompt_id: Optional[str]
    graph_hash: Optional[str]
    priority: int
    status: str
    trigger_type: str
    inputs: Optional[str]
    outputs: Optional[str]
    current_node: Optional[str]
    node_count: int
    error: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: int
    created_at: datetime
    updated_at: datetime
