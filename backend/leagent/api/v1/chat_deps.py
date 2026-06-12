"""Shared dependencies for the chat API endpoints."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Annotated, Optional

from fastapi import Depends

from leagent.api.deps import get_service_manager as get_service_manager_dep
from leagent.services.chat import ChatService, get_chat_service
from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from leagent.agent.controller import AgentController
    from leagent.services.service_manager import ServiceManager

logger = get_logger(__name__)

ChatSvc = Annotated[ChatService, Depends(get_chat_service)]


def build_agent_controller(
    service_manager: ServiceManager | None = None,
):  # type: ignore[return]
    """Build an :class:`AgentController` wired to the running services.

    Args:
        service_manager: Optional explicit ``ServiceManager``. When omitted the
            process-wide manager is resolved (so this can be used both as a
            FastAPI dependency and as a plain helper).

    Returns ``None`` when the LLM service is unavailable so callers can
    gracefully degrade.
    """
    started = time.perf_counter()
    status_label = "success"
    try:
        from leagent.agent.controller import AgentConfig, AgentController
        from leagent.services.runtime import get_service_manager

        sm = service_manager if service_manager is not None else get_service_manager()
        if sm.llm_service is None:
            return None

        ctx = sm.runtime_context
        if ctx.llm is None or ctx.tools is None or ctx.executor is None:
            return None

        config = AgentConfig(enable_streaming=True)
        controller = AgentController(
            llm=ctx.llm,
            tools=ctx.tools,
            agent_memory=ctx.agent_memory,
            session_manager=ctx.session_manager,
            executor=ctx.executor,
            hook_manager=ctx.hook_manager,
            config=config,
            permission_context=ctx.permission_context,
            checkpoint_store=ctx.checkpoint_store,
        )
        return controller
    except Exception as exc:
        status_label = "error"
        logger.debug("agent_controller_unavailable: %s", exc)
        return None
    finally:
        try:
            from leagent.utils.metrics import get_metrics

            get_metrics().record_agent_turn_phase(
                "build_agent_controller",
                time.perf_counter() - started,
                status=status_label,
            )
        except Exception:
            logger.debug("agent_controller_metrics_failed", exc_info=True)


def get_agent_controller(
    sm: Annotated[ServiceManager, Depends(get_service_manager_dep)],
):  # type: ignore[return]
    """FastAPI dependency wrapper around :func:`build_agent_controller`."""
    return build_agent_controller(sm)


# Inject the (optional) agent controller into a handler:
#   async def handler(agent: AgentControllerDep) -> ...:
AgentControllerDep = Annotated[Optional["AgentController"], Depends(get_agent_controller)]
