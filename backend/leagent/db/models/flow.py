"""Flow model for workflow/agent definitions."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlmodel import Column, Field, Relationship, SQLModel, Text

from leagent.db.models.base import BaseModel, SoftDeleteMixin

if TYPE_CHECKING:
    from leagent.db.models.folder import Folder
    from leagent.db.models.message import Message


class FlowStatus(str, Enum):
    """Flow status values."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class FlowType(str, Enum):
    """Flow type classification."""

    AGENT = "agent"
    WORKFLOW = "workflow"
    CHAT = "chat"
    TOOL = "tool"


class FlowBase(SQLModel):
    """Base flow fields."""

    name: str = Field(index=True, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    icon: Optional[str] = Field(default="🤖", max_length=50)
    icon_bg_color: Optional[str] = Field(default=None, max_length=20)
    status: FlowStatus = Field(default=FlowStatus.DRAFT)
    flow_type: FlowType = Field(default=FlowType.AGENT)
    is_public: bool = Field(default=False)
    tags: Optional[str] = Field(default=None, max_length=500)


class Flow(FlowBase, BaseModel, SoftDeleteMixin, table=True):
    """Flow database model."""

    __tablename__ = "flows"

    # Flow definition (JSON)
    data: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Versioning
    version: int = Field(default=1)
    parent_id: Optional[UUID] = Field(default=None, foreign_key="flows.id")

    # Ownership
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    folder_id: Optional[UUID] = Field(default=None, foreign_key="folders.id")
    # Tenant scoping (nullable → belongs to user's personal workspace).
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)

    # Execution settings (JSON)
    settings: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Stats
    run_count: int = Field(default=0)
    last_run_at: Optional[datetime] = Field(default=None)
    avg_run_time_ms: Optional[int] = Field(default=None)

    # Embedding endpoint for RAG
    endpoint_name: Optional[str] = Field(default=None, max_length=100)

    # Relationships
    folder: Optional["Folder"] = Relationship(back_populates="flows")
    messages: List["Message"] = Relationship(back_populates="flow")


class FlowVersion(BaseModel, table=True):
    """Versioned flow snapshots."""

    __tablename__ = "flow_versions"

    flow_id: UUID = Field(foreign_key="flows.id", index=True)
    version: int = Field(index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    data: Optional[str] = Field(default=None, sa_column=Column(Text))
    settings: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_by: Optional[UUID] = Field(default=None, foreign_key="users.id")
    change_log: Optional[str] = Field(default=None, max_length=1000)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)


class FlowCreate(FlowBase):
    """Schema for creating a flow."""

    data: Optional[str] = None
    settings: Optional[str] = None
    folder_id: Optional[UUID] = None


class FlowUpdate(SQLModel):
    """Schema for updating a flow."""

    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    icon_bg_color: Optional[str] = None
    status: Optional[FlowStatus] = None
    flow_type: Optional[FlowType] = None
    is_public: Optional[bool] = None
    tags: Optional[str] = None
    data: Optional[str] = None
    settings: Optional[str] = None
    folder_id: Optional[UUID] = None


class FlowRead(FlowBase):
    """Schema for reading a flow."""

    id: UUID
    version: int
    user_id: Optional[UUID]
    folder_id: Optional[UUID]
    run_count: int
    last_run_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # JSON graph: either `{ "nodes", "edges" }` (editor) or engine workflow dict from templates
    data: Optional[str] = None
