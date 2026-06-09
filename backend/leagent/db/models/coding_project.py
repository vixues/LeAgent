"""Coding-project model: agent-generated runnable scaffolds.

A :class:`CodingProject` row pairs an on-disk directory (under
``CODING_PROJECTS_ROOT`` for managed scaffolds, or any user-chosen
absolute path that the agent later "adopted") with the runtime
metadata the :class:`DevServerSupervisor` needs to boot it: which
template it was scaffolded from, what kind of runtime to spawn
(frontend / FastAPI), the last-allocated port, the supervised PID,
and the live status. Folder integration is via a nullable
``folder_id`` foreign key — every managed scaffold also gets a
project-mode :class:`Folder` row so the existing FolderPage UI keeps
working unchanged.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlmodel import Field, SQLModel

from leagent.db.models.base import BaseModel, SoftDeleteMixin

if TYPE_CHECKING:  # pragma: no cover
    pass


class CodingProjectRuntimeKind(str, Enum):
    """Which dev-server profile the supervisor uses for this project."""

    FRONTEND = "frontend"
    FASTAPI = "fastapi"
    PYTHON = "python"


class CodingProjectStatus(str, Enum):
    """Live status of the supervised dev server."""

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"


class CodingProjectBase(SQLModel):
    name: str = Field(max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    template: str = Field(max_length=64)
    runtime_kind: CodingProjectRuntimeKind = Field(
        default=CodingProjectRuntimeKind.FRONTEND
    )


class CodingProject(CodingProjectBase, BaseModel, SoftDeleteMixin, table=True):
    """Persistent record of an agent-generated runnable project."""

    __tablename__ = "coding_projects"

    user_id: Optional[UUID] = Field(
        default=None, foreign_key="users.id", index=True
    )
    folder_id: Optional[UUID] = Field(
        default=None, foreign_key="folders.id", index=True
    )

    #: Absolute path on disk. For managed scaffolds this is under
    #: ``CODING_PROJECTS_ROOT``; for "adopted" folders it matches the
    #: linked :attr:`Folder.project_path`.
    root_path: str = Field(max_length=1024)

    #: Latest port the supervisor bound the dev server to. ``None``
    #: when the project has never run.
    port: Optional[int] = Field(default=None)
    #: Latest supervised PID; cleared on stop.
    pid: Optional[int] = Field(default=None)

    status: CodingProjectStatus = Field(
        default=CodingProjectStatus.IDLE, index=True
    )
    last_started_at: Optional[datetime] = Field(default=None)
    last_stopped_at: Optional[datetime] = Field(default=None)

    #: Free-form supervisor-side state that doesn't deserve its own
    #: column (e.g. the install marker file path, ready regex used).
    install_marker: Optional[str] = Field(default=None, max_length=255)


class CodingProjectCreate(SQLModel):
    name: str = Field(max_length=200)
    template: str = Field(max_length=64)
    description: Optional[str] = Field(default=None, max_length=500)
    folder_id: Optional[UUID] = None
    #: Optional caller-supplied absolute path. When omitted the manager
    #: scaffolds into ``CODING_PROJECTS_ROOT/<uuid>`` and creates a
    #: matching :class:`Folder` row in project-mode.
    into_path: Optional[str] = Field(default=None, max_length=1024)


class CodingProjectUpdate(SQLModel):
    name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)


class CodingProjectRead(CodingProjectBase):
    id: UUID
    user_id: Optional[UUID]
    folder_id: Optional[UUID]
    root_path: str
    port: Optional[int]
    status: CodingProjectStatus
    last_started_at: Optional[datetime]
    last_stopped_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
