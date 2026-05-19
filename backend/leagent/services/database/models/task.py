"""Task model for background job tracking.

Modeled after the reference Task.ts / tasks.ts architecture:
- Typed task statuses with terminal-state helper
- Prefixed task ID generation (type-prefix + random suffix)
- TaskContext with abort controller for cancellation
- Output file tracking for streaming task logs
"""

from __future__ import annotations

import asyncio
import os
import secrets
import string
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel, Text

from leagent.services.database.models.base import BaseModel


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """Task execution status (mirrors reference TaskStatus)."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    KILLED = "killed"
    TIMEOUT = "timeout"


class TaskPriority(str, Enum):
    """Task priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskType(str, Enum):
    """Task type classification (extended to match reference types)."""

    AGENT = "agent"
    SHELL = "shell"
    WORKFLOW = "workflow"
    TOOL = "tool"
    CRON = "cron"
    BATCH = "batch"
    IMPORT = "import"
    EXPORT = "export"
    MONITOR = "monitor"
    DREAM = "dream"


# ---------------------------------------------------------------------------
# Terminal-state helper (mirrors reference isTerminalTaskStatus)
# ---------------------------------------------------------------------------

_TERMINAL_STATUSES = frozenset({
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.KILLED,
    TaskStatus.TIMEOUT,
})


def is_terminal_task_status(status: TaskStatus) -> bool:
    """True when a task is in a terminal state and will not transition further.

    Guards against injecting messages into dead tasks, evicting finished tasks
    from active state, and orphan-cleanup paths.
    """
    return status in _TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# Prefixed task ID generation (mirrors reference generateTaskId)
# ---------------------------------------------------------------------------

_TASK_ID_PREFIXES: dict[str, str] = {
    TaskType.SHELL.value: "b",
    TaskType.AGENT.value: "a",
    TaskType.WORKFLOW.value: "w",
    TaskType.TOOL.value: "t",
    TaskType.CRON.value: "c",
    TaskType.BATCH.value: "h",
    TaskType.IMPORT.value: "i",
    TaskType.EXPORT.value: "e",
    TaskType.MONITOR.value: "m",
    TaskType.DREAM.value: "d",
}

_TASK_ID_ALPHABET = string.digits + string.ascii_lowercase  # 36 chars


def generate_task_id(task_type: TaskType, *, length: int = 8) -> str:
    """Generate a short, typed, collision-resistant task ID.

    Format: <type-prefix><random-suffix>  (e.g. ``a3kf82nx`` for an agent task).
    36^8 ≈ 2.8 trillion combinations.
    """
    prefix = _TASK_ID_PREFIXES.get(task_type.value, "x")
    suffix = "".join(secrets.choice(_TASK_ID_ALPHABET) for _ in range(length))
    return f"{prefix}{suffix}"


# ---------------------------------------------------------------------------
# TaskContext (mirrors reference TaskContext with abort controller)
# ---------------------------------------------------------------------------


