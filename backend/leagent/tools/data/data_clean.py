"""Data Clean Tool - Clean and preprocess DataFrame data.

Provides operations for removing duplicates, handling missing values,
normalizing data types, and trimming whitespace.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools._data import build_result, extend_input_schema, resolve_input
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class DataCleanTool(SyncTool):
    """Clean and preprocess DataFrame data.

    Features:
    - Remove duplicate rows based on specified columns
    - Fill missing values with specified strategies
    - Drop rows/columns with missing values
    - Trim whitespace from string columns
    - Normalize data types (dates, numbers, strings)
    """

    name = "data_clean"
    description = (
        "Clean and preprocess tabular data by removing duplicates, "
        "handling missing values, trimming whitespace, and normalizing data types."
    )
    category = ToolCategory.DATA
    version = "1.0.0"
    timeout_sec = 300
    aliases = ["clean", "preprocess", "data_preprocess"]
    search_hint = "clean deduplicate missing values normalize trim whitespace preprocess"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("source_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        properties: dict[str, Any] = {
            "operations": {
                    "type": "array",
                    "description": "List of cleaning operations to apply in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "remove_duplicates",
                                    "fill_missing",
                                    "drop_missing",
                                    "trim_whitespace",
                                    "normalize_types",
                                ],
                                "description": "Type of cleaning operation.",
                            },
                            "columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Columns to apply operation to. If empty, applies to all columns.",
                            },
                            "keep": {
                                "type": "string",
                                "enum": ["first", "last", "none"],
                                "description": "For remove_duplicates: which duplicate to keep.",
                                "default": "first",
                            },
                            "fill_value": {
                                "description": "For fill_missing: value to fill with, or strategy name.",
                            },
                            "fill_strategy": {
                                "type": "string",
                                "enum": ["value", "mean", "median", "mode", "ffill", "bfill"],
                                "description": "For fill_missing: strategy to use.",
                                "default": "value",
                            },
                            "axis": {
                                "type": "string",
                                "enum": ["rows", "columns"],
                                "description": "For drop_missing: drop rows or columns.",
                                "default": "rows",
                            },
                            "how": {
                                "type": "string",
                                "enum": ["any", "all"],
                                "description": "For drop_missing: drop if 'any' or 'all' values are missing.",
                                "default": "any",
                            },
                            "thresh": {
                                "type": "integer",
                                "description": "For drop_missing: minimum non-null values required.",
                            },
                            "type_map": {
                                "type": "object",
                                "description": "For normalize_types: column to type mapping.",
                                "additionalProperties": {
                                    "type": "string",
                                    "enum": ["int", "float", "str", "bool", "datetime"],
                                },
                            },
                        },
                        "required": ["type"],
                    },
                },
                "output_format": {
                    "type": "string",
                    "enum": ["records", "dict"],
                    "description": "Output format: 'records' (list of dicts) or 'dict' (column-oriented).",
                    "default": "records",
                },
        }
        extend_input_schema(properties)
        return {
            "type": "object",
            "properties": properties,
            "required": ["operations"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Cleaning data"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute data cleaning operations.

        Args:
            params: Tool parameters including data and operations.
            context: Execution context.

        Returns:
            Dictionary containing cleaned data and operation summary.

        Raises:
            ValueError: If operations are invalid or data format is incorrect.
            RuntimeError: If pandas operations fail.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise RuntimeError("pandas is not installed. Install with: pip install pandas") from e

        data = resolve_input(params, context, required=False)
        operations = params["operations"]
        output_format = params.get("output_format", "records")

        if not data:
            return build_result(
                [],
                context,
                op_name=self.name,
                output_format=output_format,
                params=params,
                extra={
                    "rows_before": 0,
                    "rows_after": 0,
                    "columns": [],
                    "operations_applied": [],
                },
            )

        df = pd.DataFrame(data)
        rows_before = len(df)
        columns_before = list(df.columns)
        operations_applied: list[dict[str, Any]] = []

        logger.info("Starting data cleaning", rows=rows_before, columns=len(columns_before))

        for op in operations:
            op_type = op["type"]
            columns = op.get("columns", [])
            target_cols = columns if columns else list(df.columns)

            try:
                if op_type == "remove_duplicates":
                    rows_pre = len(df)
                    subset = columns if columns else None
                    keep = op.get("keep", "first")
                    keep_param = keep if keep != "none" else False
                    df = df.drop_duplicates(subset=subset, keep=keep_param)
                    removed = rows_pre - len(df)
                    operations_applied.append({
                        "type": op_type,
                        "columns": subset or "all",
                        "duplicates_removed": removed,
                    })
                    logger.debug("Removed duplicates", count=removed)

                elif op_type == "fill_missing":
                    strategy = op.get("fill_strategy", "value")
                    fill_value = op.get("fill_value")
                    filled_count = 0

                    for col in target_cols:
                        if col not in df.columns:
                            continue
                        missing_before = df[col].isna().sum()
                        if missing_before == 0:
                            continue

                        if strategy == "value":
                            df[col] = df[col].fillna(fill_value)
                        elif strategy == "mean":
                            df[col] = df[col].fillna(df[col].mean())
                        elif strategy == "median":
                            df[col] = df[col].fillna(df[col].median())
                        elif strategy == "mode":
                            mode_val = df[col].mode()
                            if len(mode_val) > 0:
                                df[col] = df[col].fillna(mode_val.iloc[0])
                        elif strategy == "ffill":
                            df[col] = df[col].ffill()
                        elif strategy == "bfill":
                            df[col] = df[col].bfill()

                        filled_count += missing_before - df[col].isna().sum()

                    operations_applied.append({
                        "type": op_type,
                        "strategy": strategy,
                        "columns": target_cols,
                        "values_filled": int(filled_count),
                    })
                    logger.debug("Filled missing values", count=filled_count, strategy=strategy)

                elif op_type == "drop_missing":
                    rows_pre = len(df)
                    cols_pre = len(df.columns)
                    axis = 0 if op.get("axis", "rows") == "rows" else 1
                    how = op.get("how", "any")
                    thresh = op.get("thresh")
                    subset = columns if columns else None

                    if axis == 0:
                        df = df.dropna(axis=axis, how=how, thresh=thresh, subset=subset)
                        dropped = rows_pre - len(df)
                        operations_applied.append({
                            "type": op_type,
                            "axis": "rows",
                            "rows_dropped": dropped,
                        })
                    else:
                        df = df.dropna(axis=axis, how=how, thresh=thresh)
                        dropped = cols_pre - len(df.columns)
                        operations_applied.append({
                            "type": op_type,
                            "axis": "columns",
                            "columns_dropped": dropped,
                        })
                    logger.debug("Dropped missing", axis=op.get("axis", "rows"), count=dropped)

                elif op_type == "trim_whitespace":
                    trimmed_cols = []
                    for col in target_cols:
                        if col not in df.columns:
                            continue
                        if df[col].dtype == "object":
                            df[col] = df[col].apply(
                                lambda x: x.strip() if isinstance(x, str) else x
                            )
                            trimmed_cols.append(col)
                    operations_applied.append({
                        "type": op_type,
                        "columns_trimmed": trimmed_cols,
                    })
                    logger.debug("Trimmed whitespace", columns=trimmed_cols)

                elif op_type == "normalize_types":
                    type_map = op.get("type_map", {})
                    converted = {}

                    for col, dtype in type_map.items():
                        if col not in df.columns:
                            continue
                        try:
                            if dtype == "int":
                                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                            elif dtype == "float":
                                df[col] = pd.to_numeric(df[col], errors="coerce")
                            elif dtype == "str":
                                df[col] = df[col].astype(str)
                            elif dtype == "bool":
                                df[col] = df[col].astype(bool)
                            elif dtype == "datetime":
                                df[col] = pd.to_datetime(df[col], errors="coerce")
                            converted[col] = dtype
                        except Exception as e:
                            logger.warning("Type conversion failed", column=col, dtype=dtype, error=str(e))

                    operations_applied.append({
                        "type": op_type,
                        "conversions": converted,
                    })
                    logger.debug("Normalized types", conversions=converted)

            except Exception as e:
                logger.error("Operation failed", operation=op_type, error=str(e))
                raise ValueError(f"Operation '{op_type}' failed: {e}") from e

        for col in df.columns:
            if hasattr(df[col], "dt"):
                df[col] = df[col].apply(lambda x: x.isoformat() if pd.notna(x) else None)

        output_records = df.to_dict(orient="records")
        logger.info(
            "Data cleaning complete",
            rows_before=rows_before,
            rows_after=len(df),
            operations=len(operations_applied),
        )
        return build_result(
            output_records,
            context,
            op_name=self.name,
            output_format=output_format,
            params=params,
            extra={
                "rows_before": rows_before,
                "rows_after": len(df),
                "columns_before": columns_before,
                "columns_after": list(df.columns),
                "operations_applied": operations_applied,
            },
        )
