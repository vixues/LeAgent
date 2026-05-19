"""Task handlers and handler registration for the :class:`TaskManager`.

Handlers implement the ``TaskHandler`` protocol defined in
:mod:`leagent.services.task_manager` and cover the concrete
``TaskType`` variants (``agent``/``shell``/``workflow``/``tool``/
``batch``). Sites can swap in their own handlers at bootstrap by
calling :func:`register_task_handler_builder` before the
:class:`ServiceManager` starts.
"""

from __future__ import annotations

from leagent.tasks.registration import (
    register_default_handlers,
    register_task_handler_builder,
    reset_task_handler_builders,
)

__all__ = [
    "register_default_handlers",
    "register_task_handler_builder",
    "reset_task_handler_builders",
]
