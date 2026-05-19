"""SQL Query Tool - Execute SQL queries on DataFrames.

Provides SQL interface for querying tabular data with safe query validation.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from leagent.tools._data import build_result, load_records
from leagent.tools._data.tool_helpers import INPUT_SCHEMA_FRAGMENT
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


FORBIDDEN_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bCALL\b",
    r"--",
    r"/\*",
    r"\*/",
    r";.*\b(DROP|DELETE|TRUNCATE|ALTER|CREATE|INSERT|UPDATE)\b",
]


class SQLQueryTool(SyncTool):
    """Execute SQL queries on DataFrame data.

    Features:
    - Full SQL SELECT support via pandasql/sqldf
    - Safe query validation to prevent harmful operations
    - Multiple table support via named datasets
    - Result formatting options
    - Query explanation and optimization hints
    """

    name = "sql_query"
    description = (
        "Execute SQL queries on tabular data. Supports SELECT queries with "
        "JOINs, WHERE clauses, GROUP BY, ORDER BY, and aggregations."
    )
    category = ToolCategory.DATA
    version = "1.0.0"
    timeout_sec = 300
    aliases = ["sql", "query", "sql_exec"]
    search_hint = "SQL query select join where group order aggregate filter"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("source_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL query to execute. Only SELECT queries are allowed.",
                },
                "tables": {
                    "type": "object",
                    "description": (
                        "Named tables as mapping of table_name to rows. Each value "
                        "may be an inline array of records or an artifact-ref object."
                    ),
                    "additionalProperties": {
                        "oneOf": [
                            {"type": "array", "items": {"type": "object"}},
                            {"type": "object", "properties": {"uri": {"type": "string"}}, "required": ["uri"]},
                        ],
                    },
                },
                "data": {
                    "type": "array",
                    "description": "Single table data (will be available as 'data' table).",
                    "items": {"type": "object"},
                },
                "artifact": INPUT_SCHEMA_FRAGMENT["artifact"],
                "source_path": INPUT_SCHEMA_FRAGMENT["source_path"],
                "max_rows": INPUT_SCHEMA_FRAGMENT["max_rows"],
                "spill_rows": INPUT_SCHEMA_FRAGMENT["spill_rows"],
                "spill_bytes": INPUT_SCHEMA_FRAGMENT["spill_bytes"],
                "force_spill": INPUT_SCHEMA_FRAGMENT["force_spill"],
                "output_format": {
                    "type": "string",
                    "enum": ["records", "dict"],
                    "description": "Output format for results.",
                    "default": "records",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum rows to return (applied if query has no LIMIT).",
                    "default": 1000,
                    "minimum": 1,
                    "maximum": 100000,
                },
                "explain": {
                    "type": "boolean",
                    "description": "Return query explanation instead of executing.",
                    "default": False,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Executing SQL query"

    def _validate_query(self, query: str) -> tuple[bool, str | None]:
        """Validate SQL query for safety.

        Args:
            query: SQL query to validate.

        Returns:
            Tuple of (is_valid, error_message).
        """
        query_upper = query.upper().strip()

        if not query_upper.startswith("SELECT") and not query_upper.startswith("WITH"):
            return False, "Only SELECT queries (including WITH/CTE) are allowed"

        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, query_upper):
                return False, f"Query contains forbidden pattern: {pattern}"

        paren_count = 0
        for char in query:
            if char == "(":
                paren_count += 1
            elif char == ")":
                paren_count -= 1
            if paren_count < 0:
                return False, "Unbalanced parentheses in query"
        if paren_count != 0:
            return False, "Unbalanced parentheses in query"

        return True, None

    def _add_limit_if_missing(self, query: str, limit: int) -> str:
        """Add LIMIT clause if not present in query.

        Args:
            query: SQL query.
            limit: Maximum rows.

        Returns:
            Query with LIMIT clause.
        """
        query_upper = query.upper().strip()

        if "LIMIT" in query_upper:
            return query

        query = query.rstrip().rstrip(";")
        return f"{query} LIMIT {limit}"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute SQL query on provided data.

        Args:
            params: Tool parameters including query and table data.
            context: Execution context.

        Returns:
            Dictionary containing query results and execution info.

        Raises:
            ValueError: If query is invalid or tables are missing.
            RuntimeError: If SQL execution fails.
        """
        try:
            import pandas as pd
            import pandasql
        except ImportError as e:
            if "pandasql" in str(e):
                raise RuntimeError(
                    "pandasql is not installed. Install with: pip install pandasql"
                ) from e
            raise RuntimeError("pandas is not installed. Install with: pip install pandas") from e

        query = params["query"]
        tables = dict(params.get("tables") or {})
        data = params.get("data") or params.get("artifact") or params.get("source_path")
        output_format = params.get("output_format", "records")
        limit = params.get("limit", 1000)
        explain = params.get("explain", False)
        max_rows = params.get("max_rows")

        is_valid, error_msg = self._validate_query(query)
        if not is_valid:
            raise ValueError(f"Invalid query: {error_msg}")

        if data is not None:
            tables["data"] = data

        if not tables:
            raise ValueError("No table data provided. Use 'tables' or 'data'/'artifact'/'source_path'.")

        dataframes: dict[str, Any] = {}
        table_info: dict[str, dict[str, Any]] = {}

        for table_name, table_data in tables.items():
            loaded = load_records(table_data, context, max_rows=max_rows)
            df = pd.DataFrame(loaded) if loaded else pd.DataFrame()
            dataframes[table_name] = df
            table_info[table_name] = {
                "rows": len(df),
                "columns": list(df.columns),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            }

        if explain:
            return {
                "query": query,
                "tables": table_info,
                "explanation": self._explain_query(query, table_info),
            }

        query = self._add_limit_if_missing(query, limit)

        logger.info(
            "Executing SQL query",
            tables=list(tables.keys()),
            query_length=len(query),
        )

        try:
            result_df = pandasql.sqldf(query, dataframes)
        except Exception as e:
            error_msg = str(e)
            if "no such table" in error_msg.lower():
                available = list(dataframes.keys())
                raise ValueError(
                    f"Table not found. Available tables: {available}. "
                    f"Original error: {error_msg}"
                ) from e
            raise RuntimeError(f"SQL execution failed: {error_msg}") from e

        output_records = result_df.to_dict(orient="records")
        logger.info(
            "SQL query complete",
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
                "query": query,
                "tables_used": list(tables.keys()),
            },
        )

    def _explain_query(
        self, query: str, table_info: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Generate query explanation.

        Args:
            query: SQL query.
            table_info: Information about available tables.

        Returns:
            Dictionary with query explanation.
        """
        query_upper = query.upper()

        operations: list[str] = []
        if "SELECT" in query_upper:
            operations.append("SELECT")
        if "FROM" in query_upper:
            operations.append("FROM")
        if "JOIN" in query_upper:
            operations.append("JOIN")
        if "WHERE" in query_upper:
            operations.append("WHERE")
        if "GROUP BY" in query_upper:
            operations.append("GROUP BY")
        if "HAVING" in query_upper:
            operations.append("HAVING")
        if "ORDER BY" in query_upper:
            operations.append("ORDER BY")
        if "LIMIT" in query_upper:
            operations.append("LIMIT")
        if "DISTINCT" in query_upper:
            operations.append("DISTINCT")
        if "UNION" in query_upper:
            operations.append("UNION")

        tables_referenced: list[str] = []
        for table_name in table_info.keys():
            if re.search(rf"\b{table_name}\b", query, re.IGNORECASE):
                tables_referenced.append(table_name)

        aggregations: list[str] = []
        for agg in ["COUNT", "SUM", "AVG", "MIN", "MAX", "GROUP_CONCAT"]:
            if agg in query_upper:
                aggregations.append(agg)

        return {
            "operations": operations,
            "tables_referenced": tables_referenced,
            "aggregations": aggregations,
            "has_subquery": query_upper.count("SELECT") > 1,
            "has_join": "JOIN" in query_upper,
            "has_grouping": "GROUP BY" in query_upper,
            "has_ordering": "ORDER BY" in query_upper,
            "available_tables": table_info,
        }
