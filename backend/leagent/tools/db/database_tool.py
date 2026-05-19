"""Real-database tool (SQLite default; optional PostgreSQL/MySQL with env gate)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine  # noqa: TC002

from leagent.tools.base import SyncTool, ToolCategory, ToolContext
from leagent.tools.db import connection as dbconn
from leagent.tools.db import inspector_ops, sql_guard

logger = structlog.get_logger(__name__)


def _dialect_for_kind(kind: str) -> str:
    k = (kind or "sqlite").lower().strip()
    if k in ("mysql", "mariadb"):
        return "mysql"
    if k == "postgresql":
        return "postgresql"
    return "sqlite"


class DatabaseTool(SyncTool):
    """Run SQL against real databases (not the in-memory ``sql_query`` tool).

    Default: SQLite file under the path sandbox (``sqlite_path``).
    Remote PostgreSQL/MySQL requires ``LEAGENT_DATABASE_TOOL_REMOTE=1`` and
    an allow-listed ``database_url``.
    """

    name = "database"
    description = (
        "Execute SQL against a real database file or (if enabled) a remote server. "
        "This is NOT ``sql_query`` (which runs SELECT-only SQL on in-memory tables / "
        "artifacts). Operations: create_sqlite, query (read-only SQL), execute "
        "(DML/DDL; destructive statements need confirm_destructive), list_tables, "
        "describe_table, test_connection. Prefer bound ``params`` (object) with "
        "named placeholders in ``sql``. Default kind is sqlite."
    )
    category = ToolCategory.DATA
    version = "1.0.0"
    timeout_sec = 120
    aliases = ["db", "rdbms", "sql_database"]
    search_hint = "sqlite postgresql mysql sql database schema table query execute ddl"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    output_path_params = ("sqlite_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "create_sqlite",
                        "query",
                        "execute",
                        "list_tables",
                        "describe_table",
                        "test_connection",
                    ],
                    "description": "Database operation to perform.",
                },
                "kind": {
                    "type": "string",
                    "enum": ["sqlite", "postgresql", "mysql", "mariadb"],
                    "description": "Database kind. Default sqlite.",
                },
                "sqlite_path": {
                    "type": "string",
                    "description": "Path to SQLite database file (sandboxed; required for sqlite kind).",
                },
                "database_url": {
                    "type": "string",
                    "description": "SQLAlchemy URL for remote DB; only when LEAGENT_DATABASE_TOOL_REMOTE=1.",
                },
                "sql": {
                    "type": "string",
                    "description": "Single SQL statement (no multiple statements separated by semicolons).",
                },
                "params": {
                    "description": (
                        "Bind parameters: object maps names to values for :name placeholders; "
                        "array maps to :p0, :p1, … in sql."
                    ),
                    "oneOf": [
                        {"type": "object", "additionalProperties": True},
                        {"type": "array"},
                    ],
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Connection / SQLite busy timeout seconds.",
                    "minimum": 1,
                    "maximum": 300,
                },
                "max_rows": {
                    "type": "integer",
                    "description": "Max rows returned for query.",
                    "minimum": 1,
                    "maximum": 100_000,
                },
                "table_name": {
                    "type": "string",
                    "description": "Table name for describe_table.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "If true, create_sqlite replaces an existing empty file target.",
                },
                "confirm_destructive": {
                    "type": "boolean",
                    "description": "Must be true for execute when SQL contains DROP, TRUNCATE, or ALTER...DROP.",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "query")
        return f"Database ({op})"

    def _engine(self, params: dict[str, Any]) -> Engine:
        kind = params.get("kind") or "sqlite"
        timeout = int(params.get("timeout_seconds") or 30)
        return dbconn.build_engine(
            kind=kind,
            sqlite_path=params.get("sqlite_path"),
            database_url=params.get("database_url"),
            timeout_seconds=timeout,
        )

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        op = params["operation"]
        kind = params.get("kind") or "sqlite"
        dialect = _dialect_for_kind(kind)

        if op == "create_sqlite":
            if (params.get("kind") or "sqlite").lower().strip() != "sqlite":
                raise ValueError("create_sqlite requires kind sqlite")
            return self._op_create_sqlite(params)
        if op == "test_connection":
            return self._op_test_connection(params, dialect)
        if op == "list_tables":
            return self._op_list_tables(params)
        if op == "describe_table":
            return self._op_describe_table(params)

        sql = params.get("sql")
        if not sql or not isinstance(sql, str):
            raise ValueError("'sql' is required and must be a non-empty string")

        bind = sql_guard.coerce_params(params.get("params"))

        if op == "query":
            sql_guard.assert_mode(sql, dialect=dialect, expected="query")
            return self._op_query(params, dialect, bind)
        if op == "execute":
            sql_guard.assert_single_statement(sql)
            if sql_guard.requires_destructive_confirm(sql) and not params.get("confirm_destructive"):
                raise ValueError(
                    "This SQL appears destructive (DROP/TRUNCATE/ALTER...DROP). "
                    "Pass confirm_destructive: true only when the user explicitly requested it."
                )
            return self._op_execute(params, bind)
        raise ValueError(f"Unknown operation: {op}")

    def _op_create_sqlite(self, params: dict[str, Any]) -> dict[str, Any]:
        path_str = params.get("sqlite_path")
        if not path_str:
            raise ValueError("sqlite_path is required for create_sqlite")
        path = Path(path_str)
        if path.exists():
            if params.get("overwrite"):
                path.unlink()
            else:
                raise ValueError(
                    f"SQLite file already exists: {path}. Pass overwrite: true to replace, "
                    "or use a different sqlite_path."
                )
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=float(params.get("timeout_seconds") or 30))
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
        logger.info("database_create_sqlite", path=str(path))
        return {"success": True, "sqlite_path": str(path.resolve())}

    def _op_test_connection(self, params: dict[str, Any], dialect: str) -> dict[str, Any]:
        eng = self._engine(params)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"success": True, "kind": params.get("kind") or "sqlite"}

    def _op_list_tables(self, params: dict[str, Any]) -> dict[str, Any]:
        eng = self._engine(params)
        names = inspector_ops.list_tables(eng)
        return {"tables": names, "count": len(names)}

    def _op_describe_table(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("table_name")
        if not name or not isinstance(name, str):
            raise ValueError("table_name is required for describe_table")
        eng = self._engine(params)
        return inspector_ops.describe_table(eng, name.strip())

    def _op_query(self, params: dict[str, Any], dialect: str, bind: dict[str, Any]) -> dict[str, Any]:
        sql = params["sql"]
        max_rows = min(int(params.get("max_rows") or 1000), 100_000)
        eng = self._engine(params)
        with eng.connect() as conn:
            result = conn.execute(text(sql), bind)
            if not result.returns_rows:
                return {"rows": [], "row_count": 0, "truncated": False, "note": "Statement did not return rows"}
            keys = list(result.keys())
            rows: list[dict[str, Any]] = []
            truncated = False
            for i, row in enumerate(result):
                if i >= max_rows:
                    truncated = True
                    break
                rows.append(dict(row._mapping))
        return {
            "columns": keys,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }

    def _op_execute(self, params: dict[str, Any], bind: dict[str, Any]) -> dict[str, Any]:
        sql = params["sql"]
        eng = self._engine(params)
        with eng.begin() as conn:
            result = conn.execute(text(sql), bind)
            rc = result.rowcount if result.rowcount is not None else -1
            if result.returns_rows:
                keys = list(result.keys())
                preview = [dict(r._mapping) for r in result.fetchmany(50)]
                return {
                    "success": True,
                    "rowcount": rc,
                    "returns_rows": True,
                    "columns": keys,
                    "preview_rows": preview,
                }
            return {"success": True, "rowcount": rc, "returns_rows": False}
