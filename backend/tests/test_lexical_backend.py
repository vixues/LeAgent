"""Lexical backend dialect helpers."""

from __future__ import annotations

from sqlalchemy import ColumnElement

from leagent.memory.lexical_backend import column_text_match, session_dialect


def test_session_dialect_fallback_on_error() -> None:
    class _BadSession:
        def get_bind(self):
            raise RuntimeError("no bind")

    assert session_dialect(_BadSession()) == "sqlite"


def test_column_match_sqlite_is_ilike() -> None:
    class _Col:
        def ilike(self, pattern: str) -> object:
            return ("ilike", pattern)

    col = _Col()
    expr = column_text_match(col, "hello", "sqlite")
    assert expr == ("ilike", "%hello%")


def test_column_match_postgres_is_tsvector() -> None:
    from leagent.db.models.agent_memory import AgentEpisode

    expr = column_text_match(AgentEpisode.summary, "budget report", "postgresql")
    assert isinstance(expr, ColumnElement)
