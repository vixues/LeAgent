"""Change reviews: worktree diffs awaiting human approve/reject (Review Queue)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field

from leagent.db.models.base import BaseModel


class ChangeReview(BaseModel, table=True):
    """One reviewable changeset produced by a worktree coding session."""

    __tablename__ = "change_reviews"

    session_id: str = Field(default="", index=True, max_length=100)
    user_id: Optional[str] = Field(default=None, index=True, max_length=100)
    run_id: Optional[str] = Field(default=None, max_length=100)

    workspace_mode: str = Field(default="worktree", max_length=32)
    project_root: str = Field(default="", max_length=1024)
    worktree_path: Optional[str] = Field(default=None, max_length=1024)
    branch: Optional[str] = Field(default=None, max_length=200)
    base_branch: Optional[str] = Field(default=None, max_length=200)

    title: str = Field(default="", max_length=500)
    summary: Optional[str] = Field(default=None, max_length=4000)
    files_changed: int = Field(default=0)
    additions: int = Field(default=0)
    deletions: int = Field(default=0)

    #: pending | approved | merged | rejected | failed
    status: str = Field(default="pending", index=True, max_length=32)
    decided_at: Optional[datetime] = Field(default=None)
    decided_by: Optional[str] = Field(default=None, max_length=100)
    reject_reason: Optional[str] = Field(default=None, max_length=1000)
