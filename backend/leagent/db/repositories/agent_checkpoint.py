"""Agent-run checkpoint persistence repository."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlmodel import select

from leagent.db.models.agent_checkpoint import AgentCheckpoint

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService


class CheckpointRepository(Protocol):
    """Protocol for durable agent-run checkpoint persistence."""

    async def upsert(
        self,
        *,
        checkpoint_id: str,
        session_id: str,
        agent_name: str,
        turn: int,
        reason: str,
        payload: str,
    ) -> None:
        """Insert or replace the checkpoint identified by *checkpoint_id*."""
        ...

    async def get(self, checkpoint_id: str) -> AgentCheckpoint | None:
        """Return the checkpoint row for *checkpoint_id*."""
        ...

    async def delete(self, checkpoint_id: str) -> None:
        """Delete the checkpoint identified by *checkpoint_id*."""
        ...

    async def list_for_session(self, session_id: str) -> list[AgentCheckpoint]:
        """Return checkpoints for *session_id*, newest first."""
        ...


class DbCheckpointRepository:
    """``DatabaseService``-backed :class:`CheckpointRepository`."""

    def __init__(self, db: "DatabaseService") -> None:
        self._db = db

    async def upsert(
        self,
        *,
        checkpoint_id: str,
        session_id: str,
        agent_name: str,
        turn: int,
        reason: str,
        payload: str,
    ) -> None:
        async with self._db.session() as session:
            result = await session.exec(
                select(AgentCheckpoint).where(
                    AgentCheckpoint.checkpoint_id == checkpoint_id
                )
            )
            row = result.first()
            if row is None:
                row = AgentCheckpoint(checkpoint_id=checkpoint_id)
            row.session_id = session_id
            row.agent_name = agent_name
            row.turn = turn
            row.reason = reason
            row.payload = payload
            session.add(row)

    async def get(self, checkpoint_id: str) -> AgentCheckpoint | None:
        async with self._db.session() as session:
            result = await session.exec(
                select(AgentCheckpoint).where(
                    AgentCheckpoint.checkpoint_id == checkpoint_id
                )
            )
            return result.first()

    async def delete(self, checkpoint_id: str) -> None:
        async with self._db.session() as session:
            result = await session.exec(
                select(AgentCheckpoint).where(
                    AgentCheckpoint.checkpoint_id == checkpoint_id
                )
            )
            row = result.first()
            if row is not None:
                await session.delete(row)

    async def list_for_session(self, session_id: str) -> list[AgentCheckpoint]:
        async with self._db.session() as session:
            result = await session.exec(
                select(AgentCheckpoint)
                .where(AgentCheckpoint.session_id == session_id)
                .order_by(AgentCheckpoint.created_at.desc())
            )
            return list(result.all())


__all__ = ["CheckpointRepository", "DbCheckpointRepository"]
