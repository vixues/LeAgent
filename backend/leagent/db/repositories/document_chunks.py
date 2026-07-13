"""Document-chunk persistence + chunk-level knowledge retrieval.

Writes go through :meth:`DbDocumentChunkRepository.replace_for_file` (idempotent
re-index of a single file). Reads use BM25 over the SQLite FTS5 index when
available and fall back to a portable ``ILIKE`` scan on PostgreSQL / when the
FTS table is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlmodel import delete, select

from leagent.db.models.document_chunk import DocumentChunk
from leagent.library.chunking import Chunk
from leagent.library.fts import FTS_TABLE, escape_fts_query
from leagent.memory.lexical_backend import session_dialect

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService


@dataclass
class ChunkHit:
    """A single chunk-level search result grounded in a source file."""

    chunk_id: UUID
    file_id: UUID
    file_name: str
    seq: int
    start_offset: int
    end_offset: int
    text: str
    snippet: str
    score: float


class DocumentChunkRepository(Protocol):
    async def replace_for_file(
        self, file_id: UUID, user_id: UUID | None, chunks: list[Chunk]
    ) -> int: ...

    async def delete_for_file(self, file_id: UUID) -> int: ...

    async def search(
        self,
        user_id: UUID | None,
        query: str,
        *,
        limit: int = 20,
        library_scope: str | None = None,
    ) -> list[ChunkHit]: ...


class DbDocumentChunkRepository:
    """``DatabaseService``-backed :class:`DocumentChunkRepository`."""

    def __init__(self, db: "DatabaseService") -> None:
        self._db = db

    async def replace_for_file(
        self, file_id: UUID, user_id: UUID | None, chunks: list[Chunk]
    ) -> int:
        async with self._db.session() as session:
            await session.exec(
                delete(DocumentChunk).where(DocumentChunk.file_id == file_id)
            )
            for chunk in chunks:
                session.add(
                    DocumentChunk(
                        file_id=file_id,
                        user_id=user_id,
                        seq=chunk.seq,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        text=chunk.text,
                    )
                )
            return len(chunks)

    async def delete_for_file(self, file_id: UUID) -> int:
        async with self._db.session() as session:
            result = await session.exec(
                select(DocumentChunk.id).where(DocumentChunk.file_id == file_id)
            )
            ids = list(result.all())
            if ids:
                await session.exec(
                    delete(DocumentChunk).where(DocumentChunk.file_id == file_id)
                )
            return len(ids)

    async def search(
        self,
        user_id: UUID | None,
        query: str,
        *,
        limit: int = 20,
        library_scope: str | None = None,
    ) -> list[ChunkHit]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as session:
            dialect = session_dialect(session)
            if dialect == "sqlite" and await self._fts_available(session):
                hits = await self._search_fts(
                    session, user_id, query, limit, library_scope
                )
                if hits is not None:
                    return hits
            return await self._search_lexical(
                session, user_id, query, limit, library_scope
            )

    # ── internals ────────────────────────────────────────────────

    async def _fts_available(self, session) -> bool:
        try:
            result = await session.execute(
                sa.text(
                    "SELECT 1 FROM sqlite_master "
                    "WHERE type='table' AND name=:name"
                ),
                {"name": FTS_TABLE},
            )
            return result.first() is not None
        except Exception:
            return False

    async def _search_fts(
        self,
        session,
        user_id: UUID | None,
        query: str,
        limit: int,
        library_scope: str | None,
    ) -> list[ChunkHit] | None:
        match_expr = escape_fts_query(query)
        if not match_expr:
            return []
        # SQLite may persist UUIDs as dashed or hex-only text; compare both.
        user_id_dashed = str(user_id) if user_id else None
        user_id_hex = user_id_dashed.replace("-", "") if user_id_dashed else None
        # SQLModel/SQLite may store Enum by name ("KNOWLEDGE") or value ("knowledge").
        scope_value, scope_name = _scope_variants(library_scope)
        sql = sa.text(
            f"""
            SELECT dc.id AS chunk_id, dc.file_id AS file_id, dc.seq AS seq,
                   dc.start_offset AS start_offset, dc.end_offset AS end_offset,
                   dc.text AS text,
                   f.name AS file_name,
                   bm25({FTS_TABLE}) AS score,
                   snippet({FTS_TABLE}, 0, '[', ']', ' … ', 16) AS snippet
            FROM {FTS_TABLE}
            JOIN document_chunks dc ON dc.rowid = {FTS_TABLE}.rowid
            JOIN files f ON f.id = dc.file_id
            WHERE {FTS_TABLE} MATCH :match
              AND f.is_deleted = 0
              AND (
                    :user_id_dashed IS NULL
                    OR lower(replace(CAST(dc.user_id AS TEXT), '-', ''))
                       = lower(:user_id_hex)
                  )
              AND (
                    :scope_value IS NULL
                    OR f.library_scope = :scope_value
                    OR f.library_scope = :scope_name
                  )
            ORDER BY score
            LIMIT :limit
            """
        )
        try:
            result = await session.execute(
                sql,
                {
                    "match": match_expr,
                    "user_id_dashed": user_id_dashed,
                    "user_id_hex": user_id_hex,
                    "scope_value": scope_value,
                    "scope_name": scope_name,
                    "limit": limit,
                },
            )
        except Exception:
            return None
        return [self._row_to_hit(row, score=-float(row.score)) for row in result]

    async def _search_lexical(
        self,
        session,
        user_id: UUID | None,
        query: str,
        limit: int,
        library_scope: str | None,
    ) -> list[ChunkHit]:
        from leagent.db.models.file import File

        stmt = (
            select(DocumentChunk, File.name)
            .join(File, File.id == DocumentChunk.file_id)
            .where(File.is_deleted == False)  # noqa: E712
            .where(DocumentChunk.text.ilike(f"%{query}%"))  # type: ignore[attr-defined]
        )
        if user_id is not None:
            stmt = stmt.where(DocumentChunk.user_id == user_id)
        if library_scope is not None:
            from leagent.db.models.file import LibraryScope as _LibraryScope

            try:
                scope_enum = _LibraryScope(str(library_scope).lower())
            except ValueError:
                scope_enum = _LibraryScope[str(library_scope).upper()]
            stmt = stmt.where(File.library_scope == scope_enum)
        stmt = stmt.limit(limit)
        result = await session.exec(stmt)
        hits: list[ChunkHit] = []
        for chunk, file_name in result.all():
            hits.append(
                ChunkHit(
                    chunk_id=chunk.id,
                    file_id=chunk.file_id,
                    file_name=file_name or "",
                    seq=chunk.seq,
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    text=chunk.text,
                    snippet=_lexical_snippet(chunk.text, query),
                    score=1.0,
                )
            )
        return hits

    @staticmethod
    def _row_to_hit(row, *, score: float) -> ChunkHit:
        return ChunkHit(
            chunk_id=_as_uuid(row.chunk_id),
            file_id=_as_uuid(row.file_id),
            file_name=row.file_name or "",
            seq=int(row.seq),
            start_offset=int(row.start_offset),
            end_offset=int(row.end_offset),
            text=row.text or "",
            snippet=row.snippet or "",
            score=score,
        )


def _as_uuid(value) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _scope_variants(library_scope: str | None) -> tuple[str | None, str | None]:
    """Return ``(value, NAME)`` forms for SQLite enum storage drift."""
    if library_scope is None:
        return None, None
    raw = str(library_scope).strip()
    if not raw:
        return None, None
    return raw.lower(), raw.upper()


def _lexical_snippet(text: str, query: str, *, radius: int = 120) -> str:
    lower = text.lower()
    idx = lower.find(query.lower())
    if idx < 0:
        return text[: radius * 2].strip()
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query) + radius)
    prefix = "… " if start > 0 else ""
    suffix = " …" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"
