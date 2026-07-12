"""ContextVars for the active agent running-trace."""

from __future__ import annotations

from contextvars import ContextVar

run_id_var: ContextVar[str | None] = ContextVar("agent_trace_run_id", default=None)
root_span_id_var: ContextVar[str | None] = ContextVar(
    "agent_trace_root_span_id", default=None
)
parent_span_id_var: ContextVar[str | None] = ContextVar(
    "agent_trace_parent_span_id", default=None
)


def current_run_id() -> str | None:
    """Return the active execution ``run_id`` / ``trace_id``, if any."""
    return run_id_var.get()


def bind_trace_context(
    *,
    run_id: str | None,
    root_span_id: str | None = None,
    parent_span_id: str | None = None,
) -> None:
    """Bind trace correlation ContextVars for the current task."""
    run_id_var.set(run_id)
    if root_span_id is not None:
        root_span_id_var.set(root_span_id)
    if parent_span_id is not None:
        parent_span_id_var.set(parent_span_id)


def clear_trace_context() -> None:
    """Clear trace ContextVars."""
    run_id_var.set(None)
    root_span_id_var.set(None)
    parent_span_id_var.set(None)


__all__ = [
    "bind_trace_context",
    "clear_trace_context",
    "current_run_id",
    "parent_span_id_var",
    "root_span_id_var",
    "run_id_var",
]
