"""Lexical fallback for recall: PostgreSQL ``tsvector`` / ``@@`` vs portable ``ILIKE``.

Milvus-offline paths still need keyword retrieval; Postgres deployments get
better relevance than substring ``ILIKE`` without pulling in an external BM25
service.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.sql.elements import ColumnElement


def session_dialect(session: Any) -> str:
    """Return SQLAlchemy dialect name (``postgresql``, ``sqlite``, …)."""
    try:
        bind = session.get_bind()
        if bind is None:
            return "sqlite"
        return str(bind.dialect.name)
    except Exception:
        return "sqlite"


def column_text_match(column: Any, query: str, dialect: str) -> ColumnElement[Any]:
    """Single-column token / substring match."""
    q = (query or "").strip()
    if dialect == "postgresql":
        ts = func.to_tsvector("english", func.coalesce(column, ""))
        pq = func.plainto_tsquery("english", q)
        return ts.op("@@")(pq)
    return column.ilike(f"%{q}%")


def or_text_match(columns: list[Any], query: str, dialect: str) -> ColumnElement[Any]:
    """OR across multiple text columns (semantic key + value, procedural name + description)."""
    parts = [column_text_match(c, query, dialect) for c in columns]
    if len(parts) == 1:
        return parts[0]
    return or_(*parts)


__all__ = ["column_text_match", "or_text_match", "session_dialect"]
