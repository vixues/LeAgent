"""FastAPI workflow server package.

Mount ``workflow.server.router.router`` under the API prefix
(e.g. ``app.include_router(workflow_router, prefix="/api/v1")``).
"""

from __future__ import annotations

from .event_bus import (
    ExecutionEventBus,
    InMemoryEventBus,
    get_event_bus,
    reset_event_bus,
)
from .prompt_hooks import apply_replacements, seed_context, validate_prompt
from .router import router
from .ws import stream_all, stream_execution

__all__ = [
    "ExecutionEventBus",
    "InMemoryEventBus",
    "apply_replacements",
    "get_event_bus",
    "reset_event_bus",
    "router",
    "seed_context",
    "stream_all",
    "stream_execution",
    "validate_prompt",
]
