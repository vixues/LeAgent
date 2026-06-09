"""Pluggable registration of :class:`TaskHandler` implementations.

Sites and plugins can swap out a concrete handler (for example the
``AGENT`` handler) without editing core code by registering a handler
builder before the :class:`ServiceManager` starts:

.. code-block:: python

    from leagent.tasks.registration import register_task_handler_builder

    def build_legacy_agent(sm):
        from my_site.handlers import LegacyAgentHandler
        return LegacyAgentHandler(sm)

    register_task_handler_builder(build_legacy_agent)

Builders registered later take precedence (the ``TaskManager`` keeps a
single handler per :class:`TaskType`, so the last registration wins).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, List

if TYPE_CHECKING:
    from leagent.services.service_manager import ServiceManager
    from leagent.services.task_manager import TaskHandler, TaskManager

logger = logging.getLogger(__name__)


HandlerBuilder = Callable[["ServiceManager"], "TaskHandler | None"]

_builders: List[HandlerBuilder] = []


def register_task_handler_builder(fn: HandlerBuilder) -> None:
    """Register a factory that produces a :class:`TaskHandler`.

    The factory receives the :class:`ServiceManager` so it can wire
    runtime dependencies (DB, LLM, workflow engine, tool registry).
    It may return ``None`` to skip registration conditionally.
    """
    _builders.append(fn)


def reset_task_handler_builders() -> None:
    """Clear all registered builders (for tests)."""
    _builders.clear()


def _default_builders() -> List[HandlerBuilder]:
    """Return the set of default-handler builders shipped with the app."""

    def _agent(sm: "ServiceManager") -> "TaskHandler | None":
        from leagent.tasks.handlers.agent_handler import AgentTaskHandler

        return AgentTaskHandler(service_manager=sm)

    def _shell(_: "ServiceManager") -> "TaskHandler | None":
        from leagent.tasks.handlers.shell_handler import ShellTaskHandler

        return ShellTaskHandler()

    def _workflow(sm: "ServiceManager") -> "TaskHandler | None":
        from leagent.tasks.handlers.workflow_handler import WorkflowTaskHandler

        if sm.workflow_service is None:
            return None
        return WorkflowTaskHandler(service_manager=sm)

    def _tool(sm: "ServiceManager") -> "TaskHandler | None":
        from leagent.tasks.handlers.tool_handler import ToolTaskHandler

        return ToolTaskHandler(service_manager=sm)

    def _batch(sm: "ServiceManager") -> "TaskHandler | None":
        from leagent.tasks.handlers.batch_handler import BatchTaskHandler

        return BatchTaskHandler(service_manager=sm)

    def _file_processing(sm: "ServiceManager") -> "TaskHandler | None":
        from leagent.tasks.handlers.file_processing_handler import (
            FileProcessingTaskHandler,
        )

        return FileProcessingTaskHandler(service_manager=sm)

    return [_agent, _shell, _workflow, _tool, _batch, _file_processing]


async def register_default_handlers(
    sm: "ServiceManager", tm: "TaskManager"
) -> int:
    """Instantiate and register every known :class:`TaskHandler`.

    Default builders are loaded first so site-registered builders (via
    :func:`register_task_handler_builder`) always override the defaults
    for the same :class:`TaskType`.

    Returns the count of handlers actually registered.
    """
    registered = 0
    for builder in (*_default_builders(), *list(_builders)):
        try:
            handler: Any = builder(sm)
        except Exception:
            logger.warning(
                "task_handler_builder_failed", exc_info=True
            )
            continue
        if handler is None:
            continue
        try:
            tm.register_handler(handler)
            registered += 1
        except Exception:
            logger.warning(
                "task_handler_registration_failed",
                handler=getattr(handler, "name", type(handler).__name__),
                exc_info=True,
            )
    return registered
