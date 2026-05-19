"""Shared dependencies for the chat API endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends

from leagent.services.chat import ChatService, get_chat_service

logger = logging.getLogger(__name__)

ChatSvc = Annotated[ChatService, Depends(get_chat_service)]


def build_agent_controller():  # type: ignore[return]
    """Build an :class:`AgentController` wired to the running services.

    Returns ``None`` when the LLM service is unavailable so callers can
    gracefully degrade.
    """
    try:
        from leagent.agent.controller import AgentController, AgentConfig
        from leagent.agent.hooks import HookManager, create_default_hooks
        from leagent.agent.planner import TaskPlanner
        from leagent.services.runtime import get_service_manager
        from leagent.tools.base import ToolPermissionContext
        from leagent.tools.executor import ToolExecutor
        from leagent.tools.registry import get_registry

        sm = get_service_manager()
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
        try:
            from leagent.bootstrap import (
                register_coding_agent_tool,
                register_script_agent_tool,
                register_subagent_tool,
            )
            register_script_agent_tool(registry, controller)
            register_coding_agent_tool(registry, controller)
            register_subagent_tool(registry, controller)
        except Exception:
            logger.debug("agent_subtools_unavailable", exc_info=True)
        return controller
    except Exception as exc:
        logger.debug("agent_controller_unavailable: %s", exc)
        return None
