"""Workflow-execution persistence repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlmodel import select

from leagent.db.models.workflow_execution import WorkflowExecution

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService


class WorkflowExecutionRepository(Protocol):
    """Protocol for workflow-execution persistence."""

    async def get(self, execution_id: UUID) -> WorkflowExecution | None:
        """Return a workflow execution by id."""
        ...

    async def list_for_flow(
        self, flow_id: UUID, *, limit: int = 50
    ) -> list[WorkflowExecution]:
        """Return executions for *flow_id*, newest first."""
        ...

    async def list_for_user(
        self, user_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[WorkflowExecution]:
        """Return executions owned by *user_id*, optionally filtered by status."""
        ...

    async def create(self, execution: WorkflowExecution) -> WorkflowExecution:
        """Persist a new workflow-execution row."""
        ...


class DbWorkflowExecutionRepository:
    """``DatabaseService``-backed :class:`WorkflowExecutionRepository`."""

    def __init__(self, db: "DatabaseService") -> None:
        self._db = db

    async def get(self, execution_id: UUID) -> WorkflowExecution | None:
        async with self._db.session() as session:
            return await session.get(WorkflowExecution, execution_id)

    async def list_for_flow(
        self, flow_id: UUID, *, limit: int = 50
    ) -> list[WorkflowExecution]:
        async with self._db.session() as session:
            result = await session.exec(
                select(WorkflowExecution)
                .where(WorkflowExecution.flow_id == flow_id)
                .order_by(WorkflowExecution.created_at.desc())
                .limit(limit)
            )
            return list(result.all())

    async def list_for_user(
        self, user_id: UUID, *, status: str | None = None, limit: int = 50
    ) -> list[WorkflowExecution]:
        async with self._db.session() as session:
            stmt = select(WorkflowExecution).where(WorkflowExecution.user_id == user_id)
            if status is not None:
                stmt = stmt.where(WorkflowExecution.status == status)
            stmt = stmt.order_by(WorkflowExecution.created_at.desc()).limit(limit)
            result = await session.exec(stmt)
            return list(result.all())

    async def create(self, execution: WorkflowExecution) -> WorkflowExecution:
        async with self._db.session() as session:
            session.add(execution)
            await session.flush()
            await session.refresh(execution)
            return execution
