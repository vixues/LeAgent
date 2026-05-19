"""Canvas documents: hosted HTML / embeds / generative UI snapshots."""

from __future__ import annotations

from enum import Enum
from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel, Text, UniqueConstraint

from leagent.services.database.models.base import BaseModel


class CanvasContentType(str, Enum):
    """Stored canvas payload kind."""

    HTML = "html"
    REACT_BUNDLE = "react_bundle"
    EMBED_URL = "embed_url"
    GEN_UI_SNAPSHOT = "gen_ui_snapshot"


class CanvasDocument(BaseModel, table=True):
    """One revision of an agent canvas (HTML body or snapshot metadata)."""

    __tablename__ = "canvas_documents"
    __table_args__ = (UniqueConstraint("canvas_id", "revision", name="uq_canvas_revision"),)

    canvas_id: UUID = Field(index=True)
    revision: int = Field(default=1, ge=1)
    session_id: UUID = Field(foreign_key="chat_sessions.id", index=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    workspace_id: Optional[UUID] = Field(default=None, nullable=True, index=True)
    message_id: Optional[UUID] = Field(default=None, foreign_key="messages.id", index=True)
    title: str = Field(max_length=500)
    content_type: str = Field(max_length=64)
    html_body: Optional[str] = Field(default=None, sa_column=Column(Text))
    embed_url: Optional[str] = Field(default=None, max_length=2000)
    ui_snapshot_json: Optional[str] = Field(default=None, sa_column=Column(Text))
