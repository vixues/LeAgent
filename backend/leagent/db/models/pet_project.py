"""Pet Space — mascot creative projects and asset links."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Column, Field, SQLModel, Text

from leagent.db.models.base import BaseModel, SoftDeleteMixin, utc_now


class PetProject(BaseModel, SoftDeleteMixin, table=True):
    """A creative project for virtual-mascot assets (reference art, sprites, etc.)."""

    __tablename__ = "pet_projects"

    user_id: UUID = Field(foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, foreign_key="workspaces.id", index=True)
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    settings: Optional[str] = Field(default=None, sa_column=Column(Text))


class PetProjectFile(SQLModel, table=True):
    """Join row: a library file belongs to exactly one pet project."""

    __tablename__ = "pet_project_files"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    pet_project_id: UUID = Field(foreign_key="pet_projects.id", index=True)
    file_id: UUID = Field(foreign_key="files.id", unique=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
