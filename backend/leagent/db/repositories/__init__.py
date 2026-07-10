"""Per-domain persistence repositories.

Repositories are the seam between application/service code and the database.
They encapsulate SQLModel queries so handlers and services depend on a narrow,
typed interface (modeled on :class:`leagent.cron.repository.JobRepository`)
rather than embedding inline ``select(...)`` statements.

Each repository is defined as a ``Protocol`` plus a concrete ``Db*`` implementation
that wraps a :class:`~leagent.db.service.DatabaseService`. The :class:`Repositories`
aggregator provides lazy access to all of them from a single ``DatabaseService``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leagent.db.repositories.agent_checkpoint import (
    CheckpointRepository,
    DbCheckpointRepository,
)
from leagent.db.repositories.chat import ChatRepository, DbChatRepository
from leagent.db.repositories.document_chunks import (
    DbDocumentChunkRepository,
    DocumentChunkRepository,
)
from leagent.db.repositories.files import DbFileRepository, FileRepository
from leagent.db.repositories.tasks import DbTaskRepository, TaskRepository
from leagent.db.repositories.workflow_executions import (
    DbWorkflowExecutionRepository,
    WorkflowExecutionRepository,
)

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService


class Repositories:
    """Lazy accessor bundling all per-domain repositories for a database."""

    def __init__(self, db: "DatabaseService") -> None:
        self._db = db
        self._files: DbFileRepository | None = None
        self._document_chunks: DbDocumentChunkRepository | None = None
        self._tasks: DbTaskRepository | None = None
        self._chat: DbChatRepository | None = None
        self._checkpoints: DbCheckpointRepository | None = None
        self._workflow_executions: DbWorkflowExecutionRepository | None = None

    @property
    def files(self) -> DbFileRepository:
        if self._files is None:
            self._files = DbFileRepository(self._db)
        return self._files

    @property
    def document_chunks(self) -> DbDocumentChunkRepository:
        if self._document_chunks is None:
            self._document_chunks = DbDocumentChunkRepository(self._db)
        return self._document_chunks

    @property
    def tasks(self) -> DbTaskRepository:
        if self._tasks is None:
            self._tasks = DbTaskRepository(self._db)
        return self._tasks

    @property
    def chat(self) -> DbChatRepository:
        if self._chat is None:
            self._chat = DbChatRepository(self._db)
        return self._chat

    @property
    def checkpoints(self) -> DbCheckpointRepository:
        if self._checkpoints is None:
            self._checkpoints = DbCheckpointRepository(self._db)
        return self._checkpoints

    @property
    def workflow_executions(self) -> DbWorkflowExecutionRepository:
        if self._workflow_executions is None:
            self._workflow_executions = DbWorkflowExecutionRepository(self._db)
        return self._workflow_executions


__all__ = [
    "Repositories",
    "ChatRepository",
    "DbChatRepository",
    "CheckpointRepository",
    "DbCheckpointRepository",
    "FileRepository",
    "DbFileRepository",
    "DocumentChunkRepository",
    "DbDocumentChunkRepository",
    "TaskRepository",
    "DbTaskRepository",
    "WorkflowExecutionRepository",
    "DbWorkflowExecutionRepository",
]
