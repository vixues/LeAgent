"""Tabular schema inference.

:class:`TabularSchema` captures the shape of a result so downstream
tools, UI widgets, and the LLM can reason about it without scanning the
raw rows. Inference is done once when a tool finishes so it costs
O(columns) not O(rows × columns).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = ["TabularSchema", "ColumnInfo", "infer_schema"]


@dataclass
class ColumnInfo:
    """Per-column metadata."""

    name: str
    dtype: str
    nullable: bool = True
    null_count: int = 0
    unique_count: int | None = None
    sample_values: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TabularSchema:
    """Summary of a tabular result."""

    columns: list[ColumnInfo] = field(default_factory=list)
    row_count: int = 0

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    @property
    def column_count(self) -> int:
        return len(self.columns)

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": [c.to_dict() for c in self.columns],
        }


def infer_schema(
    source: Any,
    *,
    sample_size: int = 3,
    unique_threshold: int = 50,
) -> TabularSchema:
    """Infer a :class:`TabularSchema` from records or a DataFrame.

    ``source`` may be a pandas DataFrame or a list of row dicts. Only
    the top ``sample_size`` distinct values per column are retained in
    ``sample_values`` to keep the schema payload small.
    """
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover - pandas is a declared dep
        pd = None  # type: ignore[assignment]

    if pd is not None and hasattr(source, "dtypes") and hasattr(source, "columns"):
        return _schema_from_dataframe(source, pd, sample_size=sample_size,
                                       unique_threshold=unique_threshold)

    if isinstance(source, list):
        return _schema_from_records(source, sample_size=sample_size,
                                    unique_threshold=unique_threshold)

    return TabularSchema()


def _schema_from_dataframe(
    df: Any, pd: Any, *, sample_size: int, unique_threshold: int,
) -> TabularSchema:
    columns: list[ColumnInfo] = []
    row_count = int(len(df))
    for name in df.columns:
        series = df[name]
        null_count = int(series.isna().sum()) if row_count else 0
        dtype = str(series.dtype)
        unique_count: int | None
        try:
            uniques = series.dropna().unique()
            unique_count = int(len(uniques))
        except Exception:  # noqa: BLE001
            uniques = []
            unique_count = None
        if unique_count is not None and unique_count > unique_threshold:
            sample: list[Any] = []
        else:
            sample = [_py(v) for v in list(uniques)[:sample_size]]
        columns.append(ColumnInfo(
            name=str(name),
            dtype=dtype,
            nullable=null_count > 0,
            null_count=null_count,
            unique_count=unique_count,
            sample_values=sample,
        ))
    return TabularSchema(columns=columns, row_count=row_count)


def _schema_from_records(
    records: list[dict[str, Any]], *, sample_size: int, unique_threshold: int,
) -> TabularSchema:
    row_count = len(records)
    if row_count == 0:
        return TabularSchema()

    seen: dict[str, dict[str, Any]] = {}
    for row in records:
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            info = seen.setdefault(key, {"nulls": 0, "types": set(), "samples": []})
            if value is None:
                info["nulls"] += 1
                continue
            info["types"].add(type(value).__name__)
            if len(info["samples"]) < unique_threshold and value not in info["samples"]:
                info["samples"].append(value)

    columns: list[ColumnInfo] = []
    for name, info in seen.items():
        types = sorted(info["types"])
        dtype = types[0] if len(types) == 1 else "mixed"
        columns.append(ColumnInfo(
            name=name,
            dtype=dtype,
            nullable=info["nulls"] > 0,
            null_count=info["nulls"],
            unique_count=len(info["samples"]) if info["samples"] else 0,
            sample_values=[_py(v) for v in info["samples"][:sample_size]],
        ))
    return TabularSchema(columns=columns, row_count=row_count)


def _py(value: Any) -> Any:
    """JSON-safe coercion for sample values."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # noqa: BLE001
            return str(value)
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return None
