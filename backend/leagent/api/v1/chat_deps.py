"""Shared dependencies for the chat API endpoints."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Annotated, Optional

from fastapi import Depends

from leagent.api.deps import get_service_manager as get_service_manager_dep
from leagent.services.chat import ChatService, get_chat_service

if TYPE_CHECKING:
    from leagent.agent.controller import AgentController
    from leagent.services.service_manager import ServiceManager

logger = logging.getLogger(__name__)

ChatSvc = Annotated[ChatService, Depends(get_chat_service)]


def build_agent_controller(
    service_manager: "ServiceManager | None" = None,
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
        from leagent.agent.controller import AgentController, AgentConfig
        from leagent.agent.hooks import HookManager, create_default_hooks
        from leagent.agent.planner import TaskPlanner
        from leagent.services.runtime import get_service_manager
        from leagent.tools.base import ToolPermissionContext
        from leagent.tools.executor import ToolExecutor
        from leagent.tools.registry import get_registry

        sm = service_manager if service_manager is not None else get_service_manager()
        if sm.llm_service is None:
            return None

        registry = get_registry()
        # Shared with AgentController so deny/allow rules apply on the QueryEngine
        # tool path (executor enforces only when permission_context is set).
        permission_context = ToolPermissionContext()
        executor = ToolExecutor(
            registry=registry,
            service_manager=sm,
            permission_context=permission_context,
        )
        planner = TaskPlanner(
            llm=sm.llm_service,
            agent_memory=sm.agent_memory,
            rule_engine=sm.rule_engine,
        )

        workflow_engine = None
        try:
            from leagent.workflow import WorkflowExecutor
            workflow_engine = WorkflowExecutor()
        except Exception:
            pass

        hook_manager = HookManager()
        for hook in create_default_hooks(sm.agent_memory):
            hook_manager.register(hook)

        config = AgentConfig(enable_streaming=True)
        controller = AgentController(
            llm=sm.llm_service,
            tools=registry,
            agent_memory=sm.agent_memory,
            session_manager=sm.session_manager,
            planner=planner,
            executor=executor,
            workflow_engine=workflow_engine,
            hook_manager=hook_manager,
            config=config,
            permission_context=permission_context,
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
    sm: Annotated["ServiceManager", Depends(get_service_manager_dep)],
):  # type: ignore[return]
    """FastAPI dependency wrapper around :func:`build_agent_controller`."""
    return build_agent_controller(sm)


# Inject the (optional) agent controller into a handler:
#   async def handler(agent: AgentControllerDep) -> ...:
AgentControllerDep = Annotated[Optional["AgentController"], Depends(get_agent_controller)]
