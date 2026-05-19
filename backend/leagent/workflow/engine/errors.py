"""Taxonomy of engine-raised exceptions."""

from __future__ import annotations

from typing import Any


class WorkflowEngineError(Exception):
    """Base class for all engine-raised errors."""

    def __init__(self, message: str, *, node_id: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.node_id = node_id
        self.details = details


class ValidationError(WorkflowEngineError):
    """Document failed structural or per-node validation."""

    def __init__(self, message: str, errors: dict[str, list[dict[str, Any]]] | None = None) -> None:
        super().__init__(message, details=errors)
        self.errors = errors or {}


class NodeExecutionError(WorkflowEngineError):
    """Wrapper for an exception raised inside a node's execute."""


class DependencyCycleError(WorkflowEngineError):
    """The graph contains a cycle the scheduler cannot resolve."""


class InterruptedError(WorkflowEngineError):  # noqa: A001 - shadows builtin intentionally
    """Execution was cancelled via the executor's interrupt handle."""


class BlockedError(WorkflowEngineError):
    """Raised when the scheduler can only make progress once an external
    block is released (human_review, long-polling external systems)."""
