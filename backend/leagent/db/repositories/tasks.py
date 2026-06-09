"""Task persistence repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlmodel import select

from leagent.db.models.task import Task, TaskStatus

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService


class TaskRepository(Protocol):
    """Protocol for task persistence."""

    async def get(self, task_id: UUID) -> Task | None:
        """Return a task by id."""
        ...

    async def list_for_user(
        self, user_id: UUID, *, status: TaskStatus | None = None, limit: int = 100
    ) -> list[Task]:
        """Return tasks owned by *user_id*, optionally filtered by status."""
        ...

    async def create(self, task: Task) -> Task:
        """Persist a new task row."""
        ...

    async def update_status(self, task_id: UUID, status: TaskStatus) -> bool:
        """Update a task's status; return whether the row existed."""
        ...


class DbTaskRepository:
    """``DatabaseService``-backed :class:`TaskRepository`."""

    def __init__(self, db: "DatabaseService") -> None:
        self._db = db

    async def get(self, task_id: UUID) -> Task | None:
        async with self._db.session() as session:
            return await session.get(Task, task_id)

    async def list_for_user(
        self, user_id: UUID, *, status: TaskStatus | None = None, limit: int = 100
    ) -> list[Task]:
        async with self._db.session() as session:
            stmt = select(Task).where(Task.user_id == user_id)
            if status is not None:
                stmt = stmt.where(Task.status == status)
            stmt = stmt.order_by(Task.created_at.desc()).limit(limit)
            result = await session.exec(stmt)
            return list(result.all())

    async def create(self, task: Task) -> Task:
        async with self._db.session() as session:
            session.add(task)
            await session.flush()
            await session.refresh(task)
            return task

    async def update_status(self, task_id: UUID, status: TaskStatus) -> bool:
        async with self._db.session() as session:
            row = await session.get(Task, task_id)
            if row is None:
                return False
            row.status = status
            session.add(row)
            return True
