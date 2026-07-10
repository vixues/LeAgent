"""Document chunk model — the knowledge Storage Layer's addressable spans.

A :class:`DocumentChunk` is an immutable, offset-addressed slice of a source
file's extracted text. Chunks are the substrate for lexical/BM25 retrieval
(``document_chunks_fts`` on SQLite; lexical fallback on PostgreSQL) and the
grounding target for the future EOKA Evidence Layer — each chunk records the
exact ``[start_offset, end_offset)`` span so citations are verifiable back to
the original document.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlmodel import Column, Field, SQLModel, Text

from leagent.db.models.base import BaseModel


class DocumentChunk(BaseModel, table=True):
    """An offset-addressed chunk of a file's extracted text."""

    __tablename__ = "document_chunks"

    file_id: UUID = Field(foreign_key="files.id", index=True)
    user_id: Optional[UUID] = Field(default=None, index=True)
    seq: int = Field(default=0)
    start_offset: int = Field(default=0)
    end_offset: int = Field(default=0)
    text: str = Field(sa_column=Column(Text))


class DocumentChunkRead(SQLModel):
    """Read schema for a chunk (used by knowledge search results)."""

    id: UUID
    file_id: UUID
    seq: int
    start_offset: int
    end_offset: int
    text: str
