"""Kernel run state — explicit, serialisable snapshot of a run.

``RunState`` extends the raw ``QueryState`` bookkeeping with
checkpoint-oriented fields (session, agent name, usage accumulator)
so the kernel can persist/resume a run at any turn boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass
class RunState:
    """Serialisable snapshot of an in-progress agent run.

    Created once at the start of ``runtime.run`` / ``runtime.stream`` and
    mutated at turn boundaries by the kernel loop.  The
    :class:`~leagent.sdk.protocols.CheckpointStore` persists this object
    so runs can be interrupted and resumed (LangGraph-style).
    """

    session_id: str = ""
    agent_name: str = ""
    turn: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)
    reason: str = "running"
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls_total: int = 0
    produced_files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return self.reason not in ("running", "awaiting_user_input")

    def to_checkpoint_dict(self) -> dict[str, Any]:
        """Serialise for :class:`~leagent.sdk.protocols.CheckpointStore`."""
        return {
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "turn": self.turn,
            "messages": list(self.messages),
            "reason": self.reason,
            "error": self.error,
            "usage": dict(self.usage),
            "tool_calls_total": self.tool_calls_total,
            "produced_files": list(self.produced_files),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_checkpoint_dict(cls, data: dict[str, Any]) -> RunState:
        """Restore from a serialised checkpoint."""
        return cls(
            session_id=str(data.get("session_id", "")),
            agent_name=str(data.get("agent_name", "")),
            turn=int(data.get("turn", 0)),
            messages=list(data.get("messages") or []),
            reason=str(data.get("reason", "running")),
            error=data.get("error"),
            usage=dict(data.get("usage") or {}),
            tool_calls_total=int(data.get("tool_calls_total", 0)),
            produced_files=list(data.get("produced_files") or []),
            metadata=dict(data.get("metadata") or {}),
        )


__all__ = ["RunState"]
