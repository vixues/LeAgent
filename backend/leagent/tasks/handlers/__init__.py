"""Concrete :class:`TaskHandler` implementations for each :class:`TaskType`.

Each module in this package exports exactly one handler class; they are
registered with the :class:`TaskManager` during startup via
:mod:`leagent.tasks.registration`.
"""

from __future__ import annotations

from leagent.tasks.handlers.agent_handler import AgentTaskHandler
from leagent.tasks.handlers.batch_handler import BatchTaskHandler
from leagent.tasks.handlers.shell_handler import ShellTaskHandler
from leagent.tasks.handlers.tool_handler import ToolTaskHandler
from leagent.tasks.handlers.workflow_handler import WorkflowTaskHandler

__all__ = [
    "AgentTaskHandler",
    "BatchTaskHandler",
    "ShellTaskHandler",
    "ToolTaskHandler",
    "WorkflowTaskHandler",
]
