"""Workflow tools — list, run, monitor and control workflow executions.

Shared helpers for the workflow tool modules live here.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import ToolResult
from leagent.tools.workflow.chat_workflow import ChatWorkflowEmitTool
from leagent.tools.workflow.workflow_embed_emit import ChatWorkflowEmbedEmitTool
from leagent.tools.workflow.workflow_crud import (
    WorkflowCancelTool,
    WorkflowListTool,
    WorkflowPauseTool,
    WorkflowResumeTool,
    WorkflowRunTool,
    WorkflowStatusTool,
)

__all__ = [
    "ChatWorkflowEmitTool",
    "ChatWorkflowEmbedEmitTool",
    "WorkflowCancelTool",
    "WorkflowListTool",
    "WorkflowPauseTool",
    "WorkflowResumeTool",
    "WorkflowRunTool",
    "WorkflowStatusTool",
    "get_workflow_service",
    "workflow_error_result",
]

logger = structlog.get_logger(__name__)


def get_workflow_service() -> Any:
    """Return the workflow service or raise if unavailable."""
    from leagent.services.service_manager import get_service_manager

    sm = get_service_manager()
    if sm.workflow_service is None:
        raise RuntimeError("WorkflowService is not available")
    return sm.workflow_service


def workflow_error_result(operation: str, exc: Exception) -> ToolResult:
    """Log and return a standard error result for workflow operations."""
    logger.error(f"workflow_{operation}_tool_error", error=str(exc))
    return ToolResult(success=False, error=str(exc))
