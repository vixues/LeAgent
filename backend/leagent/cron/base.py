"""Base types and models for the cron scheduling system.

This module provides foundational data structures for cron job management,
including job definitions, execution records, and status tracking.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class CronJobStatus(str, Enum):
    """Status of a cron job."""

    ACTIVE = "active"
    PAUSED = "paused"
    RUNNING = "running"
    FAILED = "failed"
    DISABLED = "disabled"


class CronJobType(str, Enum):
    """Type of cron job target."""

    WORKFLOW = "workflow"
    TASK = "task"
    WEBHOOK = "webhook"
    SCRIPT = "script"


class CronExecutionStatus(str, Enum):
    """Status of a cron job execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


class CronJob(BaseModel):
    """Definition of a scheduled cron job.

    Represents a recurring job that executes a workflow or task
    based on a cron expression schedule.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    schedule: str = Field(..., min_length=1, max_length=100)
    workflow_id: str | None = None
    target_type: CronJobType = CronJobType.WORKFLOW
    target_id: str | None = None
    enabled: bool = True
    status: CronJobStatus = CronJobStatus.ACTIVE

    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_sec: int = Field(default=3600, ge=1, le=86400)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay_sec: int = Field(default=60, ge=1, le=3600)

    timezone: str = Field(default="UTC", max_length=50)
    coalesce: bool = True
    max_instances: int = Field(default=1, ge=1, le=10)
    misfire_grace_sec: int = Field(default=300, ge=0, le=3600)

    channel_ids: list[str] = Field(default_factory=list)
    notify_on_start: bool = False
    notify_on_complete: bool = True
    notify_on_fail: bool = True

    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_run_status: CronExecutionStatus | None = None
    last_error: str | None = None

    run_count: int = 0
    success_count: int = 0
    error_count: int = 0
    consecutive_failures: int = 0

    user_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, v: str) -> str:
        """Validate cron expression format."""
        parts = v.strip().split()
        if len(parts) < 5 or len(parts) > 6:
            raise ValueError(
                f"Invalid cron expression: expected 5-6 parts, got {len(parts)}"
            )
        return v.strip()

    def should_run(self) -> bool:
        """Check if the job should be eligible for execution."""
        return (
            self.enabled
            and self.status == CronJobStatus.ACTIVE
            and self.consecutive_failures < self.max_retries + 1
        )

    def record_success(self) -> None:
        """Update job state after successful execution."""
        now = datetime.utcnow()
        self.last_run_at = now
        self.last_run_status = CronExecutionStatus.COMPLETED
        self.last_error = None
        self.run_count += 1
        self.success_count += 1
        self.consecutive_failures = 0
        self.updated_at = now

    def record_failure(self, error: str) -> None:
        """Update job state after failed execution."""
        now = datetime.utcnow()
        self.last_run_at = now
        self.last_run_status = CronExecutionStatus.FAILED
        self.last_error = error[:2000] if error else None
        self.run_count += 1
        self.error_count += 1
        self.consecutive_failures += 1
        self.updated_at = now

        if self.consecutive_failures > self.max_retries:
            self.status = CronJobStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = self.model_dump()
        data["id"] = str(self.id)
        if self.last_run_at:
            data["last_run_at"] = self.last_run_at.isoformat()
        if self.next_run_at:
            data["next_run_at"] = self.next_run_at.isoformat()
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CronJob:
        """Create from dictionary."""
        if isinstance(data.get("id"), str):
            data["id"] = UUID(data["id"])

        for dt_field in ("last_run_at", "next_run_at", "created_at", "updated_at"):
            if isinstance(data.get(dt_field), str):
                data[dt_field] = datetime.fromisoformat(data[dt_field])

        return cls(**data)


class CronExecution(BaseModel):
    """Record of a single cron job execution.

    Tracks the complete lifecycle of a job run including
    timing, status, outputs, and error information.
    """

    id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    job_name: str = ""
    execution_number: int = 0

    status: CronExecutionStatus = CronExecutionStatus.PENDING
    trigger_type: str = "scheduled"

    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    workflow_id: str | None = None
    workflow_state_id: UUID | None = None

    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)

    error: str | None = None
    error_type: str | None = None
    stack_trace: str | None = None

    retry_count: int = 0
    max_retries: int = 3

    duration_ms: int = 0
    node_count: int = 0

    channel_notifications: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def start(self) -> None:
        """Mark execution as started."""
        self.status = CronExecutionStatus.RUNNING
        self.started_at = datetime.utcnow()

    def complete(self, outputs: dict[str, Any] | None = None) -> None:
        """Mark execution as completed successfully."""
        self.status = CronExecutionStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if outputs:
            self.outputs = outputs
        self._calculate_duration()

    def fail(
        self,
        error: str,
        error_type: str | None = None,
        stack_trace: str | None = None,
    ) -> None:
        """Mark execution as failed."""
        self.status = CronExecutionStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error = error[:2000] if error else None
        self.error_type = error_type
        self.stack_trace = stack_trace[:5000] if stack_trace else None
        self._calculate_duration()

    def timeout(self) -> None:
        """Mark execution as timed out."""
        self.status = CronExecutionStatus.TIMEOUT
        self.completed_at = datetime.utcnow()
        self.error = "Execution timed out"
        self._calculate_duration()

    def skip(self, reason: str) -> None:
        """Mark execution as skipped."""
        self.status = CronExecutionStatus.SKIPPED
        self.completed_at = datetime.utcnow()
        self.error = reason
        self._calculate_duration()

    def _calculate_duration(self) -> None:
        """Calculate execution duration in milliseconds."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)

    @property
    def is_terminal(self) -> bool:
        """Check if execution is in a terminal state."""
        return self.status in (
            CronExecutionStatus.COMPLETED,
            CronExecutionStatus.FAILED,
            CronExecutionStatus.TIMEOUT,
            CronExecutionStatus.CANCELLED,
            CronExecutionStatus.SKIPPED,
        )

    @property
    def is_success(self) -> bool:
        """Check if execution completed successfully."""
        return self.status == CronExecutionStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = self.model_dump()
        data["id"] = str(self.id)
        data["job_id"] = str(self.job_id)
        if self.workflow_state_id:
            data["workflow_state_id"] = str(self.workflow_state_id)

        for dt_field in ("scheduled_at", "started_at", "completed_at"):
            if data.get(dt_field):
                data[dt_field] = data[dt_field].isoformat()

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CronExecution:
        """Create from dictionary."""
        for uuid_field in ("id", "job_id", "workflow_state_id"):
            if isinstance(data.get(uuid_field), str):
                data[uuid_field] = UUID(data[uuid_field])

        for dt_field in ("scheduled_at", "started_at", "completed_at"):
            if isinstance(data.get(dt_field), str):
                data[dt_field] = datetime.fromisoformat(data[dt_field])

        return cls(**data)


