"""Procedural memory — outcomes of multi-step tool chains and workflows.

Whenever the agent completes a recognisable "procedure" (a workflow, a
tool chain, a task that decomposes into ordered steps), :meth:`record`
upserts a row keyed by ``(user_id, workspace_id, signature)``. The
signature should be a deterministic digest of "what the procedure is"
(intent + ordered tool names), so two runs of the same procedure collapse
to one row and we keep aggregate statistics.

The goal is to let the agent pattern-match: "I've done this kind of thing
before, and last time it succeeded/failed like so."
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Iterable
from uuid import UUID

from sqlmodel import select

from leagent.memory.lexical_backend import or_text_match, session_dialect
from leagent.memory.types import MemoryKind, Procedure, RecallEntry
from leagent.memory.vector import MilvusCollection, MilvusConnectionConfig, VectorWriteResult
from leagent.services.database.models.agent_memory import AgentProcedure

if TYPE_CHECKING:
    from leagent.memory.embeddings import EmbeddingProvider
    from leagent.services.database.service import DatabaseService

logger = logging.getLogger(__name__)

COLLECTION_NAME = "agent_memory_procedures"


def _utc_now() -> datetime:
    """Naive UTC for :class:`~leagent.services.database.models.base.BaseModel` timestamps."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_signature(intent: str, tool_names: Iterable[str]) -> str:
    """Canonical hash for ``(intent, sorted tool names)``."""
    tools = sorted({(t or "").strip() for t in tool_names if t})
    payload = (intent or "").strip().lower() + "\x00" + ",".join(tools)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ProceduralStore:
    """Durable store for tool-chain outcomes."""

    def __init__(
        self,
        *,
        database: DatabaseService,
        embeddings: EmbeddingProvider,
        vector_connection: MilvusConnectionConfig | None = None,
    ) -> None:
        self._db = database
        self._embeddings = embeddings
        self.last_vector_write: VectorWriteResult | None = None
        self._collection = MilvusCollection(
            name=COLLECTION_NAME,
            dimension=embeddings.dimension,
            description="LeAgent procedural memory",
            connection=vector_connection,
        )

    @property
    def collection(self) -> MilvusCollection:
        return self._collection

    # -- write ----------------------------------------------------------

    async def record(
        self,
        procedure: Procedure,
        *,
        outcome: str,
        success: bool,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> Procedure:
        """Upsert a procedure row and record one run.

        The caller is responsible for setting ``procedure.signature`` before
        calling (use :func:`build_signature`). ``procedure.run_count`` /
        ``success_count`` are maintained by the store.
        """
        if not procedure.signature:
            raise ValueError("Procedure.signature is required")
        if not procedure.description.strip():
            logger.debug("skipping_empty_procedure")
            return procedure

        should_write_vector = self._collection.can_write
        vector = (
            await self._embeddings.embed_one(procedure.description)
            if should_write_vector
            else None
        )
        model_name = getattr(self._embeddings, "model", None) if vector is not None else None
        now = _utc_now()

        async with self._db.session() as db:
            stmt = select(AgentProcedure).where(
                AgentProcedure.signature == procedure.signature,
                AgentProcedure.user_id == procedure.user_id,
            )
            if procedure.workspace_id is None:
                stmt = stmt.where(AgentProcedure.workspace_id.is_(None))  # type: ignore[attr-defined]
            else:
                stmt = stmt.where(
                    AgentProcedure.workspace_id == procedure.workspace_id
                )
            result = await db.exec(stmt)
            row = result.first()

            if row is None:
                row = AgentProcedure(
                    id=procedure.id,
                    user_id=procedure.user_id,
                    workspace_id=procedure.workspace_id,
                    name=procedure.name,
                    signature=procedure.signature,
                    description=procedure.description,
                    run_count=1,
                    success_count=1 if success else 0,
                    last_outcome=outcome,
                    last_error=error,
                    last_duration_ms=duration_ms,
                    last_run_at=now,
                    vector_id=str(procedure.id) if vector is not None else None,
                    embedding_model=str(model_name) if model_name else None,
                )
                db.add(row)
            else:
                row.name = procedure.name or row.name
                row.description = procedure.description or row.description
                row.run_count = int(row.run_count or 0) + 1
                if success:
                    row.success_count = int(row.success_count or 0) + 1
                row.last_outcome = outcome
                row.last_error = error
                row.last_duration_ms = duration_ms
                row.last_run_at = now
                if vector is not None:
                    row.vector_id = str(row.id)
                if model_name:
                    row.embedding_model = str(model_name)
                procedure.id = row.id

        if vector is None:
            self.last_vector_write = VectorWriteResult(
                written=False,
                degraded=True,
                error=self._collection.last_error or "milvus_optional_off",
            )
        else:
            self.last_vector_write = await self._collection.upsert(
                row_id=str(procedure.id),
                vector=vector,
                user_id=str(procedure.user_id) if procedure.user_id else None,
                scope=procedure.signature,
            )
        procedure.run_count = (procedure.run_count or 0) + 1
        if success:
            procedure.success_count = (procedure.success_count or 0) + 1
        procedure.last_outcome = outcome
        procedure.last_error = error
        procedure.last_duration_ms = duration_ms
        procedure.last_run_at = now
        return procedure

    # -- read -----------------------------------------------------------

    async def get_by_signature(
        self,
        signature: str,
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
    ) -> Procedure | None:
        async with self._db.session() as db:
            stmt = select(AgentProcedure).where(AgentProcedure.signature == signature)
            if user_id is not None:
                stmt = stmt.where(AgentProcedure.user_id == user_id)
            if workspace_id is None:
                stmt = stmt.where(AgentProcedure.workspace_id.is_(None))  # type: ignore[attr-defined]
            else:
                stmt = stmt.where(AgentProcedure.workspace_id == workspace_id)
            result = await db.exec(stmt)
            row = result.first()
        return _row_to_procedure(row) if row else None

    async def list_recent_for_user(
        self,
        *,
        user_id: UUID,
        limit: int = 30,
    ) -> list[Procedure]:
        """Recent procedure rows for a user (workspace-agnostic browse)."""
        async with self._db.session() as db:
            stmt = (
                select(AgentProcedure)
                .where(AgentProcedure.user_id == user_id)
                .order_by(
                    AgentProcedure.last_run_at.desc().nulls_last(),
                    AgentProcedure.created_at.desc(),
                )
                .limit(max(1, limit))
            )
            result = await db.exec(stmt)
            rows = list(result.all())
        return [_row_to_procedure(r) for r in rows]

    async def lexical_search(
        self,
        query: str,
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 10,
    ) -> list[RecallEntry]:
        if not query.strip():
            return []
        q = query.strip()
        async with self._db.session() as db:
            dialect = session_dialect(db)
            text_or = or_text_match(
                [AgentProcedure.description, AgentProcedure.name],  # type: ignore[list-item]
                q,
                dialect,
            )
            stmt = select(AgentProcedure).where(text_or)
            if user_id is not None:
                stmt = stmt.where(AgentProcedure.user_id == user_id)
            if workspace_id is not None:
                stmt = stmt.where(AgentProcedure.workspace_id == workspace_id)
            stmt = stmt.order_by(AgentProcedure.last_run_at.desc().nulls_last()).limit(
                max(1, limit)
            )
            result = await db.exec(stmt)
            rows = list(result.all())
        return [_row_to_recall(r, score=0.45) for r in rows]

    async def semantic_search(
        self,
        vector: list[float],
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 10,
    ) -> list[RecallEntry]:
        """Vector search scoped by ``user_id``; rows are filtered by ``workspace_id``
        after PG load so Milvus (which stores procedure signature in ``scope``) cannot
        return procedures from another workspace for the same user.
        """
        hits = await self._collection.search(
            vector=vector,
            limit=limit,
            user_id=str(user_id) if user_id else None,
        )
        if not hits:
            return []
        row_ids = {row_id for row_id, _ in hits}
        async with self._db.session() as db:
            stmt = select(AgentProcedure).where(
                AgentProcedure.id.in_([UUID(r) for r in row_ids])  # type: ignore[attr-defined]
            )
            result = await db.exec(stmt)
            rows = {str(r.id): r for r in result.all()}

        entries: list[RecallEntry] = []
        for row_id, score in hits:
            row = rows.get(row_id)
            if row is None:
                continue
            if workspace_id is not None and row.workspace_id is not None:
                if row.workspace_id != workspace_id:
                    continue
            entries.append(_row_to_recall(row, score=score))
        return entries


def _row_to_procedure(row: AgentProcedure) -> Procedure:
    return Procedure(
        id=row.id,
        user_id=row.user_id,
        workspace_id=row.workspace_id,
        name=row.name,
        signature=row.signature,
        description=row.description,
        run_count=int(row.run_count or 0),
        success_count=int(row.success_count or 0),
        last_outcome=row.last_outcome,
        last_error=row.last_error,
        last_duration_ms=row.last_duration_ms,
        last_run_at=row.last_run_at,
        created_at=row.created_at,
    )


def _row_to_recall(row: AgentProcedure, *, score: float) -> RecallEntry:
    success_rate = 0.0
    if row.run_count:
        success_rate = max(0.0, min(1.0, (row.success_count or 0) / row.run_count))
    text = (
        f"{row.name} — {row.description.strip()} "
        f"(ran {row.run_count or 0}×, success {success_rate:.0%})"
    )
    return RecallEntry(
        kind=MemoryKind.PROCEDURAL,
        text=text,
        score=score,
        source_id=row.id,
        metadata={
            "signature": row.signature,
            "run_count": int(row.run_count or 0),
            "success_rate": success_rate,
            "last_outcome": row.last_outcome,
            "last_run_at": (
                row.last_run_at.isoformat() if row.last_run_at else None
            ),
        },
    )


__all__ = ["ProceduralStore", "COLLECTION_NAME", "build_signature"]
