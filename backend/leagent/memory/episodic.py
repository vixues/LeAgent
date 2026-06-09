"""Episodic memory — "what happened in past turns".

Each write corresponds to one user/assistant exchange the agent has
finished: the :class:`Episode` carries a short summary plus metadata
(session, user, tags), we dual-write to the SQL database and Milvus, and the row
UUID is used as both the ORM primary key and the Milvus row id so recall
can join them trivially.

The store is intentionally small. Summarisation and tagging are handled by
the agent runtime before calling :meth:`record` — this module just
persists.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlmodel import select

from leagent.memory.lexical_backend import column_text_match, session_dialect
from leagent.memory.types import Episode, MemoryKind, RecallEntry
from leagent.memory.vector import MilvusCollection, MilvusConnectionConfig
from leagent.db.models.agent_memory import AgentEpisode

if TYPE_CHECKING:
    from leagent.memory.embeddings import EmbeddingProvider
    from leagent.db.service import DatabaseService

logger = logging.getLogger(__name__)

COLLECTION_NAME = "agent_memory_episodes"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EpisodicStore:
    """Durable store for past-turn summaries."""

    def __init__(
        self,
        *,
        database: DatabaseService,
        embeddings: EmbeddingProvider,
        vector_connection: MilvusConnectionConfig | None = None,
    ) -> None:
        self._db = database
        self._embeddings = embeddings
        self._collection = MilvusCollection(
            name=COLLECTION_NAME,
            dimension=embeddings.dimension,
            description="LeAgent episodic memory",
            connection=vector_connection,
        )

    @property
    def collection(self) -> MilvusCollection:
        return self._collection

    # -- write ----------------------------------------------------------

    async def record(self, episode: Episode) -> Episode:
        """Persist an episode to the database + Milvus. Returns the stored copy."""
        if not episode.summary.strip():
            logger.debug("skipping_empty_episode")
            return episode

        if not episode.id:
            episode.id = uuid4()

        should_write_vector = self._collection.can_write
        vector = (
            await self._embeddings.embed_one(episode.summary)
            if should_write_vector
            else None
        )
        model_name = getattr(self._embeddings, "model", None) if vector is not None else None

        async with self._db.session() as db:
            row = AgentEpisode(
                id=episode.id,
                session_id=episode.session_id,
                user_id=episode.user_id,
                workspace_id=episode.workspace_id,
                flow_id=episode.flow_id,
                summary=episode.summary,
                transcript=episode.transcript,
                tags=json.dumps(episode.tags) if episode.tags else None,
                vector_id=str(episode.id) if vector is not None else None,
                embedding_model=str(model_name) if model_name else None,
                importance=float(episode.importance),
                token_count=episode.token_count,
            )
            db.add(row)

        if vector is not None:
            await self._collection.upsert(
                row_id=str(episode.id),
                vector=vector,
                user_id=str(episode.user_id) if episode.user_id else None,
                scope=str(episode.session_id),
            )
        return episode

    async def delete(self, episode_id: UUID) -> None:
        async with self._db.session() as db:
            row = await db.get(AgentEpisode, episode_id)
            if row is None:
                return
            await db.delete(row)
        await self._collection.delete(str(episode_id))

    # -- read -----------------------------------------------------------

    async def list_recent(
        self,
        *,
        session_id: UUID | None = None,
        user_id: UUID | None = None,
        limit: int = 10,
    ) -> list[Episode]:
        async with self._db.session() as db:
            stmt = select(AgentEpisode)
            if session_id is not None:
                stmt = stmt.where(AgentEpisode.session_id == session_id)
            if user_id is not None:
                stmt = stmt.where(AgentEpisode.user_id == user_id)
            stmt = stmt.order_by(AgentEpisode.created_at.desc()).limit(max(1, limit))
            result = await db.exec(stmt)
            rows = list(result.all())
        return [_row_to_episode(r) for r in rows]

    async def lexical_search(
        self,
        query: str,
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        limit: int = 10,
    ) -> list[RecallEntry]:
        """ILIKE fallback when no embedding match is available."""
        if not query.strip():
            return []
        q = query.strip()
        async with self._db.session() as db:
            dialect = session_dialect(db)
            match_expr = column_text_match(AgentEpisode.summary, q, dialect)
            stmt = select(AgentEpisode).where(match_expr)
            if user_id is not None:
                stmt = stmt.where(AgentEpisode.user_id == user_id)
            if session_id is not None:
                stmt = stmt.where(AgentEpisode.session_id == session_id)
            stmt = stmt.order_by(AgentEpisode.created_at.desc()).limit(max(1, limit))
            result = await db.exec(stmt)
            rows = list(result.all())
        return [_row_to_recall(r, score=0.4) for r in rows]

    async def semantic_search(
        self,
        vector: list[float],
        *,
        user_id: UUID | None = None,
        session_id: UUID | None = None,
        limit: int = 10,
    ) -> list[RecallEntry]:
        """Milvus search → database lookup → :class:`RecallEntry` list."""
        hits = await self._collection.search(
            vector=vector,
            limit=limit,
            user_id=str(user_id) if user_id else None,
            scope=str(session_id) if session_id else None,
        )
        if not hits:
            return []
        row_ids = {row_id for row_id, _ in hits}
        async with self._db.session() as db:
            stmt = select(AgentEpisode).where(
                AgentEpisode.id.in_([UUID(r) for r in row_ids])  # type: ignore[attr-defined]
            )
            result = await db.exec(stmt)
            rows = {str(r.id): r for r in result.all()}

        entries: list[RecallEntry] = []
        for row_id, score in hits:
            row = rows.get(row_id)
            if row is None:
                continue
            entries.append(_row_to_recall(row, score=score))
        return entries

    async def note_recall(
        self, episode_id: UUID, *, at: datetime | None = None
    ) -> None:
        """Bump the recall counter on an episode (best-effort)."""
        timestamp = at or _utc_now()
        try:
            async with self._db.session() as db:
                row = await db.get(AgentEpisode, episode_id)
                if row is None:
                    return
                row.recall_count = int(row.recall_count or 0) + 1
                row.last_recalled_at = timestamp
        except Exception as exc:  # noqa: BLE001
            logger.debug("episodic_note_recall_failed: %s", exc)


def _row_to_episode(row: AgentEpisode) -> Episode:
    tags: list[str] = []
    if row.tags:
        try:
            decoded = json.loads(row.tags)
            if isinstance(decoded, list):
                tags = [str(t) for t in decoded]
        except (TypeError, ValueError):
            tags = []
    return Episode(
        id=row.id,
        session_id=row.session_id,
        user_id=row.user_id,
        workspace_id=row.workspace_id,
        flow_id=row.flow_id,
        summary=row.summary,
        transcript=row.transcript,
        tags=tags,
        importance=float(row.importance or 0.0),
        token_count=row.token_count,
        recall_count=int(row.recall_count or 0),
        last_recalled_at=row.last_recalled_at,
        created_at=row.created_at,
    )


def _row_to_recall(row: AgentEpisode, *, score: float) -> RecallEntry:
    metadata: dict[str, Any] = {
        "session_id": str(row.session_id),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "importance": float(row.importance or 0.0),
        "recall_count": int(row.recall_count or 0),
    }
    return RecallEntry(
        kind=MemoryKind.EPISODIC,
        text=row.summary,
        score=score,
        source_id=row.id,
        metadata=metadata,
    )


__all__ = ["EpisodicStore", "COLLECTION_NAME"]
