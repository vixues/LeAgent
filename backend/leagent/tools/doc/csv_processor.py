"""CSV/TSV processing tool using the standard library csv and json modules."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

_READ_ROW_CAP = 10_000
_UNIQUE_CAP = 50_000
_SNIFF_BYTES = 65536


def _detect_encoding(path: Path) -> str:
    raw = path.read_bytes()[:_SNIFF_BYTES]
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "latin-1"


def _sniff_delimiter(sample_text: str) -> str:
    if not sample_text.strip():
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _delimiter_for_path(path: Path, encoding: str, delimiter: str | None) -> str:
    if delimiter is not None:
        return delimiter
    with open(path, "r", encoding=encoding, newline="") as f:
        sample = f.read(_SNIFF_BYTES)
    return _sniff_delimiter(sample)


def _parse_row_to_dict(row: list[str], headers: list[str]) -> dict[str, Any]:
    return {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}


def _normalize_cell(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _try_float(s: str) -> float | None:
    if s == "":
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _try_date(s: str) -> bool:
    if not s or len(s) < 4:
        return False
    t = s.strip()
    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ):
        try:
            datetime.strptime(t, fmt)
            return True
        except ValueError:
            continue
    try:
        datetime.fromisoformat(t.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


class CSVProcessorTool(SyncTool):
    name = "csv_processor"
    description = (
        "Read, query, write, analyze statistics, and convert CSV/TSV files "
        "using delimiter sniffing and UTF-8/Latin-1 encoding handling."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 120
    aliases = ["csv", "tsv", "csv_reader"]
    search_hint = "CSV TSV read query write analyze statistics delimiter tabular"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ()
    output_path_params = ("file_path", "output_path")

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "query", "write", "stats", "convert"],
                    "description": "Operation to perform.",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path to CSV/TSV: existing file for read/query/stats/convert; "
                        "destination for write (may be a new file under the session uploads directory). "
                        "Use write only when the user explicitly asked to save or export a file."
                    ),
                },
                "delimiter": {
                    "type": "string",
                    "description": "Field delimiter; if omitted, auto-detected via csv.Sniffer.",
                },
                "encoding": {
                    "type": "string",
                    "description": "Text encoding (default: utf-8 with latin-1 fallback when omitted).",
                },
                "max_rows": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Max data rows to return for read (capped at 10000).",
                },
                "has_header": {
                    "type": "boolean",
                    "description": "First row is header (read/query/stats/convert). Default true.",
                    "default": True,
                },
                "filter_column": {
                    "type": "string",
                    "description": "Column name to filter (query).",
                },
                "filter_value": {
                    "type": "string",
                    "description": "Cell value to match as string (query).",
                },
                "sort_column": {
                    "type": "string",
                    "description": "Column name to sort by (query).",
                },
                "sort_order": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "description": "Sort order when sort_column is set.",
                    "default": "asc",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Max rows after filter/sort (query).",
                },
                "data": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Array of row objects (write).",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output file path (convert).",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["json"],
                    "description": "Output format for convert.",
                    "default": "json",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {"properties": {"operation": {"const": "read"}}},
                    "then": {"required": ["file_path"]},
                },
                {
                    "if": {"properties": {"operation": {"const": "query"}}},
                    "then": {"required": ["file_path", "filter_column", "filter_value"]},
                },
                {
                    "if": {"properties": {"operation": {"const": "write"}}},
                    "then": {"required": ["file_path", "data"]},
                },
                {
                    "if": {"properties": {"operation": {"const": "stats"}}},
                    "then": {"required": ["file_path"]},
                },
                {
                    "if": {"properties": {"operation": {"const": "convert"}}},
                    "then": {"required": ["file_path", "output_path", "output_format"]},
                },
            ],
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "read")
        return f"Processing CSV ({op})"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        op = params["operation"]
        if op == "read":
            return self._op_read(params)
        if op == "query":
            return self._op_query(params)
        if op == "write":
            return self._op_write(params)
        if op == "stats":
            return self._op_stats(params)
        if op == "convert":
            return self._op_convert(params)
        raise ValueError(f"Unknown operation: {op}")

    def _op_read(self, params: dict[str, Any]) -> dict[str, Any]:
        path = Path(params["file_path"])
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        encoding = params.get("encoding") or _detect_encoding(path)
        delimiter = _delimiter_for_path(path, encoding, params.get("delimiter"))
        has_header = params.get("has_header", True)
        max_rows = params.get("max_rows")
        cap = _READ_ROW_CAP
        if max_rows is not None:
            cap = min(int(max_rows), _READ_ROW_CAP)

        headers: list[str] = []
        rows: list[dict[str, Any]] = []
        total_data_rows = 0

        with open(path, "r", encoding=encoding, newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)
            if has_header:
                first = next(reader, None)
                if first is None:
                    return {
                        "headers": [],
                        "rows": [],
                        "row_count": 0,
                        "column_count": 0,
                        "encoding": encoding,
                        "delimiter": delimiter,
                    }
                headers = [str(h) if h is not None else f"column_{i}" for i, h in enumerate(first)]
                for row in reader:
                    total_data_rows += 1
                    if len(rows) < cap:
                        rows.append(_parse_row_to_dict(row, headers))
            else:
                peek = next(reader, None)
                if peek is None:
                    return {
                        "headers": [],
                        "rows": [],
                        "row_count": 0,
                        "column_count": 0,
                        "encoding": encoding,
                        "delimiter": delimiter,
                    }
                headers = [f"column_{i}" for i in range(len(peek))]
                total_data_rows += 1
                if len(rows) < cap:
                    rows.append(_parse_row_to_dict(peek, headers))
                for row in reader:
                    total_data_rows += 1
                    if len(rows) < cap:
                        rows.append(_parse_row_to_dict(row, headers))

        return {
            "headers": headers,
            "rows": rows,
            "row_count": total_data_rows,
            "column_count": len(headers),
            "encoding": encoding,
            "delimiter": delimiter,
        }

    def _op_query(self, params: dict[str, Any]) -> dict[str, Any]:
        path = Path(params["file_path"])
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        encoding = params.get("encoding") or _detect_encoding(path)
        delimiter = _delimiter_for_path(path, encoding, params.get("delimiter"))
        has_header = params.get("has_header", True)
        filter_column = params["filter_column"]
        filter_value = params["filter_value"]
        sort_column = params.get("sort_column")
        sort_order = params.get("sort_order", "asc")
        limit = params.get("limit")
        max_out = min(int(limit), _READ_ROW_CAP) if limit is not None else _READ_ROW_CAP

        matched: list[dict[str, Any]] = []

        with open(path, "r", encoding=encoding, newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)
            if has_header:
                header_row = next(reader, None)
                if header_row is None:
                    return {"rows": [], "row_count": 0, "encoding": encoding, "delimiter": delimiter}
                headers = [str(h) if h is not None else f"column_{i}" for i, h in enumerate(header_row)]
            else:
                first = next(reader, None)
                if first is None:
                    return {"rows": [], "row_count": 0, "encoding": encoding, "delimiter": delimiter}
                headers = [f"column_{i}" for i in range(len(first))]
                d0 = _parse_row_to_dict(first, headers)
                if filter_column in d0 and _normalize_cell(d0.get(filter_column)) == filter_value:
                    matched.append(d0)

            if filter_column not in headers:
                raise ValueError(f"Unknown column: {filter_column!r}")

            for row in reader:
                rec = _parse_row_to_dict(row, headers)
                if _normalize_cell(rec.get(filter_column)) == filter_value:
                    matched.append(rec)
                    if sort_column is None and len(matched) >= max_out:
                        break

        if sort_column is not None and sort_column not in headers:
            raise ValueError(f"Unknown sort column: {sort_column!r}")

            def sort_key(r: dict[str, Any]) -> tuple[int, str]:
                v = r.get(sort_column)
                s = _normalize_cell(v)
                n = _try_float(s)
                if n is not None:
                    return (0, f"{n:020f}")
                return (1, s)

            reverse = sort_order == "desc"
            matched.sort(key=sort_key, reverse=reverse)
            matched = matched[:max_out]
        else:
            matched = matched[:max_out]

        return {
            "rows": matched,
            "row_count": len(matched),
            "encoding": encoding,
            "delimiter": delimiter,
        }

    def _op_write(self, params: dict[str, Any]) -> dict[str, Any]:
        path = Path(params["file_path"])
        data = params["data"]
        if not isinstance(data, list) or not data:
            raise ValueError("data must be a non-empty array of objects")

        delimiter = params.get("delimiter", ",")
        encoding = params.get("encoding") or "utf-8"

        keys: list[str] = []
        seen: set[str] = set()
        for obj in data:
            if not isinstance(obj, dict):
                raise ValueError("each data item must be an object")
            for k in obj:
                if k not in seen:
                    seen.add(k)
                    keys.append(k)
        if not keys:
            raise ValueError("data rows must contain at least one key")

        with open(path, "w", encoding=encoding, newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys, delimiter=delimiter, extrasaction="ignore")
            w.writeheader()
            for obj in data:
                w.writerow({k: obj.get(k) for k in keys})

        return {"success": True, "row_count": len(data), "path": str(path)}

    def _op_stats(self, params: dict[str, Any]) -> dict[str, Any]:
        path = Path(params["file_path"])
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        encoding = params.get("encoding") or _detect_encoding(path)
        delimiter = _delimiter_for_path(path, encoding, params.get("delimiter"))
        has_header = params.get("has_header", True)

        headers: list[str] = []
        null_counts: Counter[str] = Counter()
        unique_sets: dict[str, set[str]] = {}
        unique_truncated: dict[str, bool] = {}
        str_samples: dict[str, list[str]] = {}
        numeric_hits: dict[str, int] = {}
        date_hits: dict[str, int] = {}
        num_min: dict[str, float] = {}
        num_max: dict[str, float] = {}
        total_rows = 0

        def bump_unique(col: str, val: str) -> None:
            st = unique_sets.setdefault(col, set())
            if len(st) >= _UNIQUE_CAP:
                unique_truncated[col] = True
                return
            st.add(val)

        def process_row(row: list[str]) -> None:
            nonlocal total_rows
            total_rows += 1
            for i, col in enumerate(headers):
                cell = row[i] if i < len(row) else None
                s = _normalize_cell(cell)
                if s == "":
                    null_counts[col] += 1
                    continue
                bump_unique(col, s)
                samples = str_samples.setdefault(col, [])
                if len(samples) < 5 and s not in samples:
                    samples.append(s)
                n = _try_float(s)
                if n is not None:
                    numeric_hits[col] = numeric_hits.get(col, 0) + 1
                    prev_min = num_min.get(col)
                    prev_max = num_max.get(col)
                    num_min[col] = n if prev_min is None else min(prev_min, n)
                    num_max[col] = n if prev_max is None else max(prev_max, n)
                if _try_date(s):
                    date_hits[col] = date_hits.get(col, 0) + 1

        with open(path, "r", encoding=encoding, newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)
            if has_header:
                hr = next(reader, None)
                if hr is None:
                    return {
                        "columns": {},
                        "encoding": encoding,
                        "delimiter": delimiter,
                        "total_rows": 0,
                    }
                headers = [str(h) if h is not None else f"column_{i}" for i, h in enumerate(hr)]
            else:
                first = next(reader, None)
                if first is None:
                    return {
                        "columns": {},
                        "encoding": encoding,
                        "delimiter": delimiter,
                        "total_rows": 0,
                    }
                headers = [f"column_{i}" for i in range(len(first))]
                process_row(first)

            for row in reader:
                process_row(row)

        out_cols: dict[str, Any] = {}
        for col in headers:
            null_c = null_counts.get(col, 0)
            non_null = total_rows - null_c
            ulen = len(unique_sets.get(col, set()))
            if unique_truncated.get(col):
                ulen = _UNIQUE_CAP
            nf = numeric_hits.get(col, 0)
            df = date_hits.get(col, 0)
            if non_null == 0:
                inferred = "string"
            elif nf == non_null:
                inferred = "numeric"
            elif non_null > 0 and df >= non_null * 0.8:
                inferred = "date"
            else:
                inferred = "string"

            col_info: dict[str, Any] = {
                "inferred_type": inferred,
                "null_count": null_c,
                "unique_count": ulen,
                "unique_count_truncated": unique_truncated.get(col, False),
                "sample_values": str_samples.get(col, [])[:5],
            }
            if inferred == "numeric" and col in num_min and col in num_max:
                col_info["min"] = num_min[col]
                col_info["max"] = num_max[col]
            else:
                col_info["min"] = None
                col_info["max"] = None
            out_cols[col] = col_info

        return {
            "columns": out_cols,
            "encoding": encoding,
            "delimiter": delimiter,
            "total_rows": total_rows,
        }

    def _op_convert(self, params: dict[str, Any]) -> dict[str, Any]:
        path = Path(params["file_path"])
        out_path = Path(params["output_path"])
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        fmt = params.get("output_format", "json")
        if fmt != "json":
            raise ValueError("Only output_format 'json' is supported")

        encoding = params.get("encoding") or _detect_encoding(path)
        delimiter = _delimiter_for_path(path, encoding, params.get("delimiter"))
        has_header = params.get("has_header", True)

        row_count = 0
        with (
            open(path, "r", encoding=encoding, newline="") as inf,
            open(out_path, "w", encoding="utf-8", newline="\n") as outf,
        ):
            reader = csv.reader(inf, delimiter=delimiter)
            outf.write("[\n")
            first_elem = True
            headers: list[str] = []

            if has_header:
                hr = next(reader, None)
                if hr is None:
                    outf.write("]\n")
                    return {"success": True, "path": str(out_path), "row_count": 0}
                headers = [str(h) if h is not None else f"column_{i}" for i, h in enumerate(hr)]
            else:
                fr = next(reader, None)
                if fr is None:
                    outf.write("]\n")
                    return {"success": True, "path": str(out_path), "row_count": 0}
                headers = [f"column_{i}" for i in range(len(fr))]
                outf.write(json.dumps(_parse_row_to_dict(fr, headers), ensure_ascii=False, indent=2))
                first_elem = False
                row_count = 1

            for row in reader:
                rec = _parse_row_to_dict(row, headers)
                if first_elem:
                    outf.write(json.dumps(rec, ensure_ascii=False, indent=2))
                    first_elem = False
                else:
                    outf.write(",\n")
                    outf.write(json.dumps(rec, ensure_ascii=False, indent=2))
                row_count += 1
            outf.write("\n]\n")

        return {"success": True, "path": str(out_path), "row_count": row_count}

