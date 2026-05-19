"""Data Validate Tool - Validate DataFrame data against schemas and rules.

Provides comprehensive data validation including schema validation, type checks,
range validation, and required field verification.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from leagent.tools._data import emit_records, extend_input_schema, resolve_input
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class DataValidateTool(SyncTool):
    """Validate DataFrame data against schemas and rules.

    Features:
    - JSON Schema-like validation for DataFrames
    - Data type checks with coercion options
    - Range validation (min/max) for numeric columns
    - Required field checks
    - Regex pattern validation
    - Unique constraint validation
    - Custom validation rules
    """

    name = "data_validate"
    description = (
        "Validate tabular data against schemas and rules including type checks, "
        "range validation, required fields, patterns, and uniqueness constraints."
    )
    category = ToolCategory.DATA
    version = "1.0.0"
    timeout_sec = 180
    aliases = ["validate", "data_check", "schema_validate"]
    search_hint = "validate schema check type range required pattern uniqueness constraint"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000
    path_params = ("source_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        properties: dict[str, Any] = {
                "schema": {
                    "type": "object",
                    "description": "Validation schema defining column rules.",
                    "properties": {
                        "columns": {
                            "type": "object",
                            "description": "Column-level validation rules.",
                            "additionalProperties": {
                                "type": "object",
                                "properties": {
                                    "type": {
                                        "type": "string",
                                        "enum": ["string", "integer", "number", "boolean", "datetime", "any"],
                                        "description": "Expected data type.",
                                    },
                                    "required": {
                                        "type": "boolean",
                                        "description": "Whether the column must have non-null values.",
                                    },
                                    "nullable": {
                                        "type": "boolean",
                                        "description": "Whether null values are allowed.",
                                        "default": True,
                                    },
                                    "min": {
                                        "type": "number",
                                        "description": "Minimum value for numeric columns.",
                                    },
                                    "max": {
                                        "type": "number",
                                        "description": "Maximum value for numeric columns.",
                                    },
                                    "min_length": {
                                        "type": "integer",
                                        "description": "Minimum length for string columns.",
                                    },
                                    "max_length": {
                                        "type": "integer",
                                        "description": "Maximum length for string columns.",
                                    },
                                    "pattern": {
                                        "type": "string",
                                        "description": "Regex pattern for string validation.",
                                    },
                                    "enum": {
                                        "type": "array",
                                        "description": "Allowed values.",
                                    },
                                    "unique": {
                                        "type": "boolean",
                                        "description": "Whether values must be unique.",
                                    },
                                },
                            },
                        },
                        "required_columns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of columns that must exist.",
                        },
                        "unique_together": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "description": "Column combinations that must be unique together.",
                        },
                        "row_count": {
                            "type": "object",
                            "properties": {
                                "min": {"type": "integer"},
                                "max": {"type": "integer"},
                            },
                            "description": "Row count constraints.",
                        },
                    },
                },
                "fail_fast": {
                    "type": "boolean",
                    "description": "Stop validation on first error.",
                    "default": False,
                },
                "return_valid_rows": {
                    "type": "boolean",
                    "description": "Return only valid rows in output.",
                    "default": False,
                },
        }
        extend_input_schema(properties)
        return {
            "type": "object",
            "properties": properties,
            "required": ["schema"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Validating data"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute data validation.

        Args:
            params: Tool parameters including data and validation schema.
            context: Execution context.

        Returns:
            Dictionary containing validation results and error details.

        Raises:
            ValueError: If schema is invalid.
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise RuntimeError("pandas is not installed. Install with: pip install pandas") from e

        data = resolve_input(params, context, required=False)
        schema = params["schema"]
        fail_fast = params.get("fail_fast", False)
        return_valid_rows = params.get("return_valid_rows", False)

        if not data:
            return {
                "valid": True,
                "row_count": 0,
                "errors": [],
                "warnings": [],
                "summary": {"total_rows": 0, "valid_rows": 0, "invalid_rows": 0},
            }

        df = pd.DataFrame(data)
        errors: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        invalid_row_indices: set[int] = set()

        logger.info("Starting data validation", rows=len(df), columns=len(df.columns))

        if "required_columns" in schema:
            missing_cols = set(schema["required_columns"]) - set(df.columns)
            if missing_cols:
                errors.append({
                    "type": "missing_columns",
                    "columns": list(missing_cols),
                    "message": f"Required columns missing: {missing_cols}",
                })
                if fail_fast:
                    return self._build_result(df, errors, warnings, invalid_row_indices, return_valid_rows, context, params)

        if "row_count" in schema:
            row_constraints = schema["row_count"]
            min_rows = row_constraints.get("min")
            max_rows = row_constraints.get("max")

            if min_rows is not None and len(df) < min_rows:
                errors.append({
                    "type": "row_count_violation",
                    "constraint": "min",
                    "expected": min_rows,
                    "actual": len(df),
                    "message": f"Row count {len(df)} is below minimum {min_rows}",
                })

            if max_rows is not None and len(df) > max_rows:
                errors.append({
                    "type": "row_count_violation",
                    "constraint": "max",
                    "expected": max_rows,
                    "actual": len(df),
                    "message": f"Row count {len(df)} exceeds maximum {max_rows}",
                })

        columns_schema = schema.get("columns", {})
        for col_name, rules in columns_schema.items():
            if col_name not in df.columns:
                if rules.get("required", False):
                    errors.append({
                        "type": "missing_required_column",
                        "column": col_name,
                        "message": f"Required column '{col_name}' is missing",
                    })
                continue

            col_errors = self._validate_column(df, col_name, rules, pd)
            for err in col_errors:
                if "row_indices" in err:
                    invalid_row_indices.update(err["row_indices"])
                errors.append(err)

                if fail_fast:
                    return self._build_result(df, errors, warnings, invalid_row_indices, return_valid_rows, context, params)

        if "unique_together" in schema:
            for col_group in schema["unique_together"]:
                valid_cols = [c for c in col_group if c in df.columns]
                if len(valid_cols) != len(col_group):
                    continue

                duplicates = df[df.duplicated(subset=valid_cols, keep=False)]
                if not duplicates.empty:
                    dup_indices = duplicates.index.tolist()
                    invalid_row_indices.update(dup_indices)
                    errors.append({
                        "type": "unique_together_violation",
                        "columns": col_group,
                        "row_indices": dup_indices[:10],
                        "total_violations": len(dup_indices),
                        "message": f"Duplicate values found for column combination {col_group}",
                    })

        return self._build_result(df, errors, warnings, invalid_row_indices, return_valid_rows, context, params)

    def _validate_column(
        self, df: Any, col_name: str, rules: dict[str, Any], pd: Any
    ) -> list[dict[str, Any]]:
        """Validate a single column against its rules."""
        errors: list[dict[str, Any]] = []
        col = df[col_name]

        nullable = rules.get("nullable", True)
        if not nullable:
            null_mask = col.isna()
            if null_mask.any():
                null_indices = df.index[null_mask].tolist()
                errors.append({
                    "type": "null_violation",
                    "column": col_name,
                    "row_indices": null_indices[:10],
                    "total_violations": int(null_mask.sum()),
                    "message": f"Column '{col_name}' contains null values but is not nullable",
                })

        expected_type = rules.get("type")
        if expected_type and expected_type != "any":
            type_errors = self._check_type(df, col_name, expected_type, pd)
            errors.extend(type_errors)

        if "min" in rules or "max" in rules:
            range_errors = self._check_range(df, col_name, rules, pd)
            errors.extend(range_errors)

        if "min_length" in rules or "max_length" in rules:
            length_errors = self._check_length(df, col_name, rules)
            errors.extend(length_errors)

        if "pattern" in rules:
            pattern_errors = self._check_pattern(df, col_name, rules["pattern"])
            errors.extend(pattern_errors)

        if "enum" in rules:
            enum_errors = self._check_enum(df, col_name, rules["enum"])
            errors.extend(enum_errors)

        if rules.get("unique", False):
            duplicates = col[col.duplicated(keep=False) & col.notna()]
            if not duplicates.empty:
                dup_indices = duplicates.index.tolist()
                errors.append({
                    "type": "unique_violation",
                    "column": col_name,
                    "row_indices": dup_indices[:10],
                    "total_violations": len(dup_indices),
                    "message": f"Column '{col_name}' contains duplicate values",
                })

        return errors

    def _check_type(
        self, df: Any, col_name: str, expected_type: str, pd: Any
    ) -> list[dict[str, Any]]:
        """Check column data type."""
        errors: list[dict[str, Any]] = []
        col = df[col_name]
        non_null = col.dropna()

        if non_null.empty:
            return errors

        invalid_indices: list[int] = []

        if expected_type == "string":
            for idx, val in non_null.items():
                if not isinstance(val, str):
                    invalid_indices.append(idx)

        elif expected_type == "integer":
            for idx, val in non_null.items():
                if not isinstance(val, (int, float)):
                    invalid_indices.append(idx)
                elif isinstance(val, float) and not val.is_integer():
                    invalid_indices.append(idx)

        elif expected_type == "number":
            for idx, val in non_null.items():
                if not isinstance(val, (int, float)):
                    try:
                        float(val)
                    except (ValueError, TypeError):
                        invalid_indices.append(idx)

        elif expected_type == "boolean":
            for idx, val in non_null.items():
                if not isinstance(val, bool) and val not in (0, 1, "true", "false", "True", "False"):
                    invalid_indices.append(idx)

        elif expected_type == "datetime":
            for idx, val in non_null.items():
                try:
                    pd.to_datetime(val)
                except Exception:
                    invalid_indices.append(idx)

        if invalid_indices:
            errors.append({
                "type": "type_violation",
                "column": col_name,
                "expected_type": expected_type,
                "row_indices": invalid_indices[:10],
                "total_violations": len(invalid_indices),
                "message": f"Column '{col_name}' contains values not matching type '{expected_type}'",
            })

        return errors

    def _check_range(
        self, df: Any, col_name: str, rules: dict[str, Any], pd: Any
    ) -> list[dict[str, Any]]:
        """Check numeric range constraints."""
        errors: list[dict[str, Any]] = []
        col = df[col_name]

        try:
            numeric_col = pd.to_numeric(col, errors="coerce")
        except Exception:
            return errors

        non_null = numeric_col.dropna()
        if non_null.empty:
            return errors

        if "min" in rules:
            min_val = rules["min"]
            below_min = non_null[non_null < min_val]
            if not below_min.empty:
                errors.append({
                    "type": "range_violation",
                    "column": col_name,
                    "constraint": "min",
                    "limit": min_val,
                    "row_indices": below_min.index.tolist()[:10],
                    "total_violations": len(below_min),
                    "message": f"Column '{col_name}' has {len(below_min)} values below minimum {min_val}",
                })

        if "max" in rules:
            max_val = rules["max"]
            above_max = non_null[non_null > max_val]
            if not above_max.empty:
                errors.append({
                    "type": "range_violation",
                    "column": col_name,
                    "constraint": "max",
                    "limit": max_val,
                    "row_indices": above_max.index.tolist()[:10],
                    "total_violations": len(above_max),
                    "message": f"Column '{col_name}' has {len(above_max)} values above maximum {max_val}",
                })

        return errors

    def _check_length(
        self, df: Any, col_name: str, rules: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Check string length constraints."""
        errors: list[dict[str, Any]] = []
        col = df[col_name]

        str_col = col.dropna().astype(str)
        lengths = str_col.str.len()

        if "min_length" in rules:
            min_len = rules["min_length"]
            too_short = lengths[lengths < min_len]
            if not too_short.empty:
                errors.append({
                    "type": "length_violation",
                    "column": col_name,
                    "constraint": "min_length",
                    "limit": min_len,
                    "row_indices": too_short.index.tolist()[:10],
                    "total_violations": len(too_short),
                    "message": f"Column '{col_name}' has {len(too_short)} values shorter than {min_len}",
                })

        if "max_length" in rules:
            max_len = rules["max_length"]
            too_long = lengths[lengths > max_len]
            if not too_long.empty:
                errors.append({
                    "type": "length_violation",
                    "column": col_name,
                    "constraint": "max_length",
                    "limit": max_len,
                    "row_indices": too_long.index.tolist()[:10],
                    "total_violations": len(too_long),
                    "message": f"Column '{col_name}' has {len(too_long)} values longer than {max_len}",
                })

        return errors

    def _check_pattern(
        self, df: Any, col_name: str, pattern: str
    ) -> list[dict[str, Any]]:
        """Check regex pattern constraint."""
        errors: list[dict[str, Any]] = []
        col = df[col_name]

        try:
            regex = re.compile(pattern)
        except re.error as e:
            errors.append({
                "type": "invalid_pattern",
                "column": col_name,
                "pattern": pattern,
                "message": f"Invalid regex pattern: {e}",
            })
            return errors

        str_col = col.dropna().astype(str)
        non_matching: list[int] = []

        for idx, val in str_col.items():
            if not regex.match(val):
                non_matching.append(idx)

        if non_matching:
            errors.append({
                "type": "pattern_violation",
                "column": col_name,
                "pattern": pattern,
                "row_indices": non_matching[:10],
                "total_violations": len(non_matching),
                "message": f"Column '{col_name}' has {len(non_matching)} values not matching pattern",
            })

        return errors

    def _check_enum(
        self, df: Any, col_name: str, allowed_values: list[Any]
    ) -> list[dict[str, Any]]:
        """Check enum constraint."""
        errors: list[dict[str, Any]] = []
        col = df[col_name]

        non_null = col.dropna()
        invalid_mask = ~non_null.isin(allowed_values)
        invalid_values = non_null[invalid_mask]

        if not invalid_values.empty:
            errors.append({
                "type": "enum_violation",
                "column": col_name,
                "allowed_values": allowed_values,
                "invalid_values": list(invalid_values.unique())[:10],
                "row_indices": invalid_values.index.tolist()[:10],
                "total_violations": len(invalid_values),
                "message": f"Column '{col_name}' has {len(invalid_values)} values not in allowed set",
            })

        return errors

    def _build_result(
        self,
        df: Any,
        errors: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        invalid_row_indices: set[int],
        return_valid_rows: bool,
        context: ToolContext | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build validation result."""
        valid_rows = len(df) - len(invalid_row_indices)
        is_valid = len(errors) == 0

        result: dict[str, Any] = {
            "valid": is_valid,
            "row_count": len(df),
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "total_rows": len(df),
                "valid_rows": valid_rows,
                "invalid_rows": len(invalid_row_indices),
                "error_count": len(errors),
                "warning_count": len(warnings),
            },
        }

        if return_valid_rows and invalid_row_indices:
            valid_mask = ~df.index.isin(invalid_row_indices)
            valid_df = df[valid_mask]
            valid_records = valid_df.to_dict(orient="records")
            envelope = emit_records(
                valid_records,
                context,
                op_name=f"{self.name}_valid",
                spill_rows=int((params or {}).get("spill_rows", 50_000)),
                spill_bytes=int((params or {}).get("spill_bytes", 5 * 1024 * 1024)),
                force_spill=bool((params or {}).get("force_spill", False)),
            )
            payload = envelope.to_dict()
            if payload.get("artifact") is not None:
                result["valid_artifact"] = payload["artifact"]
                result["valid_preview"] = payload.get("preview", [])
            else:
                result["valid_data"] = payload.get("data", valid_records)
            result["valid_schema"] = payload.get("schema")

        logger.info(
            "Validation complete",
            valid=is_valid,
            total_errors=len(errors),
            invalid_rows=len(invalid_row_indices),
        )

        return result
