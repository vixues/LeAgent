"""Audit log for tool approval decisions (Codex-style approval flow)."""

from __future__ import annotations

from typing import Optional

from sqlmodel import Field

from leagent.db.models.base import BaseModel


class ApprovalDecisionLog(BaseModel, table=True):
    """One row per user Allow/Deny decision on a gated tool call."""

    __tablename__ = "approval_decisions"

    session_id: Optional[str] = Field(default=None, index=True, max_length=100)
    user_id: Optional[str] = Field(default=None, index=True, max_length=100)
    tool_call_id: str = Field(default="", max_length=100)
    tool_name: str = Field(default="", index=True, max_length=200)
    params_digest: str = Field(default="", max_length=32)
    params_summary: Optional[str] = Field(default=None, max_length=2000)
    reason: Optional[str] = Field(default=None, max_length=1000)
    decision: str = Field(default="", index=True, max_length=32)  # allow_once | allow_session | deny
    scope: str = Field(default="once", max_length=16)  # once | session
    decided_by: str = Field(default="user", max_length=32)  # user | auto_review