class TaskContext:
    """Runtime context for an executing task.

    Carries an ``abort_event`` (Python equivalent of AbortController),
    mutable state accessors, and an optional output file path for streaming
    task logs/output.
    """

    __slots__ = (
        "task_id",
        "task_type",
        "abort_event",
        "output_file",
        "output_offset",
        "_state",
    )

    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        *,
        output_dir: str | None = None,
    ) -> None:
        self.task_id = task_id
        self.task_type = task_type
        self.abort_event = asyncio.Event()
        self.output_file = _get_task_output_path(task_id, output_dir)
        self.output_offset: int = 0
        self._state: dict[str, Any] = {}

    @property
    def is_aborted(self) -> bool:
        return self.abort_event.is_set()

    def abort(self) -> None:
        self.abort_event.set()

    def get_state(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        self._state[key] = value

    def append_output(self, text: str) -> None:
        """Append text to the task's output file."""
        try:
            os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
            with open(self.output_file, "a", encoding="utf-8") as f:
                f.write(text)
            self.output_offset += len(text.encode("utf-8"))
        except OSError:
            pass


def _get_task_output_path(task_id: str, output_dir: str | None = None) -> str:
    """Return the output file path for a task (mirrors reference getTaskOutputPath)."""
    base = output_dir or os.path.join(os.getcwd(), ".leagent", "tasks")
    return os.path.join(base, f"{task_id}.log")


# ---------------------------------------------------------------------------
# createTaskStateBase factory (mirrors reference createTaskStateBase)
# ---------------------------------------------------------------------------


def create_task_state_base(
    task_type: TaskType,
    description: str,
    *,
    tool_use_id: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Create the base state dict for a new task (mirrors reference)."""
    task_id = generate_task_id(task_type)
    return {
        "id": task_id,
        "type": task_type.value,
        "status": TaskStatus.PENDING.value,
        "description": description,
        "tool_use_id": tool_use_id,
        "start_time": datetime.utcnow().isoformat(),
        "end_time": None,
        "total_paused_ms": 0,
        "output_file": _get_task_output_path(task_id, output_dir),
        "output_offset": 0,
        "notified": False,
    }


# ---------------------------------------------------------------------------
# SQLModel schemas
# ---------------------------------------------------------------------------


class TaskBase(SQLModel):
    """Base task fields."""

    name: str = Field(max_length=200)
    task_type: TaskType = Field(default=TaskType.AGENT)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    priority: TaskPriority = Field(default=TaskPriority.NORMAL)
    description: Optional[str] = Field(default=None, max_length=2000)


class Task(TaskBase, BaseModel, table=True):
    """Task database model."""

    __tablename__ = "tasks"

    # Association
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)
    flow_id: Optional[UUID] = Field(default=None, foreign_key="flows.id", index=True)
    session_id: Optional[UUID] = Field(default=None, index=True)

    # Input/output data (JSON)
    input_data: Optional[str] = Field(default=None, sa_column=Column(Text))
    output_data: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Execution details
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    duration_ms: Optional[int] = Field(default=None)

    # Progress tracking (0-100)
    progress: int = Field(default=0)
    progress_message: Optional[str] = Field(default=None, max_length=500)

    # Error handling
    error: Optional[str] = Field(default=None, sa_column=Column(Text))
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)
    last_retry_at: Optional[datetime] = Field(default=None)

    # Scheduling
    scheduled_at: Optional[datetime] = Field(default=None)
    timeout_seconds: int = Field(default=300)

    # Resource tracking
    model_used: Optional[str] = Field(default=None, max_length=100)
    tokens_used: Optional[int] = Field(default=None)
    cost: Optional[float] = Field(default=None)

    # Execution context (JSON)
    context: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Parent task for hierarchical execution
    parent_id: Optional[UUID] = Field(default=None, foreign_key="tasks.id")

    # Output file for streaming logs (mirrors reference outputFile)
    output_file: Optional[str] = Field(default=None, max_length=500)
    output_offset: int = Field(default=0)

    # Notification flag (mirrors reference notified)
    notified: bool = Field(default=False)

    # Pause tracking (mirrors reference totalPausedMs)
    total_paused_ms: int = Field(default=0)


class TaskCreate(TaskBase):
    """Schema for creating a task."""

    flow_id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    input_data: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    timeout_seconds: int = 300


class TaskUpdate(SQLModel):
    """Schema for updating a task."""

    status: Optional[TaskStatus] = None
    progress: Optional[int] = None
    progress_message: Optional[str] = None
    output_data: Optional[str] = None
    error: Optional[str] = None


class TaskRead(TaskBase):
    """Schema for reading a task."""

    id: UUID
    user_id: Optional[UUID]
    flow_id: Optional[UUID]
    session_id: Optional[UUID]
    progress: int
    progress_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    error: Optional[str]
    output_file: Optional[str]
    notified: bool
    parent_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime
