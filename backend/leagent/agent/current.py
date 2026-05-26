"""Context-local access to the agent controller currently executing a tool."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from leagent.agent.controller import AgentController

_current_agent_controller: ContextVar["AgentController | None"] = ContextVar(
    "leagent_current_agent_controller",
    default=None,
)


def get_current_agent_controller() -> "AgentController | None":
    """Return the controller bound to the current async execution context."""
    return _current_agent_controller.get()


@contextmanager
def bind_current_agent_controller(controller: "AgentController") -> Iterator[None]:
    """Bind a controller for sub-agent tools during a single agent run."""
    token = _current_agent_controller.set(controller)
    try:
        yield
    finally:
        _current_agent_controller.reset(token)
