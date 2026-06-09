"""Unified runtime event + result types.

``AgentEvent`` is the **single** streaming event type emitted by
:class:`~leagent.sdk.AgentRuntime`.  It consolidates the ``SDKMessage``
frames produced by ``QueryEngine`` and the legacy ``StreamEvent`` shape,
while preserving the exact ``{type, data}`` wire format that
SSE/WebSocket consumers already depend on.

``AgentResult`` is the aggregate, non-streaming result of ``runtime.run``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from leagent.agent.query_engine import SDKMessage


class AgentEventType(StrEnum):
    """Canonical runtime event types (mirror of QueryEngine SDK frames)."""

    SYSTEM_INIT = "system_init"
    STREAM_DELTA = "stream_delta"
    TOOL_CALL_DELTA = "tool_call_delta"
    ASSISTANT = "assistant"
    ASSISTANT_TOOLS = "assistant_tools"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    WORKSPACE_ATTACHMENTS = "workspace_attachments"
    RESULT = "result"


@dataclass
class AgentEvent:
    """A single event in an agent run stream.

    The ``{type, data}`` shape is intentionally identical to the legacy
    ``SDKMessage`` so existing serializers keep working unchanged.
    """

    type: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_sdk_message(cls, message: SDKMessage) -> AgentEvent:
        return cls(type=message.type, data=dict(message.data or {}))

    def to_sdk_message(self) -> SDKMessage:
        from leagent.agent.query_engine import SDKMessage

        return SDKMessage(type=self.type, data=dict(self.data or {}))

    @property
    def is_terminal(self) -> bool:
        return self.type == AgentEventType.RESULT


@dataclass
class AgentResult:
    """Aggregate result of a completed (non-streaming) agent run."""

    session_id: str
    text: str = ""
    reason: str = "completed"
    error: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: int = 0
    produced_files: list[str] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None and self.reason in (
            "completed",
            "awaiting_user_input",
        )


__all__ = ["AgentEvent", "AgentEventType", "AgentResult"]
