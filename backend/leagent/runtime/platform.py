"""Platform integration adapters for external channels and IM systems.

This module provides a thin adapter layer so chat/agent/workflow execution
can be invoked from non-HTTP ingress paths (Slack, Teams, webhooks) using
the same ``AgentRuntime`` and ``WorkflowService`` facades as the web UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from leagent.runtime.execution_run import ExecutionRun, ExecutionScope


@dataclass
class PlatformContext:
    """Caller context from an external platform integration."""

    platform: str
    external_user_id: str
    external_thread_id: str
    session_id: UUID | None = None
    metadata: dict[str, Any] | None = None


class PlatformAdapter:
    """Route platform messages through the unified agent runtime."""

    def __init__(self, service_manager: Any) -> None:
        self._sm = service_manager

    async def handle_message(
        self,
        ctx: PlatformContext,
        message: str,
        *,
        agent_name: str = "default_agent",
    ) -> ExecutionRun:
        from leagent.runtime.execution_registry import get_execution_run_registry
        from leagent.sdk import AgentRuntime

        run = get_execution_run_registry().register(
            ExecutionRun(
                scope=ExecutionScope.CHAT_TURN,
                session_id=str(ctx.session_id) if ctx.session_id else None,
                metadata={
                    "platform": ctx.platform,
                    "external_user_id": ctx.external_user_id,
                    "external_thread_id": ctx.external_thread_id,
                },
            )
        )
        runtime = AgentRuntime(self._sm.runtime_context)
        result = await runtime.run(
            agent_name,
            message,
            session_id=ctx.session_id,
            tool_extra={"platform": ctx.platform, "run_id": run.run_id},
        )
        run.metadata["result_reason"] = result.reason
        return run


__all__ = ["PlatformAdapter", "PlatformContext"]
