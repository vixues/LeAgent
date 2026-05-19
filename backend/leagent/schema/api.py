"""API-facing Pydantic models for requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuildStatus(str, Enum):
    IDLE = "idle"
    BUILDING = "building"
    READY = "ready"
    ERROR = "error"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatSession(BaseModel):
    session_id: UUID
    user_id: UUID
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Task / Run
# ---------------------------------------------------------------------------

class RunResponse(BaseModel):
    run_id: UUID
    session_id: UUID
    status: TaskStatus = TaskStatus.RUNNING
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TaskResponse(BaseModel):
    task_id: UUID
    task_type: str
    status: TaskStatus
    progress: float = 0.0
    result: dict[str, Any] | None = None
    output_files: list[str] = Field(default_factory=list)
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    steps: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 20
    has_next: bool = False
    has_prev: bool = False


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ErrorResponse(BaseModel):
    error: bool = True
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    recovery: dict[str, Any] | None = None