class CronJobStats(BaseModel):
    """Statistics for a cron job."""

    job_id: UUID
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    timed_out_runs: int = 0
    skipped_runs: int = 0

    average_duration_ms: float = 0.0
    min_duration_ms: int = 0
    max_duration_ms: int = 0

    last_7_days_runs: int = 0
    last_7_days_success_rate: float = 0.0

    first_run_at: datetime | None = None
    last_run_at: datetime | None = None

    @property
    def success_rate(self) -> float:
        """Calculate overall success rate."""
        if self.total_runs == 0:
            return 0.0
        return self.successful_runs / self.total_runs * 100


class CronHeartbeat(BaseModel):
    """Heartbeat record for cron system health monitoring."""

    id: UUID = Field(default_factory=uuid4)
    instance_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    active_jobs: int = 0
    running_jobs: int = 0
    pending_executions: int = 0

    scheduler_running: bool = False
    last_execution_at: datetime | None = None
    next_execution_at: datetime | None = None

    cpu_percent: float = 0.0
    memory_mb: float = 0.0

    errors_last_hour: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_healthy(self, max_age_sec: int = 60) -> bool:
        """Check if heartbeat is recent enough to be considered healthy."""
        age = (datetime.utcnow() - self.timestamp).total_seconds()
        return age <= max_age_sec
