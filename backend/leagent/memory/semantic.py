"""Semantic memory — stable user / workspace facts.

Facts are upserted under a ``(user_id, workspace_id, key)`` unique key so
writing the same key twice replaces the previous value. Each fact has an
embedding in Milvus, keyed by the database row UUID, so the recall
pipeline can match facts by meaning as well as by literal key lookup.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import UUID

from sqlmodel import select

from leagent.memory.lexical_backend import or_text_match, session_dialect
from leagent.memory.types import Fact, MemoryKind, RecallEntry
from leagent.memory.vector import MilvusCollection, MilvusConnectionConfig
from leagent.db.models.agent_memory import AgentFact

if TYPE_CHECKING:
    from leagent.memory.embeddings import EmbeddingProvider
    from leagent.db.service import DatabaseService

logger = logging.getLogger(__name__)

COLLECTION_NAME = "agent_memory_facts"


class SemanticStore:
    """Durable store for user / workspace facts."""

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
            description="LeAgent semantic memory",
            connection=vector_connection,
        )

    @property
    def collection(self) -> MilvusCollection:
        return self._collection

    # -- write ----------------------------------------------------------

    async def upsert(self, fact: Fact) -> Fact:
        """Insert or update a fact under its natural upsert key."""
        if not fact.value.strip():
            logger.debug("skipping_empty_fact")
            return fact
        if not fact.key.strip():
            raise ValueError("Fact.key is required")

        should_write_vector = self._collection.can_write
        embed_text = f"{fact.key}: {fact.value}"
        vector = (
            await self._embeddings.embed_one(embed_text)
            if should_write_vector
            else None
        )
        model_name = getattr(self._embeddings, "model", None) if vector is not None else None

        async with self._db.session() as db:
            stmt = select(AgentFact).where(
                AgentFact.user_id == fact.user_id,
                AgentFact.key == fact.key,
            )
            if fact.workspace_id is None:
                stmt = stmt.where(AgentFact.workspace_id.is_(None))  # type: ignore[attr-defined]
            else:
                stmt = stmt.where(AgentFact.workspace_id == fact.workspace_id)
            result = await db.exec(stmt)
            row = result.first()

            if row is None:
                row = AgentFact(
                    id=fact.id,
                    user_id=fact.user_id,
                    workspace_id=fact.workspace_id,
                    key=fact.key,
                    value=fact.value,
                    confidence=float(fact.confidence),
                    source=fact.source,
                    vector_id=str(fact.id) if vector is not None else None,
                    embedding_model=str(model_name) if model_name else None,
                )
                db.add(row)
            else:
                row.value = fact.value
                row.confidence = float(fact.confidence)
                if fact.source:
                    row.source = fact.source
                if vector is not None:
                    row.vector_id = str(row.id)
                    row.embedding_model = str(model_name) if model_name else row.embedding_model
                fact.id = row.id

        if vector is not None:
            await self._collection.upsert(
                row_id=str(fact.id),
                vector=vector,
                user_id=str(fact.user_id),
                scope=str(fact.workspace_id) if fact.workspace_id else "global",
            )
        return fact

    async def delete(self, fact_id: UUID) -> None:
        async with self._db.session() as db:
            row = await db.get(AgentFact, fact_id)
            if row is None:
                return
            await db.delete(row)
        await self._collection.delete(str(fact_id))

    # -- read -----------------------------------------------------------

    async def get_by_key(
        self,
        *,
        user_id: UUID,
        key: str,
        workspace_id: UUID | None = None,
    ) -> Fact | None:
        async with self._db.session() as db:
            stmt = select(AgentFact).where(
                AgentFact.user_id == user_id,
                AgentFact.key == key,
            )
            if workspace_id is None:
                stmt = stmt.where(AgentFact.workspace_id.is_(None))  # type: ignore[attr-defined]
            else:
                stmt = stmt.where(AgentFact.workspace_id == workspace_id)
            result = await db.exec(stmt)
            row = result.first()
        return _row_to_fact(row) if row else None

    async def list_for_user(
        self,
        user_id: UUID,
        *,
        workspace_id: UUID | None = None,
        limit: int = 20,
    ) -> list[Fact]:
        async with self._db.session() as db:
            stmt = select(AgentFact).where(AgentFact.user_id == user_id)
            if workspace_id is not None:
                stmt = stmt.where(AgentFact.workspace_id == workspace_id)
            stmt = stmt.order_by(AgentFact.updated_at.desc()).limit(max(1, limit))
            result = await db.exec(stmt)
            rows = list(result.all())
        return [_row_to_fact(r) for r in rows]

    async def lexical_search(
        self,
        query: str,
        *,
        user_id: UUID,
        workspace_id: UUID | None = None,
        limit: int = 10,
    ) -> list[RecallEntry]:
        if not query.strip():
            return []
        q = query.strip()
        async with self._db.session() as db:
            dialect = session_dialect(db)
            text_or = or_text_match(
                [AgentFact.value, AgentFact.key],  # type: ignore[list-item]
                q,
                dialect,
            )
            stmt = select(AgentFact).where(AgentFact.user_id == user_id, text_or)
            if workspace_id is not None:
                stmt = stmt.where(AgentFact.workspace_id == workspace_id)
            stmt = stmt.order_by(AgentFact.updated_at.desc()).limit(max(1, limit))
            result = await db.exec(stmt)
            rows = list(result.all())
        return [_row_to_recall(r, score=0.5 * float(r.confidence or 0.0)) for r in rows]

    async def semantic_search(
        self,
        vector: list[float],
        *,
        user_id: UUID,
        workspace_id: UUID | None = None,
        limit: int = 10,
    ) -> list[RecallEntry]:
        hits = await self._collection.search(
            vector=vector,
            limit=limit,
            user_id=str(user_id),
            scope=str(workspace_id) if workspace_id else "global",
        )
        if not hits:
            return []
        row_ids = {row_id for row_id, _ in hits}
        async with self._db.session() as db:
            stmt = select(AgentFact).where(
                AgentFact.id.in_([UUID(r) for r in row_ids])  # type: ignore[attr-defined]
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


def _row_to_fact(row: AgentFact) -> Fact:
    return Fact(
        id=row.id,
        user_id=row.user_id,
        workspace_id=row.workspace_id,
        key=row.key,
        value=row.value,
        confidence=float(row.confidence or 0.0),
        source=row.source,
        created_at=row.created_at,
    )


def _row_to_recall(row: AgentFact, *, score: float) -> RecallEntry:
    text = f"{row.key}: {row.value}"
    return RecallEntry(
        kind=MemoryKind.SEMANTIC,
        text=text,
        score=score,
        source_id=row.id,
        metadata={
            "key": row.key,
            "confidence": float(row.confidence or 0.0),
            "source": row.source,
        },
    )


__all__ = ["SemanticStore", "COLLECTION_NAME"]
