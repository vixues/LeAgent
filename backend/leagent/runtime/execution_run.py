"""Shared execution run contract for agent, workflow, and task scopes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class ExecutionScope(StrEnum):
    CHAT_TURN = "chat_turn"
    WORKFLOW = "workflow"
    TASK = "task"
    TOOL_ONLY = "tool_only"


@dataclass
class PauseToken:
    """Unified pause/resume reference across agent and workflow runs."""

    scope: ExecutionScope
    reason: str = "awaiting_user_input"
    checkpoint_id: str | None = None
    workflow_execution_id: UUID | None = None
    workflow_state_id: UUID | None = None
    prompt_id: str | None = None
    session_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "reason": self.reason,
            "checkpoint_id": self.checkpoint_id,
            "workflow_execution_id": (
                str(self.workflow_execution_id) if self.workflow_execution_id else None
            ),
            "workflow_state_id": (
                str(self.workflow_state_id) if self.workflow_state_id else None
            ),
            "prompt_id": self.prompt_id,
            "session_id": self.session_id,
        }


@dataclass
class ExecutionRun:
    """In-process handle for a single execution unit."""

    run_id: str = field(default_factory=lambda: uuid4().hex)
    scope: ExecutionScope = ExecutionScope.CHAT_TURN
    parent_run_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    prompt_id: str | None = None
    workflow_execution_id: UUID | None = None
    task_id: str | None = None
    pause_token: PauseToken | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def pause(self, *, reason: str, **refs: Any) -> PauseToken:
        token = PauseToken(
            scope=self.scope,
            reason=reason,
            session_id=self.session_id,
            prompt_id=self.prompt_id,
            checkpoint_id=refs.get("checkpoint_id"),
            workflow_execution_id=refs.get("workflow_execution_id") or self.workflow_execution_id,
            workflow_state_id=refs.get("workflow_state_id"),
        )
        self.pause_token = token
        return token


__all__ = ["ExecutionScope", "ExecutionRun", "PauseToken"]
