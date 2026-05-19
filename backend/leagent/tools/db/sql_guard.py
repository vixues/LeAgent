"""Single-statement SQL classification for the database tool."""

from __future__ import annotations

import re
from typing import Any, Literal

SqlMode = Literal["query", "execute"]


_WS = re.compile(r"\s+")
_COMMENT_LINE = re.compile(r"^\s*--")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_sql_comments(sql: str) -> str:
    """Remove line and block comments (conservative, not a full lexer)."""
    out: list[str] = []
    for line in sql.splitlines():
        if _COMMENT_LINE.match(line):
            continue
        out.append(line)
    joined = "\n".join(out)
    return _BLOCK_COMMENT.sub(" ", joined)


def normalize_statement(sql: str) -> str:
    s = sql.strip()
    if not s:
        return ""
    s = _strip_sql_comments(s)
    s = s.strip().rstrip(";")
    return s.strip()


def assert_single_statement(sql: str) -> None:
    """Reject multiple statements (semicolon-separated)."""
    body = normalize_statement(sql)
    if not body:
        raise ValueError("SQL is empty")
    core = body.rstrip(";").strip()
    if ";" in core:
        raise ValueError("Multiple SQL statements are not allowed; run one statement at a time")


_PRAGMA_READ_ALLOWLIST = frozenset({
    "table_info",
    "index_list",
    "index_info",
    "foreign_key_list",
    "database_list",
    "collation_list",
    "compile_options",
    "schema_version",
    "user_version",
    "encoding",
    "application_id",
    "freelist_count",
    "page_count",
    "table_xinfo",
    "integrity_check",
    "quick_check",
})


def _pragma_subcommand(upper_sql: str) -> str | None:
    if not upper_sql.startswith("PRAGMA"):
        return None
    rest = upper_sql[len("PRAGMA") :].lstrip()
    m = re.match(r"^([A-Za-z_]+)", rest)
    return m.group(1).lower() if m else None


def classify_for_mode(sql: str, *, dialect: str) -> SqlMode:
    """Return whether SQL is allowed under read-only *query* mode."""
    assert_single_statement(sql)
    u = normalize_statement(sql).upper()
    if u.startswith("SELECT") or u.startswith("WITH") or u.startswith("EXPLAIN"):
        return "query"
    if u.startswith("SHOW") and dialect == "mysql":
        return "query"
    if u.startswith("PRAGMA") and dialect == "sqlite":
        sub = _pragma_subcommand(u)
        if sub and sub in _PRAGMA_READ_ALLOWLIST:
            return "query"
    return "execute"


def assert_mode(sql: str, *, dialect: str, expected: SqlMode) -> None:
    got = classify_for_mode(sql, dialect=dialect)
    if expected == "query" and got != "query":
        raise ValueError(
            "This operation only allows read-only SQL "
            "(SELECT / WITH / EXPLAIN, or allow-listed SQLite PRAGMA)."
        )


_DESTRUCTIVE_RE = re.compile(
    r"\b(DROP|TRUNCATE)\b|\bALTER\s+TABLE\b.*\bDROP\b",
    re.IGNORECASE | re.DOTALL,
)


def requires_destructive_confirm(sql: str) -> bool:
    u = normalize_statement(sql).upper()
    return bool(_DESTRUCTIVE_RE.search(u))


def coerce_params(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, list):
        return {f"p{i}": v for i, v in enumerate(raw)}
    raise TypeError("params must be an object or array")
