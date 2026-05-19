"""Data Transform Tool - Transform and reshape DataFrame data.

Provides operations for column renaming, type casting, value mapping, and derived columns.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools._data import build_result, extend_input_schema, resolve_input
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class DataTransformTool(SyncTool):
    """Transform and reshape DataFrame data.

    Features:
    - Column renaming
    - Type casting with format options
    - Value mapping and replacement
    - Derived columns from expressions
    - Column reordering and selection
    - String transformations (upper, lower, title case)
    """

    name = "data_transform"
    description = (
        "Transform tabular data with operations including column renaming, "
        "type casting, value mapping, derived columns, and string transformations."
    )
    category = ToolCategory.DATA
    version = "1.0.0"
    timeout_sec = 300
    aliases = ["transform", "reshape", "data_reshape"]
    search_hint = "transform rename cast map derive column type conversion string"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("source_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        properties: dict[str, Any] = {
                "transformations": {
                    "type": "array",
                    "description": "List of transformation operations to apply in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "rename",
                                    "cast",
                                    "map_values",
                                    "derive",
                                    "select",
                                    "drop",
                                    "reorder",
                                    "string_transform",
                                    "split",
                                    "combine",
                                    "extract",
                                ],
                                "description": "Type of transformation.",
                            },
                            "columns": {
                                "type": "object",
                                "description": "For rename: mapping of old names to new names.",
                                "additionalProperties": {"type": "string"},
                            },
                            "column": {
                                "type": "string",
                                "description": "Target column for single-column operations.",
                            },
                            "target_type": {
                                "type": "string",
                                "enum": ["int", "float", "str", "bool", "datetime", "date"],
                                "description": "For cast: target data type.",
                            },
                            "datetime_format": {
                                "type": "string",
                                "description": "For cast to datetime: strptime format string.",
                            },
                            "mapping": {
                                "type": "object",
                                "description": "For map_values: value replacement mapping.",
                            },
                            "default": {
                                "description": "For map_values: default value for unmapped values.",
                            },
                            "expression": {
                                "type": "string",
                                "description": "For derive: Python expression using column names.",
                            },
                            "new_column": {
                                "type": "string",
                                "description": "For derive/split/combine: name of the new column.",
                            },
                            "select_columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "For select/reorder: list of columns.",
                            },
                            "drop_columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "For drop: columns to remove.",
                            },
                            "transform_type": {
                                "type": "string",
                                "enum": ["upper", "lower", "title", "strip", "capitalize"],
                                "description": "For string_transform: transformation type.",
                            },
                            "delimiter": {
                                "type": "string",
                                "description": "For split: delimiter to split on.",
                            },
                            "split_index": {
                                "type": "integer",
                                "description": "For split: which part to keep (0-indexed).",
                            },
                            "combine_columns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "For combine: columns to combine.",
                            },
                            "combine_separator": {
                                "type": "string",
                                "description": "For combine: separator between values.",
                                "default": " ",
                            },
                            "pattern": {
                                "type": "string",
                                "description": "For extract: regex pattern with capture group.",
                            },
                        },
                        "required": ["type"],
                    },
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
            "required": ["transformations"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Transforming data"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute data transformations.

        Args:
            params: Tool parameters including data and transformations.
            context: Execution context.

        Returns:
            Dictionary containing transformed data and operation summary.

        Raises:
            ValueError: If transformation parameters are invalid.
            RuntimeError: If pandas operations fail.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise RuntimeError("pandas is not installed. Install with: pip install pandas") from e

        data = resolve_input(params, context, required=False)
        transformations = params["transformations"]
        output_format = params.get("output_format", "records")

        if not data:
            return build_result(
                [],
                context,
                op_name=self.name,
                output_format=output_format,
                params=params,
                extra={
                    "columns_before": [],
                    "columns_after": [],
                    "transformations_applied": [],
                },
            )

        df = pd.DataFrame(data)
        columns_before = list(df.columns)
        transformations_applied: list[dict[str, Any]] = []

        logger.info("Starting data transformation", rows=len(df), columns=len(columns_before))

        for transform in transformations:
            t_type = transform["type"]

            try:
                if t_type == "rename":
                    columns_map = transform.get("columns", {})
                    df = df.rename(columns=columns_map)
                    transformations_applied.append({
                        "type": "rename",
                        "renamed": columns_map,
                    })

                elif t_type == "cast":
                    column = transform.get("column")
                    target_type = transform.get("target_type")
                    datetime_format = transform.get("datetime_format")

                    if column not in df.columns:
                        raise ValueError(f"Column '{column}' not found")

                    original_type = str(df[column].dtype)

                    if target_type == "int":
                        df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
                    elif target_type == "float":
                        df[column] = pd.to_numeric(df[column], errors="coerce")
                    elif target_type == "str":
                        df[column] = df[column].astype(str).replace("nan", None)
                    elif target_type == "bool":
                        df[column] = df[column].astype(bool)
                    elif target_type == "datetime":
                        if datetime_format:
                            df[column] = pd.to_datetime(df[column], format=datetime_format, errors="coerce")
                        else:
                            df[column] = pd.to_datetime(df[column], errors="coerce")
                    elif target_type == "date":
                        df[column] = pd.to_datetime(df[column], errors="coerce").dt.date

                    transformations_applied.append({
                        "type": "cast",
                        "column": column,
                        "from_type": original_type,
                        "to_type": target_type,
                    })

                elif t_type == "map_values":
                    column = transform.get("column")
                    mapping = transform.get("mapping", {})
                    default = transform.get("default")

                    if column not in df.columns:
                        raise ValueError(f"Column '{column}' not found")

                    if default is not None:
                        df[column] = df[column].map(mapping).fillna(default)
                    else:
                        df[column] = df[column].replace(mapping)

                    transformations_applied.append({
                        "type": "map_values",
                        "column": column,
                        "mappings_count": len(mapping),
                    })

                elif t_type == "derive":
                    expression = transform.get("expression")
                    new_column = transform.get("new_column")

                    if not expression or not new_column:
                        raise ValueError("derive requires 'expression' and 'new_column'")

                    allowed_names = set(df.columns)
                    safe_funcs = {
                        "abs": abs,
                        "round": round,
                        "min": min,
                        "max": max,
                        "len": len,
                        "str": str,
                        "int": int,
                        "float": float,
                        "bool": bool,
                    }

                    local_vars = {col: df[col] for col in df.columns}
                    local_vars.update(safe_funcs)

                    try:
                        df[new_column] = eval(expression, {"__builtins__": {}}, local_vars)
                    except Exception as e:
                        raise ValueError(f"Invalid expression '{expression}': {e}") from e

                    transformations_applied.append({
                        "type": "derive",
                        "new_column": new_column,
                        "expression": expression,
                    })

                elif t_type == "select":
                    select_columns = transform.get("select_columns", [])
                    missing = set(select_columns) - set(df.columns)
                    if missing:
                        raise ValueError(f"Columns not found: {missing}")
                    df = df[select_columns]
                    transformations_applied.append({
                        "type": "select",
                        "columns": select_columns,
                    })

                elif t_type == "drop":
                    drop_columns = transform.get("drop_columns", [])
                    existing = [c for c in drop_columns if c in df.columns]
                    df = df.drop(columns=existing)
                    transformations_applied.append({
                        "type": "drop",
                        "dropped": existing,
                    })

                elif t_type == "reorder":
                    select_columns = transform.get("select_columns", [])
                    remaining = [c for c in df.columns if c not in select_columns]
                    new_order = [c for c in select_columns if c in df.columns] + remaining
                    df = df[new_order]
                    transformations_applied.append({
                        "type": "reorder",
                        "new_order": new_order,
                    })

                elif t_type == "string_transform":
                    column = transform.get("column")
                    transform_type = transform.get("transform_type")

                    if column not in df.columns:
                        raise ValueError(f"Column '{column}' not found")

                    if transform_type == "upper":
                        df[column] = df[column].astype(str).str.upper()
                    elif transform_type == "lower":
                        df[column] = df[column].astype(str).str.lower()
                    elif transform_type == "title":
                        df[column] = df[column].astype(str).str.title()
                    elif transform_type == "strip":
                        df[column] = df[column].astype(str).str.strip()
                    elif transform_type == "capitalize":
                        df[column] = df[column].astype(str).str.capitalize()

                    transformations_applied.append({
                        "type": "string_transform",
                        "column": column,
                        "transform_type": transform_type,
                    })

                elif t_type == "split":
                    column = transform.get("column")
                    delimiter = transform.get("delimiter", " ")
                    split_index = transform.get("split_index", 0)
                    new_column = transform.get("new_column")

                    if column not in df.columns:
                        raise ValueError(f"Column '{column}' not found")

                    target_col = new_column or column
                    df[target_col] = (
                        df[column]
                        .astype(str)
                        .str.split(delimiter)
                        .apply(lambda x: x[split_index] if len(x) > split_index else None)
                    )

                    transformations_applied.append({
                        "type": "split",
                        "source_column": column,
                        "target_column": target_col,
                        "delimiter": delimiter,
                        "split_index": split_index,
                    })

                elif t_type == "combine":
                    combine_columns = transform.get("combine_columns", [])
                    new_column = transform.get("new_column")
                    separator = transform.get("combine_separator", " ")

                    if not new_column:
                        raise ValueError("combine requires 'new_column'")

                    missing = set(combine_columns) - set(df.columns)
                    if missing:
                        raise ValueError(f"Columns not found: {missing}")

                    df[new_column] = df[combine_columns].astype(str).agg(separator.join, axis=1)

                    transformations_applied.append({
                        "type": "combine",
                        "source_columns": combine_columns,
                        "new_column": new_column,
                        "separator": separator,
                    })

                elif t_type == "extract":
                    column = transform.get("column")
                    pattern = transform.get("pattern")
                    new_column = transform.get("new_column")

                    if column not in df.columns:
                        raise ValueError(f"Column '{column}' not found")
                    if not pattern:
                        raise ValueError("extract requires 'pattern'")

                    target_col = new_column or column
                    df[target_col] = df[column].astype(str).str.extract(pattern, expand=False)

                    transformations_applied.append({
                        "type": "extract",
                        "source_column": column,
                        "target_column": target_col,
                        "pattern": pattern,
                    })

            except Exception as e:
                logger.error("Transformation failed", type=t_type, error=str(e))
                raise ValueError(f"Transformation '{t_type}' failed: {e}") from e

        for col in df.columns:
            if hasattr(df[col].dtype, "name") and "datetime" in df[col].dtype.name:
                df[col] = df[col].apply(lambda x: x.isoformat() if pd.notna(x) else None)

        output_records = df.to_dict(orient="records")
        logger.info(
            "Data transformation complete",
            transformations=len(transformations_applied),
            columns_after=len(df.columns),
        )
        return build_result(
            output_records,
            context,
            op_name=self.name,
            output_format=output_format,
            params=params,
            extra={
                "columns_before": columns_before,
                "columns_after": list(df.columns),
                "transformations_applied": transformations_applied,
            },
        )
