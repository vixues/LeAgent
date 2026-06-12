"""Durable workflow run snapshots for pause/resume across process restarts."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel, Text

from leagent.db.models.base import UUIDMixin


class WorkflowStateSnapshot(UUIDMixin, SQLModel, table=True):
    """Serialized :class:`~leagent.workflow.base.WorkflowState` + run context."""

    __tablename__ = "workflow_state_snapshots"

    state_id: UUID = Field(index=True, unique=True)
    execution_id: Optional[UUID] = Field(default=None, index=True)
    prompt_id: Optional[str] = Field(default=None, max_length=100, index=True)
    status: str = Field(default="paused", max_length=50)
    payload: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
