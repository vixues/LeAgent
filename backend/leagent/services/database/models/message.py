"""Message model for chat conversations."""

from datetime import datetime
from enum import Enum
import json
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from pydantic import field_validator
from sqlmodel import Column, Field, Relationship, SQLModel, Text

from leagent.services.database.models.base import BaseModel

if TYPE_CHECKING:
    from leagent.services.database.models.flow import Flow


def _parse_json_text(value: Any) -> Any:
    """Accept already-structured API values and JSON text from DB rows."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


class MessageRole(str, Enum):
    """Message sender role."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageStatus(str, Enum):
    """Message processing status."""

    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageBase(SQLModel):
    """Base message fields."""

    role: MessageRole = Field(default=MessageRole.USER)
    content: str = Field(sa_column=Column(Text))
    status: MessageStatus = Field(default=MessageStatus.COMPLETED)


class Message(MessageBase, BaseModel, table=True):
    """Message database model."""

    __tablename__ = "messages"

    # Session association
    session_id: UUID = Field(index=True)
    flow_id: Optional[UUID] = Field(default=None, foreign_key="flows.id", index=True)
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)

    # For assistant messages: which model generated it
    model: Optional[str] = Field(default=None, max_length=100)

    # Tool call information (JSON)
    tool_calls: Optional[str] = Field(default=None, sa_column=Column(Text))
    tool_call_id: Optional[str] = Field(default=None, max_length=100)

    # Attachments (JSON list of file references)
    attachments: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Structured UI payloads (e.g. chat_workflow card JSON)
    extensions: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Token usage
    input_tokens: Optional[int] = Field(default=None)
    output_tokens: Optional[int] = Field(default=None)
    total_tokens: Optional[int] = Field(default=None)

    # Execution time in milliseconds
    latency_ms: Optional[int] = Field(default=None)

    # Error information if failed
    error: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Feedback
    rating: Optional[int] = Field(default=None)  # 1-5
    feedback: Optional[str] = Field(default=None, max_length=2000)

    # Parent message (for threading)
    parent_id: Optional[UUID] = Field(default=None, foreign_key="messages.id")

    # Relationships
    flow: Optional["Flow"] = Relationship(back_populates="messages")


class ChatSession(BaseModel, table=True):
    """Chat session for grouping messages."""

    __tablename__ = "chat_sessions"

    name: Optional[str] = Field(default=None, max_length=200)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    flow_id: Optional[UUID] = Field(default=None, foreign_key="flows.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)
    is_active: bool = Field(default=True)
    message_count: int = Field(default=0)
    last_message_at: Optional[datetime] = Field(default=None)

    # Session metadata (JSON)
    session_metadata: Optional[str] = Field(default=None, sa_column=Column(Text))


class MessageCreate(SQLModel):
    """Schema for creating a message."""

    session_id: UUID
    role: MessageRole = MessageRole.USER
    content: str
    flow_id: Optional[UUID] = None
    attachments: Optional[str] = None


class MessageRead(MessageBase):
    """Schema for reading a message."""

    id: UUID
    session_id: UUID
    flow_id: Optional[UUID]
    user_id: Optional[UUID]
    model: Optional[str]
    tool_calls: Optional[list[dict[str, Any]]]
    attachments: Optional[list[Any]]
    extensions: Optional[dict[str, Any]]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    total_tokens: Optional[int] = None
    latency_ms: Optional[int]
    rating: Optional[int] = None
    created_at: datetime

    @field_validator("tool_calls", mode="before")
    @classmethod
    def _parse_tool_calls(cls, value: Any) -> list[dict[str, Any]] | None:
        parsed = _parse_json_text(value)
        if not isinstance(parsed, list):
            return None
        return [item for item in parsed if isinstance(item, dict)]

    @field_validator("attachments", mode="before")
    @classmethod
    def _parse_attachments(cls, value: Any) -> list[Any] | None:
        parsed = _parse_json_text(value)
        return parsed if isinstance(parsed, list) else None

    @field_validator("extensions", mode="before")
    @classmethod
    def _parse_extensions(cls, value: Any) -> dict[str, Any] | None:
        parsed = _parse_json_text(value)
        return parsed if isinstance(parsed, dict) else None


class SessionCreate(SQLModel):
    """Schema for creating a chat session."""

    name: Optional[str] = None
    flow_id: Optional[UUID] = None


PINNED_MESSAGE_IDS_KEY = "pinned_message_ids"
# Session-scoped directories the user explicitly granted for tool filesystem access.
AUTHORIZED_ROOTS_META_KEY = "authorized_roots"


def parse_authorized_roots_from_session_metadata(raw: Optional[str]) -> list[dict[str, Any]]:
    """Return ``[{path, label?}, …]`` from ``session_metadata`` JSON (best-effort)."""
    if not raw:
        return []
    try:
        meta = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(meta, dict):
        return []
    roots_raw = meta.get(AUTHORIZED_ROOTS_META_KEY)
    if not isinstance(roots_raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in roots_raw:
        if not isinstance(item, dict):
            continue
        p = item.get("path")
        if not isinstance(p, str) or not p.strip():
            continue
        label = item.get("label")
        out.append({
            "path": p.strip(),
            **({"label": str(label)} if isinstance(label, str) and label.strip() else {}),
        })
    return out


def parse_pinned_message_ids_from_session_metadata(raw: Optional[str]) -> list[UUID]:
    """Read ordered pinned message UUIDs from ``session_metadata`` JSON."""
    if not raw:
        return []
    try:
        meta = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(meta, dict):
        return []
    ids_raw = meta.get(PINNED_MESSAGE_IDS_KEY)
    if ids_raw is None:
        return []
    if not isinstance(ids_raw, list):
        return []
    out: list[UUID] = []
    for x in ids_raw:
        try:
            if isinstance(x, UUID):
                out.append(x)
            elif isinstance(x, str):
                out.append(UUID(x.strip()))
        except (ValueError, TypeError):
            continue
    return out


class SessionRead(SQLModel):
    """Schema for reading a chat session."""

    id: UUID
    name: Optional[str]
    user_id: UUID
    flow_id: Optional[UUID]
    is_active: bool
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    pinned_message_ids: list[UUID] = Field(default_factory=list)


def chat_session_to_read(cs: ChatSession) -> SessionRead:
    """Map ORM :class:`ChatSession` to API :class:`SessionRead` (incl. pins)."""
    return SessionRead(
        id=cs.id,
        name=cs.name,
        user_id=cs.user_id,
        flow_id=cs.flow_id,
        is_active=cs.is_active,
        message_count=cs.message_count,
        last_message_at=cs.last_message_at,
        created_at=cs.created_at,
        updated_at=cs.updated_at,
        pinned_message_ids=parse_pinned_message_ids_from_session_metadata(cs.session_metadata),
    )
