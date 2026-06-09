"""File persistence repository."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from sqlmodel import select

from leagent.db.models.file import File

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService


class FileRepository(Protocol):
    """Protocol for file persistence."""

    async def get(self, file_id: UUID) -> File | None:
        """Return a file row by id (including soft-deleted)."""
        ...

    async def get_for_user(self, file_id: UUID, user_id: UUID) -> File | None:
        """Return a non-deleted file owned by *user_id*."""
        ...

    async def list_for_session(self, session_id: UUID) -> list[File]:
        """Return non-deleted files attached to *session_id*."""
        ...

    async def get_many_for_user(
        self, file_ids: list[UUID], user_id: UUID
    ) -> list[File]:
        """Return non-deleted files owned by *user_id* matching *file_ids*."""
        ...

    async def soft_delete(self, file_id: UUID, user_id: UUID) -> bool:
        """Soft-delete a file owned by *user_id*; return whether it changed."""
        ...


class DbFileRepository:
    """``DatabaseService``-backed :class:`FileRepository`."""

    def __init__(self, db: "DatabaseService") -> None:
        self._db = db

    async def get(self, file_id: UUID) -> File | None:
        async with self._db.session() as session:
            return await session.get(File, file_id)

    async def get_for_user(self, file_id: UUID, user_id: UUID) -> File | None:
        async with self._db.session() as session:
            row = await session.get(File, file_id)
            if row is None or row.is_deleted or row.user_id != user_id:
                return None
            return row

    async def list_for_session(self, session_id: UUID) -> list[File]:
        async with self._db.session() as session:
            result = await session.exec(
                select(File)
                .where(File.session_id == session_id)
                .where(File.is_deleted == False)  # noqa: E712
                .order_by(File.created_at)
            )
            return list(result.all())

    async def get_many_for_user(
        self, file_ids: list[UUID], user_id: UUID
    ) -> list[File]:
        if not file_ids:
            return []
        async with self._db.session() as session:
            result = await session.exec(
                select(File)
                .where(File.id.in_(file_ids))  # type: ignore[attr-defined]
                .where(File.user_id == user_id)
                .where(File.is_deleted == False)  # noqa: E712
            )
            return list(result.all())

    async def soft_delete(self, file_id: UUID, user_id: UUID) -> bool:
        async with self._db.session() as session:
            row = await session.get(File, file_id)
            if row is None or row.is_deleted or row.user_id != user_id:
                return False
            row.is_deleted = True
            row.deleted_at = datetime.now(UTC)
            session.add(row)
            return True
