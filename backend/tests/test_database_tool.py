"""Tests for the real-database ``database`` tool (SQLite + sandbox)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import pytest

from leagent.tools._sandbox.paths import reset_roots
from leagent.tools.base import ToolContext, ToolResult


def _ctx() -> ToolContext:
    return ToolContext(user_id="u1", session_id="s1")


async def _run_database(params: dict[str, Any], ctx: ToolContext | None = None) -> ToolResult:
    from leagent.tools.db.database_tool import DatabaseTool

    tool = DatabaseTool()
    return await tool.run(params, ctx or _ctx())


@pytest.fixture(autouse=True)
def _reset_sandbox():
    saved = os.environ.get("LEAGENT_TOOL_FILE_ROOTS")
    yield
    if saved is None:
        os.environ.pop("LEAGENT_TOOL_FILE_ROOTS", None)
    else:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = saved
    reset_roots()


@pytest.mark.asyncio
class TestDatabaseToolSQLite:
    async def test_create_query_execute_list_describe(self, tmp_path: Path) -> None:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()

        session = tmp_path / "s1"
        session.mkdir()
        dbfile = f"session_{uuid.uuid4().hex[:10]}.db"

        r = await _run_database({
            "operation": "create_sqlite",
            "sqlite_path": dbfile,
            "kind": "sqlite",
            "overwrite": True,
        })
        assert r.success
        db_path = r.data["sqlite_path"]
        assert Path(db_path).is_file()

        r2 = await _run_database({
            "operation": "execute",
            "sqlite_path": db_path,
            "sql": "CREATE TABLE t1 (id INTEGER PRIMARY KEY, name TEXT)",
            "kind": "sqlite",
        })
        assert r2.success

        r3 = await _run_database({
            "operation": "query",
            "sqlite_path": db_path,
            "sql": "SELECT name FROM sqlite_master WHERE type='table'",
            "kind": "sqlite",
        })
        assert r3.success
        assert any("t1" in str(row) for row in r3.data.get("rows", []))

        r4 = await _run_database({"operation": "list_tables", "sqlite_path": db_path})
        assert r4.success
        assert "t1" in r4.data["tables"]

        r5 = await _run_database({
            "operation": "describe_table",
            "sqlite_path": db_path,
            "table_name": "t1",
        })
        assert r5.success
        assert len(r5.data["columns"]) >= 2

        r6 = await _run_database({"operation": "test_connection", "sqlite_path": db_path})
        assert r6.success

    async def test_query_rejects_insert(self, tmp_path: Path) -> None:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()
        session = tmp_path / "s1"
        session.mkdir()
        p = session / "a.db"
        cx = __import__("sqlite3").connect(str(p))
        cx.execute("CREATE TABLE x (a int)")
        cx.commit()
        cx.close()

        r = await _run_database({
            "operation": "query",
            "sqlite_path": str(p),
            "sql": "INSERT INTO x VALUES (1)",
        })
        assert not r.success

    async def test_multi_statement_rejected(self, tmp_path: Path) -> None:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()
        session = tmp_path / "s1"
        session.mkdir()
        p = session / "b.db"
        import sqlite3

        c = sqlite3.connect(str(p))
        c.execute("CREATE TABLE y (a int)")
        c.commit()
        c.close()

        r = await _run_database({
            "operation": "execute",
            "sqlite_path": str(p),
            "sql": "SELECT 1; SELECT 2",
        })
        assert not r.success

    async def test_remote_url_denied_without_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()
        monkeypatch.delenv("LEAGENT_DATABASE_TOOL_REMOTE", raising=False)

        r = await _run_database({
            "operation": "test_connection",
            "kind": "postgresql",
            "database_url": "postgresql+psycopg2://user:pass@localhost:5432/db",
        })
        assert not r.success
        assert "remote" in (r.error or "").lower() or "disabled" in (r.error or "").lower()

    async def test_drop_requires_confirm(self, tmp_path: Path) -> None:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()
        session = tmp_path / "s1"
        session.mkdir()
        p = session / "c.db"
        import sqlite3

        c = sqlite3.connect(str(p))
        c.execute("CREATE TABLE z (a int)")
        c.commit()
        c.close()

        r = await _run_database({
            "operation": "execute",
            "sqlite_path": str(p),
            "sql": "DROP TABLE z",
        })
        assert not r.success

        r2 = await _run_database({
            "operation": "execute",
            "sqlite_path": str(p),
            "sql": "DROP TABLE IF EXISTS z",
            "confirm_destructive": True,
        })
        assert r2.success
