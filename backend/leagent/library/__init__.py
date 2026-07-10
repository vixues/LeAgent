"""Knowledge library layer: chunking + chunk-level retrieval.

This package hosts the *Storage Layer* substrate for the knowledge base:

- :mod:`leagent.library.fts` — SQLite FTS5 DDL for ``document_chunks_fts``.
- :mod:`leagent.library.chunking` — deterministic text chunking with offsets.
- :mod:`leagent.library.chunk_search` — BM25 (SQLite) / lexical (PostgreSQL)
  search over persisted chunks.

The design deliberately separates *storage objects* (files + their immutable
chunks) from *retrieval*, which is the first principle behind the follow-up
Entry-Oriented Knowledge Architecture (EOKA).
"""

from __future__ import annotations

from leagent.library.chunking import Chunk, chunk_text
from leagent.library.fts import FTS_DDL, FTS_DROP_DDL, escape_fts_query

__all__ = [
    "Chunk",
    "chunk_text",
    "FTS_DDL",
    "FTS_DROP_DDL",
    "escape_fts_query",
]
