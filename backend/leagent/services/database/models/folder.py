"""Folder model for organizing files and flows."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from uuid import UUID

from sqlmodel import Field, Relationship, SQLModel

from leagent.services.database.models.base import BaseModel, SoftDeleteMixin

if TYPE_CHECKING:
    from leagent.services.database.models.file import File
    from leagent.services.database.models.flow import Flow


class FolderBase(SQLModel):
    """Base folder fields."""

    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = Field(default="📁", max_length=50)
    color: Optional[str] = Field(default=None, max_length=20)


class Folder(FolderBase, BaseModel, SoftDeleteMixin, table=True):
    """Folder database model."""

    __tablename__ = "folders"

    # Ownership
    user_id: Optional[UUID] = Field(default=None, foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)

    # Hierarchy
    parent_id: Optional[UUID] = Field(default=None, foreign_key="folders.id", index=True)

    # Ordering
    position: int = Field(default=0)

    # Counts (cached for performance)
    file_count: int = Field(default=0)
    flow_count: int = Field(default=0)

    # Code-project mode. When ``is_project`` is True the folder is bound to
    # an on-disk directory (``project_path``) that the coding agent /
    # project_* tools operate on. When False the folder is an ordinary DB
    # association of uploaded files, exactly as before.
    is_project: bool = Field(default=False, index=True)
    project_path: Optional[str] = Field(default=None, max_length=1024)
    project_path_checked_at: Optional[datetime] = Field(default=None)

    # Relationships
    files: List["File"] = Relationship(back_populates="folder")
    flows: List["Flow"] = Relationship(back_populates="folder")


class FolderCreate(SQLModel):
    """Schema for creating a folder."""

    name: str
    description: Optional[str] = None
    icon: Optional[str] = "📁"
    color: Optional[str] = None
    parent_id: Optional[UUID] = None


class FolderUpdate(SQLModel):
    """Schema for updating a folder."""

    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    parent_id: Optional[UUID] = None
    position: Optional[int] = None


class FolderProjectUpdate(SQLModel):
    """Schema for toggling / configuring a folder's code-project mode."""

    enabled: bool
    project_path: Optional[str] = None


class FolderRead(FolderBase):
    """Schema for reading a folder."""

    id: UUID
    user_id: Optional[UUID]
    parent_id: Optional[UUID]
    position: int
    file_count: int
    flow_count: int
    is_project: bool = False
    project_path: Optional[str] = None
    project_path_checked_at: Optional[datetime] = None
