"""Identity tables required by foreign keys and the auth control plane."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlmodel import Field, SQLModel


class UserStub(SQLModel, table=True):
    """Application user row (expanded beyond the legacy id-only stub)."""

    __tablename__ = "users"

    id: UUID = Field(primary_key=True, index=True)
    username: str | None = Field(default=None, index=True, max_length=128)
    password_hash: str | None = Field(default=None, max_length=512)
    display_name: str | None = Field(default=None, max_length=256)
    role: str = Field(default="user", max_length=32)
    disabled: bool = Field(default=False)
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)


class WorkspaceStub(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: UUID = Field(primary_key=True, index=True)
