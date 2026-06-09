"""Built-in checkpoint store implementations.

The :class:`InMemoryCheckpointStore` is the default for single-process
deployments and tests. :class:`SQLCheckpointStore` is the durable,
multi-worker backend that persists checkpoints to the database
(``agent_checkpoints`` table) for resume across process restarts.
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from leagent.sdk.protocols import Checkpoint, CheckpointStore

if TYPE_CHECKING:
    from leagent.db.models.agent_checkpoint import AgentCheckpoint


class InMemoryCheckpointStore:
    """Non-durable, in-process checkpoint store (default/test).

    Satisfies :class:`~leagent.sdk.protocols.CheckpointStore`.
    """

    def __init__(self) -> None:
        self._store: dict[str, Checkpoint] = {}

    async def save(self, checkpoint: Checkpoint) -> None:
        if not checkpoint.checkpoint_id:
            checkpoint.checkpoint_id = uuid.uuid4().hex
        self._store[checkpoint.checkpoint_id] = checkpoint

    async def load(self, checkpoint_id: str) -> Checkpoint | None:
        return self._store.get(checkpoint_id)

    async def delete(self, checkpoint_id: str) -> None:
        self._store.pop(checkpoint_id, None)

    async def list_for_session(self, session_id: str) -> list[Checkpoint]:
        return [
            cp for cp in self._store.values()
            if cp.session_id == session_id
        ]

    def clear(self) -> None:
        """Remove all checkpoints (test helper)."""
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


class SQLCheckpointStore:
    """Durable, database-backed checkpoint store.

    Persists checkpoints to the ``agent_checkpoints`` table via
    :class:`~leagent.db.repositories.agent_checkpoint.DbCheckpointRepository`,
    so a run paused on one worker can be resumed on another (Codex
    ``RolloutRecorder`` / Claude ``SessionStore`` analogue). Satisfies
    :class:`~leagent.sdk.protocols.CheckpointStore`.
    """

    def __init__(self, database_service: Any) -> None:
        self._db = database_service

    @staticmethod
    def _encode_payload(checkpoint: Checkpoint) -> str:
        return json.dumps(
            {
                "messages": checkpoint.messages,
                "usage": checkpoint.usage,
                "metadata": checkpoint.metadata,
            },
            ensure_ascii=False,
            default=str,
        )

    @staticmethod
    def _row_to_checkpoint(row: "AgentCheckpoint") -> Checkpoint:
        try:
            payload = json.loads(row.payload or "{}")
        except (json.JSONDecodeError, ValueError):
            payload = {}
        return Checkpoint(
            checkpoint_id=row.checkpoint_id,
            session_id=row.session_id,
            agent_name=row.agent_name,
            turn=row.turn,
            messages=list(payload.get("messages") or []),
            reason=row.reason,
            usage=dict(payload.get("usage") or {}),
            metadata=dict(payload.get("metadata") or {}),
        )

    async def save(self, checkpoint: Checkpoint) -> None:
        if not checkpoint.checkpoint_id:
            checkpoint.checkpoint_id = uuid.uuid4().hex
        await self._db.repositories.checkpoints.upsert(
            checkpoint_id=checkpoint.checkpoint_id,
            session_id=checkpoint.session_id,
            agent_name=checkpoint.agent_name,
            turn=checkpoint.turn,
            reason=checkpoint.reason,
            payload=self._encode_payload(checkpoint),
        )

    async def load(self, checkpoint_id: str) -> Checkpoint | None:
        row = await self._db.repositories.checkpoints.get(checkpoint_id)
        return self._row_to_checkpoint(row) if row is not None else None

    async def delete(self, checkpoint_id: str) -> None:
        await self._db.repositories.checkpoints.delete(checkpoint_id)

    async def list_for_session(self, session_id: str) -> list[Checkpoint]:
        rows = await self._db.repositories.checkpoints.list_for_session(session_id)
        return [self._row_to_checkpoint(r) for r in rows]


def build_checkpoint_store(database_service: Any) -> CheckpointStore | None:
    """Build the best available checkpoint store for the given services.

    Returns a durable :class:`SQLCheckpointStore` when a database service is
    present, else ``None`` so the runtime falls back to its in-memory default.
    """
    if database_service is None:
        return None
    return SQLCheckpointStore(database_service)


def create_checkpoint(
    *,
    session_id: str,
    agent_name: str,
    turn: int,
    messages: list[dict[str, Any]] | None = None,
    reason: str = "awaiting_user_input",
    usage: dict[str, int] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Checkpoint:
    """Convenience factory for :class:`Checkpoint`."""
    return Checkpoint(
        checkpoint_id=uuid.uuid4().hex,
        session_id=session_id,
        agent_name=agent_name,
        turn=turn,
        messages=list(messages or []),
        reason=reason,
        usage=dict(usage or {}),
        metadata=dict(metadata or {}),
    )


__all__ = [
    "InMemoryCheckpointStore",
    "SQLCheckpointStore",
    "build_checkpoint_store",
    "create_checkpoint",
]
