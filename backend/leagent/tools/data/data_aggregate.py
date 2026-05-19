"""Data Aggregate Tool - Aggregate and summarize DataFrame data.

Provides operations for grouping, aggregation functions, and pivot tables.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools._data import build_result, extend_input_schema, resolve_input
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class DataAggregateTool(SyncTool):
    """Aggregate and summarize DataFrame data.

    Features:
    - Group by single or multiple columns
    - Multiple aggregation functions (sum, avg, count, min, max, etc.)
    - Pivot tables with values and aggregation
    - Rolling window aggregations
    - Custom aggregation expressions
    """

    name = "data_aggregate"
    description = (
        "Aggregate and summarize tabular data with group by operations, "
        "aggregation functions (sum, avg, count, min, max), and pivot tables."
    )
    category = ToolCategory.DATA
    version = "1.0.0"
    timeout_sec = 300
    aliases = ["aggregate", "groupby", "summarize"]
    search_hint = "group by aggregate sum average count pivot table statistics"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("source_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        properties: dict[str, Any] = {
                "operation": {
                    "type": "string",
                    "enum": ["groupby", "pivot", "describe", "value_counts", "rolling"],
                    "description": "Type of aggregation operation.",
                    "default": "groupby",
                },
                "group_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Columns to group by.",
                },
                "aggregations": {
                    "type": "object",
                    "description": "Aggregation specifications per column.",
                    "additionalProperties": {
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["sum", "mean", "avg", "count", "min", "max", "std", "var", "median", "first", "last", "nunique"],
                            },
                            {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": ["sum", "mean", "avg", "count", "min", "max", "std", "var", "median", "first", "last", "nunique"],
                                },
                            },
                        ],
                    },
                },
                "pivot_index": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For pivot: columns to use as index.",
                },
                "pivot_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For pivot: columns to pivot into column headers.",
                },
                "pivot_values": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "For pivot: columns to aggregate.",
                },
                "pivot_aggfunc": {
                    "type": "string",
                    "enum": ["sum", "mean", "count", "min", "max", "first", "last"],
                    "description": "For pivot: aggregation function.",
                    "default": "mean",
                },
                "fill_value": {
                    "description": "Value to fill missing cells in pivot.",
                },
                "column": {
                    "type": "string",
                    "description": "For value_counts: column to count.",
                },
                "normalize": {
                    "type": "boolean",
                    "description": "For value_counts: return proportions instead of counts.",
                    "default": False,
                },
                "top_n": {
                    "type": "integer",
                    "description": "For value_counts: return only top N values.",
                },
                "window_size": {
                    "type": "integer",
                    "description": "For rolling: window size.",
                },
                "window_column": {
                    "type": "string",
                    "description": "For rolling: column to apply rolling window to.",
                },
                "window_func": {
                    "type": "string",
                    "enum": ["sum", "mean", "min", "max", "std", "var"],
                    "description": "For rolling: aggregation function.",
                    "default": "mean",
                },
                "sort_by": {
                    "type": "string",
                    "description": "Column to sort results by.",
                },
                "sort_ascending": {
                    "type": "boolean",
                    "description": "Sort in ascending order.",
                    "default": True,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["records", "dict"],
                    "description": "Output format.",
                    "default": "records",
                },
        }
        extend_input_schema(properties)
        return {
            "type": "object",
            "properties": properties,
            "required": ["operation"],
            "additionalProperties": False,
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute aggregation operation.

        Args:
            params: Tool parameters including data and aggregation options.
            context: Execution context.

        Returns:
            Dictionary containing aggregated data and operation summary.

        Raises:
            ValueError: If aggregation parameters are invalid.
            RuntimeError: If pandas operations fail.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise RuntimeError("pandas is not installed. Install with: pip install pandas") from e

        data = resolve_input(params, context, required=False)
        operation = params.get("operation", "groupby")
        output_format = params.get("output_format", "records")

        if not data:
            return build_result(
                [],
                context,
                op_name=self.name,
                output_format=output_format,
                params=params,
                extra={
                    "operation": operation,
                    "input_rows": 0,
                    "output_rows": 0,
                },
            )

        df = pd.DataFrame(data)
        input_rows = len(df)

        logger.info("Starting aggregation", operation=operation, rows=input_rows)

        if operation == "groupby":
            result_df = self._execute_groupby(df, params, pd)
        elif operation == "pivot":
            result_df = self._execute_pivot(df, params, pd)
        elif operation == "describe":
            result_df = self._execute_describe(df, params, pd)
        elif operation == "value_counts":
            result_df = self._execute_value_counts(df, params, pd)
        elif operation == "rolling":
            result_df = self._execute_rolling(df, params, pd)
        else:
            raise ValueError(f"Unknown operation: {operation}")

        sort_by = params.get("sort_by")
        if sort_by and sort_by in result_df.columns:
            ascending = params.get("sort_ascending", True)
            result_df = result_df.sort_values(by=sort_by, ascending=ascending)

        output_records = result_df.to_dict(orient="records")
        logger.info(
            "Aggregation complete",
            operation=operation,
            input_rows=input_rows,
            output_rows=len(result_df),
        )
        return build_result(
            output_records,
            context,
            op_name=self.name,
            output_format=output_format,
            params=params,
            extra={
                "operation": operation,
                "input_rows": input_rows,
                "output_rows": len(result_df),
                "columns": list(result_df.columns),
            },
        )

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "groupby")
        return f"Aggregating data ({op})"

    def _execute_groupby(self, df: Any, params: dict[str, Any], pd: Any) -> Any:
        """Execute group by aggregation."""
        group_by = params.get("group_by", [])
        aggregations = params.get("aggregations", {})

        if not group_by:
            raise ValueError("groupby operation requires 'group_by' columns")

        missing = set(group_by) - set(df.columns)
        if missing:
            raise ValueError(f"Group by columns not found: {missing}")

        agg_map: dict[str, Any] = {}
        for col, agg_funcs in aggregations.items():
            if col not in df.columns:
                logger.warning("Aggregation column not found", column=col)
                continue

            if isinstance(agg_funcs, str):
                agg_funcs = [agg_funcs]

            normalized_funcs = []
            for func in agg_funcs:
                if func == "avg":
                    func = "mean"
                normalized_funcs.append(func)

            agg_map[col] = normalized_funcs

        if not agg_map:
            numeric_cols = df.select_dtypes(include=["number"]).columns
            agg_cols = [c for c in numeric_cols if c not in group_by]
            agg_map = {col: ["sum", "mean", "count"] for col in agg_cols[:5]}

        if not agg_map:
            agg_map = {group_by[0]: ["count"]}

        grouped = df.groupby(group_by, as_index=False).agg(agg_map)

        if isinstance(grouped.columns, pd.MultiIndex):
            grouped.columns = [
                f"{col[0]}_{col[1]}" if col[1] else col[0]
                for col in grouped.columns
            ]

        return grouped

    def _execute_pivot(self, df: Any, params: dict[str, Any], pd: Any) -> Any:
        """Execute pivot table operation."""
        pivot_index = params.get("pivot_index", [])
        pivot_columns = params.get("pivot_columns", [])
        pivot_values = params.get("pivot_values", [])
        pivot_aggfunc = params.get("pivot_aggfunc", "mean")
        fill_value = params.get("fill_value")

        if not pivot_index or not pivot_columns:
            raise ValueError("pivot operation requires 'pivot_index' and 'pivot_columns'")

        missing_idx = set(pivot_index) - set(df.columns)
        if missing_idx:
            raise ValueError(f"Pivot index columns not found: {missing_idx}")

        missing_cols = set(pivot_columns) - set(df.columns)
        if missing_cols:
            raise ValueError(f"Pivot columns not found: {missing_cols}")

        if pivot_aggfunc == "avg":
            pivot_aggfunc = "mean"

        pivot_kwargs: dict[str, Any] = {
            "index": pivot_index if len(pivot_index) > 1 else pivot_index[0],
            "columns": pivot_columns if len(pivot_columns) > 1 else pivot_columns[0],
            "aggfunc": pivot_aggfunc,
        }

        if pivot_values:
            missing_vals = set(pivot_values) - set(df.columns)
            if missing_vals:
                raise ValueError(f"Pivot value columns not found: {missing_vals}")
            pivot_kwargs["values"] = pivot_values if len(pivot_values) > 1 else pivot_values[0]

        if fill_value is not None:
            pivot_kwargs["fill_value"] = fill_value

        pivot_df = pd.pivot_table(df, **pivot_kwargs)
        pivot_df = pivot_df.reset_index()

        if isinstance(pivot_df.columns, pd.MultiIndex):
            pivot_df.columns = [
                "_".join(str(c) for c in col).strip("_")
                for col in pivot_df.columns
            ]

        return pivot_df

    def _execute_describe(self, df: Any, params: dict[str, Any], pd: Any) -> Any:
        """Execute statistical description."""
        desc = df.describe(include="all").T.reset_index()
        desc = desc.rename(columns={"index": "column"})
        return desc

    def _execute_value_counts(self, df: Any, params: dict[str, Any], pd: Any) -> Any:
        """Execute value counts operation."""
        column = params.get("column")
        normalize = params.get("normalize", False)
        top_n = params.get("top_n")

        if not column:
            raise ValueError("value_counts operation requires 'column'")

        if column not in df.columns:
            raise ValueError(f"Column '{column}' not found")

        counts = df[column].value_counts(normalize=normalize)

        if top_n:
            counts = counts.head(top_n)

        result_df = counts.reset_index()
        result_df.columns = [column, "proportion" if normalize else "count"]

        return result_df

    def _execute_rolling(self, df: Any, params: dict[str, Any], pd: Any) -> Any:
        """Execute rolling window aggregation."""
        window_size = params.get("window_size")
        window_column = params.get("window_column")
        window_func = params.get("window_func", "mean")

        if not window_size or not window_column:
            raise ValueError("rolling operation requires 'window_size' and 'window_column'")

        if window_column not in df.columns:
            raise ValueError(f"Column '{window_column}' not found")

        result_df = df.copy()
        new_col_name = f"{window_column}_rolling_{window_func}_{window_size}"

        rolling = df[window_column].rolling(window=window_size, min_periods=1)

        if window_func == "sum":
            result_df[new_col_name] = rolling.sum()
        elif window_func == "mean":
            result_df[new_col_name] = rolling.mean()
        elif window_func == "min":
            result_df[new_col_name] = rolling.min()
        elif window_func == "max":
            result_df[new_col_name] = rolling.max()
        elif window_func == "std":
            result_df[new_col_name] = rolling.std()
        elif window_func == "var":
            result_df[new_col_name] = rolling.var()

        return result_df
