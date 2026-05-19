"""Data Merge Tool - Merge and join multiple DataFrames.

Provides operations for merging DataFrames with various join types and key matching.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools._data import build_result, load_records
from leagent.tools._data.tool_helpers import INPUT_SCHEMA_FRAGMENT
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class DataMergeTool(SyncTool):
    """Merge and join multiple DataFrames.

    Features:
    - Inner, outer, left, right join types
    - Single or multiple key column matching
    - Concatenation of DataFrames
    - Suffix handling for overlapping columns
    - Indicator column for merge diagnostics
    """

    name = "data_merge"
    description = (
        "Merge and join multiple datasets with support for inner, outer, left, "
        "and right joins, as well as concatenation operations."
    )
    category = ToolCategory.DATA
    version = "1.0.0"
    timeout_sec = 300
    aliases = ["merge", "join", "concat", "data_join"]
    search_hint = "merge join concatenate combine datasets inner outer left right"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("source_path",)

    def _enforce_path_sandbox(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> None:
        super()._enforce_path_sandbox(params, context)

        from leagent.tools._sandbox.paths import PathSandbox

        request_id = context.extra.get("request_id", context.session_id or "")
        for key in ("left_artifact", "right_artifact"):
            ref = params.get(key)
            if isinstance(ref, dict):
                uri = ref.get("uri", "")
                if uri and not uri.startswith("minio://"):
                    raw = uri.removeprefix("file://")
                    PathSandbox.resolve_safe(
                        raw, context=context, tool_name=self.name,
                        request_id=str(request_id),
                    )
        for ds in params.get("datasets") or []:
            if isinstance(ds, dict):
                uri = ds.get("uri", "")
                if uri and not uri.startswith("minio://"):
                    raw = uri.removeprefix("file://")
                    PathSandbox.resolve_safe(
                        raw, context=context, tool_name=self.name,
                        request_id=str(request_id),
                    )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "left_data": {
                    "type": "array",
                    "description": "Left dataset as list of records.",
                    "items": {"type": "object"},
                },
                "right_data": {
                    "type": "array",
                    "description": "Right dataset as list of records.",
                    "items": {"type": "object"},
                },
                "datasets": {
                    "type": "array",
                    "description": (
                        "Multiple datasets for concatenation (alternative to left/right). "
                        "Each entry may be either an inline array of records or an "
                        "artifact-ref object."
                    ),
                    "items": {
                        "oneOf": [
                            {"type": "array", "items": {"type": "object"}},
                            {"type": "object", "properties": {"uri": {"type": "string"}}, "required": ["uri"]},
                        ],
                    },
                },
                "left_artifact": INPUT_SCHEMA_FRAGMENT["artifact"],
                "right_artifact": INPUT_SCHEMA_FRAGMENT["artifact"],
                "max_rows": INPUT_SCHEMA_FRAGMENT["max_rows"],
                "spill_rows": INPUT_SCHEMA_FRAGMENT["spill_rows"],
                "spill_bytes": INPUT_SCHEMA_FRAGMENT["spill_bytes"],
                "force_spill": INPUT_SCHEMA_FRAGMENT["force_spill"],
                "operation": {
                    "type": "string",
                    "enum": ["merge", "concat"],
                    "description": "Operation type: 'merge' for joins, 'concat' for stacking.",
                    "default": "merge",
                },
                "how": {
                    "type": "string",
                    "enum": ["inner", "outer", "left", "right", "cross"],
                    "description": "Join type for merge operations.",
                    "default": "inner",
                },
                "on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column(s) to join on (must exist in both datasets).",
                },
                "left_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column(s) from left dataset to join on.",
                },
                "right_on": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column(s) from right dataset to join on.",
                },
                "suffixes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Suffixes for overlapping column names.",
                    "default": ["_left", "_right"],
                    "minItems": 2,
                    "maxItems": 2,
                },
                "indicator": {
                    "type": "boolean",
                    "description": "Add column indicating merge source (_merge).",
                    "default": False,
                },
                "validate": {
                    "type": "string",
                    "enum": ["one_to_one", "one_to_many", "many_to_one", "many_to_many"],
                    "description": "Validate merge relationship.",
                },
                "concat_axis": {
                    "type": "string",
                    "enum": ["rows", "columns"],
                    "description": "For concat: stack rows or columns.",
                    "default": "rows",
                },
                "ignore_index": {
                    "type": "boolean",
                    "description": "For concat: reset index after concatenation.",
                    "default": True,
                },
                "output_format": {
                    "type": "string",
                    "enum": ["records", "dict"],
                    "description": "Output format.",
                    "default": "records",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "merge")
        return f"Merging data ({op})"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute merge or concatenation operation.

        Args:
            params: Tool parameters including datasets and merge options.
            context: Execution context.

        Returns:
            Dictionary containing merged data and operation summary.

        Raises:
            ValueError: If parameters are invalid or merge fails.
            RuntimeError: If pandas operations fail.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise RuntimeError("pandas is not installed. Install with: pip install pandas") from e

        operation = params.get("operation", "merge")
        output_format = params.get("output_format", "records")

        if operation == "concat":
            return self._execute_concat(params, pd, output_format, context)
        else:
            return self._execute_merge(params, pd, output_format, context)

    def _execute_merge(
        self, params: dict[str, Any], pd: Any, output_format: str,
        context: ToolContext,
    ) -> dict[str, Any]:
        """Execute a merge/join operation."""
        left_data = load_records(
            params.get("left_data") or params.get("left_artifact"),
            context, max_rows=params.get("max_rows"),
        )
        right_data = load_records(
            params.get("right_data") or params.get("right_artifact"),
            context, max_rows=params.get("max_rows"),
        )

        if not left_data or not right_data:
            raise ValueError("Both left_data and right_data are required for merge operations")

        left_df = pd.DataFrame(left_data)
        right_df = pd.DataFrame(right_data)

        how = params.get("how", "inner")
        on = params.get("on")
        left_on = params.get("left_on")
        right_on = params.get("right_on")
        suffixes = tuple(params.get("suffixes", ["_left", "_right"]))
        indicator = params.get("indicator", False)
        validate = params.get("validate")

        logger.info(
            "Starting merge operation",
            how=how,
            left_rows=len(left_df),
            right_rows=len(right_df),
        )

        if on:
            for col in on:
                if col not in left_df.columns:
                    raise ValueError(f"Column '{col}' not found in left dataset")
                if col not in right_df.columns:
                    raise ValueError(f"Column '{col}' not found in right dataset")

        if left_on:
            for col in left_on:
                if col not in left_df.columns:
                    raise ValueError(f"Column '{col}' not found in left dataset")

        if right_on:
            for col in right_on:
                if col not in right_df.columns:
                    raise ValueError(f"Column '{col}' not found in right dataset")

        merge_kwargs: dict[str, Any] = {
            "how": how,
            "suffixes": suffixes,
            "indicator": indicator,
        }

        if on:
            merge_kwargs["on"] = on
        elif left_on and right_on:
            merge_kwargs["left_on"] = left_on
            merge_kwargs["right_on"] = right_on
        elif how != "cross":
            common_cols = set(left_df.columns) & set(right_df.columns)
            if not common_cols:
                raise ValueError(
                    "No common columns found. Specify 'on', 'left_on'/'right_on', or use 'cross' join."
                )
            merge_kwargs["on"] = list(common_cols)

        if validate:
            merge_kwargs["validate"] = validate

        try:
            result_df = pd.merge(left_df, right_df, **merge_kwargs)
        except pd.errors.MergeError as e:
            raise ValueError(f"Merge validation failed: {e}") from e

        merge_stats: dict[str, Any] = {
            "left_rows": len(left_df),
            "right_rows": len(right_df),
            "result_rows": len(result_df),
            "join_type": how,
        }

        if indicator:
            merge_counts = result_df["_merge"].value_counts().to_dict()
            merge_stats["merge_indicator"] = {
                "left_only": merge_counts.get("left_only", 0),
                "right_only": merge_counts.get("right_only", 0),
                "both": merge_counts.get("both", 0),
            }

        output_records = result_df.to_dict(orient="records")
        logger.info(
            "Merge complete",
            result_rows=len(result_df),
            result_columns=len(result_df.columns),
        )
        return build_result(
            output_records,
            context,
            op_name=self.name,
            output_format=output_format,
            params=params,
            extra={
                "columns": list(result_df.columns),
                "merge_stats": merge_stats,
            },
        )

    def _execute_concat(
        self, params: dict[str, Any], pd: Any, output_format: str,
        context: ToolContext,
    ) -> dict[str, Any]:
        """Execute a concatenation operation."""
        datasets = params.get("datasets", [])

        if not datasets:
            left_data = params.get("left_data") or params.get("left_artifact")
            right_data = params.get("right_data") or params.get("right_artifact")
            if left_data and right_data:
                datasets = [left_data, right_data]

        if len(datasets) < 2:
            raise ValueError("At least 2 datasets are required for concatenation")

        max_rows = params.get("max_rows")
        dfs = [pd.DataFrame(load_records(ds, context, max_rows=max_rows)) for ds in datasets]
        concat_axis = 0 if params.get("concat_axis", "rows") == "rows" else 1
        ignore_index = params.get("ignore_index", True)

        logger.info(
            "Starting concatenation",
            num_datasets=len(dfs),
            axis="rows" if concat_axis == 0 else "columns",
        )

        total_rows_before = sum(len(df) for df in dfs)

        result_df = pd.concat(dfs, axis=concat_axis, ignore_index=ignore_index)

        output_records = result_df.to_dict(orient="records")
        logger.info(
            "Concatenation complete",
            result_rows=len(result_df),
            result_columns=len(result_df.columns),
        )
        return build_result(
            output_records,
            context,
            op_name=self.name,
            output_format=output_format,
            params=params,
            extra={
                "columns": list(result_df.columns),
                "concat_stats": {
                    "datasets_count": len(dfs),
                    "total_rows_before": total_rows_before,
                    "result_rows": len(result_df),
                    "axis": "rows" if concat_axis == 0 else "columns",
                },
            },
        )
