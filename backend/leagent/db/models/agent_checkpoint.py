"""Durable agent-run checkpoint model.

Persists a :class:`~leagent.sdk.protocols.Checkpoint` so an agent run that
paused (e.g. ``awaiting_user_input``) can be resumed across process
restarts/workers — the Codex ``RolloutRecorder`` / Claude ``SessionStore``
analogue. The full snapshot (messages/usage/metadata) is stored as a JSON
``payload`` while the scalar columns stay queryable for lookup/listing.
"""

from __future__ import annotations

from sqlalchemy import Column, Text
from sqlmodel import Field

from leagent.db.models.base import BaseModel


class AgentCheckpoint(BaseModel, table=True):
    """A persisted snapshot of an agent run at a turn boundary."""

    __tablename__ = "agent_checkpoints"

    checkpoint_id: str = Field(index=True, unique=True)
    session_id: str = Field(default="", index=True)
    agent_name: str = Field(default="")
    turn: int = Field(default=0)
    reason: str = Field(default="awaiting_user_input")
    #: JSON-encoded ``{"messages": [...], "usage": {...}, "metadata": {...}}``.
    payload: str = Field(default="{}", sa_column=Column(Text))


__all__ = ["AgentCheckpoint"]
