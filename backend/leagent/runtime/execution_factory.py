"""Central factory for minting and retiring :class:`ExecutionRun` handles."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from leagent.runtime.execution_registry import get_execution_run_registry
from leagent.runtime.execution_run import ExecutionRun, ExecutionScope
from leagent.utils.logging import get_logger

logger = get_logger(__name__)


def begin_execution(
    *,
    scope: ExecutionScope,
    session_id: str | None = None,
    user_id: str | None = None,
    parent_run_id: str | None = None,
    prompt_id: str | None = None,
    workflow_execution_id: UUID | None = None,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ExecutionRun:
    """Register a new execution run and return the handle."""
    run = ExecutionRun(
        scope=scope,
        session_id=session_id,
        user_id=user_id,
        parent_run_id=parent_run_id,
        prompt_id=prompt_id,
        workflow_execution_id=workflow_execution_id,
        task_id=task_id,
        metadata=dict(metadata or {}),
    )
    registered = get_execution_run_registry().register(run)
    logger.info(
        "execution_run_begin",
        run_id=registered.run_id,
        scope=scope.value,
        session_id=session_id,
        parent_run_id=parent_run_id,
        prompt_id=prompt_id,
        task_id=task_id,
    )
    return registered


def end_execution(run_id: str) -> None:
    """Remove a run from the in-process registry."""
    registry = get_execution_run_registry()
    run = registry.get(run_id)
    registry.remove(run_id)
    logger.info(
        "execution_run_end",
        run_id=run_id,
        scope=run.scope.value if run is not None else None,
        session_id=run.session_id if run is not None else None,
        had_pause_token=run.is_blocked if run is not None else False,
    )


def end_execution_unless_blocked(run_id: str) -> bool:
    """Remove *run_id* unless the run is paused/blocked.

    Returns ``True`` when the run was removed, ``False`` when retained.
    """
    registry = get_execution_run_registry()
    run = registry.get(run_id)
    if run is not None and run.is_blocked:
        logger.info(
            "execution_run_retained_blocked",
            run_id=run_id,
            scope=run.scope.value,
            session_id=run.session_id,
            reason=run.pause_token.reason if run.pause_token else None,
        )
        return False
    end_execution(run_id)
    return True


def attach_run_id(data: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Return a shallow copy of *data* with ``run_id`` set."""
    out = dict(data)
    out["run_id"] = run_id
    return out


__all__ = [
    "attach_run_id",
    "begin_execution",
    "end_execution",
    "end_execution_unless_blocked",
    "ExecutionScope",
]
