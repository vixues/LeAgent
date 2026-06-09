"""SQLModel database models for cron jobs and executions."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel, Text

from leagent.db.models.base import BaseModel


class CronJobModel(BaseModel, table=True):
    """Persistent storage for cron job definitions."""

    __tablename__ = "cron_jobs"

    name: str = Field(index=True, max_length=200)
    description: str = Field(default="", max_length=500)
    schedule: str = Field(max_length=100)
    target_type: str = Field(default="workflow", max_length=50)
    target_id: Optional[str] = Field(default=None, max_length=255)
    workflow_id: Optional[str] = Field(default=None, max_length=255)

    enabled: bool = Field(default=True)
    status: str = Field(default="active", max_length=50)

    payload: Optional[str] = Field(default=None, sa_column=Column(Text))
    timeout_sec: int = Field(default=3600)
    max_retries: int = Field(default=3)
    retry_delay_sec: int = Field(default=60)

    timezone: str = Field(default="UTC", max_length=50)
    coalesce: bool = Field(default=True)
    max_instances: int = Field(default=1)
    misfire_grace_sec: int = Field(default=300)

    channel_ids: Optional[str] = Field(default=None, sa_column=Column(Text))
    notify_on_start: bool = Field(default=False)
    notify_on_complete: bool = Field(default=True)
    notify_on_fail: bool = Field(default=True)

    last_run_at: Optional[datetime] = Field(default=None)
    next_run_at: Optional[datetime] = Field(default=None)
    last_run_status: Optional[str] = Field(default=None, max_length=50)
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text))

    run_count: int = Field(default=0)
    success_count: int = Field(default=0)
    error_count: int = Field(default=0)
    consecutive_failures: int = Field(default=0)

    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)
    tags: Optional[str] = Field(default=None, max_length=500)
    meta: Optional[str] = Field(default=None, sa_column=Column(Text))
    version: int = Field(default=1)


class CronExecutionModel(SQLModel, table=True):
    """Persistent storage for cron execution records."""

    __tablename__ = "cron_executions"

    id: UUID = Field(primary_key=True)
    job_id: UUID = Field(foreign_key="cron_jobs.id", index=True)
    job_name: str = Field(default="", max_length=200)
    execution_number: int = Field(default=0)

    status: str = Field(default="pending", max_length=50, index=True)
    trigger_type: str = Field(default="scheduled", max_length=50)

    scheduled_at: Optional[datetime] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    workflow_id: Optional[str] = Field(default=None, max_length=255)
    workflow_state_id: Optional[UUID] = Field(default=None)

    inputs: Optional[str] = Field(default=None, sa_column=Column(Text))
    outputs: Optional[str] = Field(default=None, sa_column=Column(Text))

    error: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_type: Optional[str] = Field(default=None, max_length=100)
    stack_trace: Optional[str] = Field(default=None, sa_column=Column(Text))

    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    duration_ms: int = Field(default=0)
    node_count: int = Field(default=0)

    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class CronJobRead(SQLModel):
    """Read schema for cron jobs."""

    id: UUID
    name: str
    description: str
    schedule: str
    target_type: str
    target_id: Optional[str]
    workflow_id: Optional[str]
    enabled: bool
    status: str
    timeout_sec: int
    max_retries: int
    timezone: str
    notify_on_start: bool
    notify_on_complete: bool
    notify_on_fail: bool
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    last_run_status: Optional[str]
    last_error: Optional[str]
    run_count: int
    success_count: int
    error_count: int
    user_id: Optional[UUID]
    tags: Optional[str]
    created_at: datetime
    updated_at: datetime
    version: int
