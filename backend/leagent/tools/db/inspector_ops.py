"""Schema introspection helpers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import Engine  # noqa: TC002


def list_tables(engine: Engine) -> list[str]:
    insp = inspect(engine)
    return list(insp.get_table_names())


def describe_table(engine: Engine, table_name: str) -> dict[str, Any]:
    insp = inspect(engine)
    if table_name not in insp.get_table_names():
        raise ValueError(f"Table not found: {table_name}")
    cols = insp.get_columns(table_name)
    pks = insp.get_pk_constraint(table_name).get("constrained_columns") or []
    fks = insp.get_foreign_keys(table_name)
    return {
        "table": table_name,
        "columns": cols,
        "primary_key": pks,
        "foreign_keys": fks,
    }
