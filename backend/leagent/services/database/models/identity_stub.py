"""Minimal identity tables required by legacy foreign keys."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Field, SQLModel


class UserStub(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(primary_key=True, index=True)


class WorkspaceStub(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: UUID = Field(primary_key=True, index=True)
