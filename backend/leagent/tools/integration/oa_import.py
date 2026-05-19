"""OA Import Tool - Import data from OA systems.

Provides data import capabilities from OA systems with field mapping,
validation, and batch processing support.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class ImportSourceType(str, Enum):
    """Import source types."""

    API = "api"
    FILE = "file"
    DATABASE = "database"


class ImportDataType(str, Enum):
    """Data types available for import."""

    WORKFLOW_INSTANCES = "workflow_instances"
    FORMS = "forms"
    USERS = "users"
    DEPARTMENTS = "departments"
    ROLES = "roles"
    APPROVALS = "approvals"
    ATTACHMENTS = "attachments"
    CUSTOM = "custom"


class OAImportTool(BaseTool):
    """Tool for importing data from OA systems.

    Features:
    - Import from multiple sources (API, file, database)
    - Field mapping and transformation
    - Data validation
    - Batch import with pagination
    - Progress tracking
    - Error handling and partial success reporting

    Example:
        >>> tool = OAImportTool()
        >>> result = await tool.run({
        ...     "base_url": "https://oa.company.com/api",
        ...     "data_type": "workflow_instances",
        ...     "field_mapping": {"title": "form_title", "creator": "applicant"},
        ...     "filters": {"status": "completed"},
        ...     "batch_size": 100
        ... }, context)
    """

    name = "oa_import"
    description = (
        "Import data from OA systems with field mapping and batch processing. "
        "Supports importing workflow instances, forms, users, and more."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 300
    max_retries = 2
    aliases = ["oa_data_import", "import_oa"]
    search_hint = "OA import data field mapping batch workflow forms users"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "block"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Importing OA data"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "Base URL of the OA system API",
                },
                "source_type": {
                    "type": "string",
                    "enum": [s.value for s in ImportSourceType],
                    "default": "api",
                    "description": "Import source type",
                },
                "data_type": {
                    "type": "string",
                    "enum": [d.value for d in ImportDataType],
                    "description": "Type of data to import",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Custom API endpoint (overrides data_type endpoint)",
                },
                "auth_type": {
                    "type": "string",
                    "enum": ["none", "basic", "bearer", "api_key"],
                    "default": "none",
                    "description": "Authentication type",
                },
                "auth_credentials": {
                    "type": "object",
                    "description": "Authentication credentials",
                    "properties": {
                        "username": {"type": "string"},
                        "password": {"type": "string"},
                        "token": {"type": "string"},
                        "api_key": {"type": "string"},
                        "api_key_header": {"type": "string"},
                    },
                },
                "field_mapping": {
                    "type": "object",
                    "description": "Field mapping from source to target format. Keys are target fields, values are source fields.",
                    "additionalProperties": {"type": "string"},
                },
                "field_transforms": {
                    "type": "object",
                    "description": "Field transformations. Keys are field names, values are transform rules.",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "string",
                                    "integer",
                                    "float",
                                    "boolean",
                                    "date",
                                    "datetime",
                                    "json",
                                    "list",
                                ],
                            },
                            "format": {"type": "string"},
                            "default": {},
                            "mapping": {"type": "object"},
                        },
                    },
                },
                "filters": {
                    "type": "object",
                    "description": "Filter conditions for data query",
                },
                "date_range": {
                    "type": "object",
                    "description": "Date range filter",
                    "properties": {
                        "field": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                    },
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Number of records per batch",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "max_records": {
                    "type": "integer",
                    "description": "Maximum total records to import",
                    "default": 10000,
                    "minimum": 1,
                },
                "pagination_config": {
                    "type": "object",
                    "description": "Pagination configuration",
                    "properties": {
                        "page_param": {"type": "string", "default": "page"},
                        "size_param": {"type": "string", "default": "page_size"},
                        "offset_mode": {"type": "boolean", "default": False},
                        "offset_param": {"type": "string", "default": "offset"},
                        "total_path": {"type": "string", "default": "total"},
                        "data_path": {"type": "string", "default": "data"},
                    },
                },
                "validation_rules": {
                    "type": "object",
                    "description": "Validation rules for imported data",
                    "properties": {
                        "required_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "unique_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "field_patterns": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                    },
                },
                "headers": {
                    "type": "object",
                    "description": "Additional HTTP headers",
                },
            },
            "required": ["base_url", "data_type"],
        }

    def _get_endpoint_for_type(self, data_type: str) -> str:
        """Get default endpoint for data type."""
        endpoints = {
            ImportDataType.WORKFLOW_INSTANCES.value: "/api/workflow/instances",
            ImportDataType.FORMS.value: "/api/forms",
            ImportDataType.USERS.value: "/api/users",
            ImportDataType.DEPARTMENTS.value: "/api/departments",
            ImportDataType.ROLES.value: "/api/roles",
            ImportDataType.APPROVALS.value: "/api/approvals",
            ImportDataType.ATTACHMENTS.value: "/api/attachments",
            ImportDataType.CUSTOM.value: "",
        }
        return endpoints.get(data_type, "")

    def _build_auth_headers(
        self, auth_type: str, credentials: dict[str, Any]
    ) -> dict[str, str]:
        """Build authentication headers."""
        headers: dict[str, str] = {}

        if auth_type == "basic":
            import base64

            username = credentials.get("username", "")
            password = credentials.get("password", "")
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"

        elif auth_type == "bearer":
            token = credentials.get("token", "")
            headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "api_key":
            api_key = credentials.get("api_key", "")
            header_name = credentials.get("api_key_header", "X-API-Key")
            headers[header_name] = api_key

        return headers

    def _extract_nested_value(self, data: dict[str, Any], path: str) -> Any:
        """Extract value from nested dictionary using dot notation."""
        value = data
        for key in path.split("."):
            if isinstance(value, dict):
                value = value.get(key)
            elif isinstance(value, list) and key.isdigit():
                idx = int(key)
                value = value[idx] if idx < len(value) else None
            else:
                return None
        return value

    def _apply_field_mapping(
        self,
        record: dict[str, Any],
        mapping: dict[str, str],
        transforms: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply field mapping and transformations to a record."""
        result: dict[str, Any] = {}

        for target_field, source_field in mapping.items():
            value = self._extract_nested_value(record, source_field)

            if target_field in transforms:
                transform = transforms[target_field]
                value = self._transform_value(value, transform)

            result[target_field] = value

        for key, value in record.items():
            mapped_target = None
            for t_field, s_field in mapping.items():
                if s_field.split(".")[0] == key:
                    mapped_target = t_field
                    break
            if mapped_target is None and key not in result:
                result[key] = value

        return result

    def _transform_value(self, value: Any, transform: dict[str, Any]) -> Any:
        """Apply transformation to a value."""
        transform_type = transform.get("type", "string")
        default = transform.get("default")
        value_mapping = transform.get("mapping", {})

        if value is None:
            return default

        if value_mapping and str(value) in value_mapping:
            return value_mapping[str(value)]

        try:
            if transform_type == "string":
                return str(value)
            elif transform_type == "integer":
                return int(float(value))
            elif transform_type == "float":
                return float(value)
            elif transform_type == "boolean":
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("true", "1", "yes", "是")
            elif transform_type == "date":
                fmt = transform.get("format", "%Y-%m-%d")
                if isinstance(value, str):
                    return datetime.strptime(value, fmt).date().isoformat()
                return value
            elif transform_type == "datetime":
                fmt = transform.get("format", "%Y-%m-%d %H:%M:%S")
                if isinstance(value, str):
                    return datetime.strptime(value, fmt).isoformat()
                return value
            elif transform_type == "json":
                import json

                if isinstance(value, str):
                    return json.loads(value)
                return value
            elif transform_type == "list":
                if isinstance(value, list):
                    return value
                delimiter = transform.get("delimiter", ",")
                return str(value).split(delimiter) if value else []
        except (ValueError, TypeError) as e:
            logger.warning(
                "Transform failed, using default",
                value=value,
                transform_type=transform_type,
                error=str(e),
            )
            return default

        return value

    def _validate_record(
        self, record: dict[str, Any], rules: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Validate a record against validation rules."""
        errors: list[str] = []

        required_fields = rules.get("required_fields", [])
        for field in required_fields:
            if field not in record or record[field] is None:
                errors.append(f"Missing required field: {field}")

        import re

        field_patterns = rules.get("field_patterns", {})
        for field, pattern in field_patterns.items():
            if field in record and record[field] is not None:
                if not re.match(pattern, str(record[field])):
                    errors.append(f"Field {field} does not match pattern: {pattern}")

        return len(errors) == 0, errors

    async def _fetch_batch(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], int]:
        """Fetch a batch of records from the API."""
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()

        data = response.json()

        pagination_config = params.get("_pagination_config", {})
        data_path = pagination_config.get("data_path", "data")
        total_path = pagination_config.get("total_path", "total")

        records = self._extract_nested_value(data, data_path)
        if records is None:
            records = data if isinstance(data, list) else []

        total = self._extract_nested_value(data, total_path)
        if total is None:
            total = len(records)

        return records, total

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute data import from OA system.

        Args:
            params: Import parameters including URL, data type, and mapping.
            context: Tool execution context.

        Returns:
            Dictionary containing imported data and import statistics.

        Raises:
            ValueError: If required parameters are missing.
            httpx.HTTPError: If API requests fail.
        """
        base_url = params["base_url"].rstrip("/")
        data_type = params["data_type"]
        auth_type = params.get("auth_type", "none")
        auth_credentials = params.get("auth_credentials", {})
        field_mapping = params.get("field_mapping", {})
        field_transforms = params.get("field_transforms", {})
        filters = params.get("filters", {})
        date_range = params.get("date_range")
        batch_size = params.get("batch_size", 100)
        max_records = params.get("max_records", 10000)
        pagination_config = params.get("pagination_config", {})
        validation_rules = params.get("validation_rules", {})
        custom_headers = params.get("headers", {})

        endpoint = params.get("endpoint") or self._get_endpoint_for_type(data_type)
        if not endpoint:
            raise ValueError(f"No endpoint for data type: {data_type}")

        url = urljoin(base_url + "/", endpoint.lstrip("/"))

        auth_headers = self._build_auth_headers(auth_type, auth_credentials)
        headers = {
            "Accept": "application/json",
            **auth_headers,
            **custom_headers,
        }

        page_param = pagination_config.get("page_param", "page")
        size_param = pagination_config.get("size_param", "page_size")
        offset_mode = pagination_config.get("offset_mode", False)
        offset_param = pagination_config.get("offset_param", "offset")

        logger.info(
            "Starting OA data import",
            url=url,
            data_type=data_type,
            batch_size=batch_size,
            max_records=max_records,
        )

        all_records: list[dict[str, Any]] = []
        failed_records: list[dict[str, Any]] = []
        validation_errors: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        unique_fields = validation_rules.get("unique_fields", [])

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            page = 1
            offset = 0
            total_fetched = 0
            total_available = None

            while True:
                query_params = {**filters}

                if offset_mode:
                    query_params[offset_param] = offset
                    query_params[size_param] = batch_size
                else:
                    query_params[page_param] = page
                    query_params[size_param] = batch_size

                if date_range:
                    date_field = date_range.get("field", "created_at")
                    if date_range.get("start"):
                        query_params[f"{date_field}_start"] = date_range["start"]
                    if date_range.get("end"):
                        query_params[f"{date_field}_end"] = date_range["end"]

                query_params["_pagination_config"] = pagination_config

                try:
                    records, total = await self._fetch_batch(
                        client, url, headers, query_params
                    )
                except httpx.HTTPError as e:
                    logger.error("Batch fetch failed", page=page, error=str(e))
                    failed_records.append({"page": page, "error": str(e)})
                    break

                if total_available is None:
                    total_available = total

                if not records:
                    break

                for record in records:
                    if total_fetched >= max_records:
                        break

                    if field_mapping:
                        mapped_record = self._apply_field_mapping(
                            record, field_mapping, field_transforms
                        )
                    else:
                        mapped_record = record

                    if validation_rules:
                        is_valid, errors = self._validate_record(
                            mapped_record, validation_rules
                        )
                        if not is_valid:
                            validation_errors.append({
                                "record": mapped_record,
                                "errors": errors,
                            })
                            continue

                    is_duplicate = False
                    for unique_field in unique_fields:
                        if unique_field in mapped_record:
                            field_value = str(mapped_record[unique_field])
                            unique_key = f"{unique_field}:{field_value}"
                            if unique_key in seen_ids:
                                is_duplicate = True
                                break
                            seen_ids.add(unique_key)

                    if is_duplicate:
                        continue

                    all_records.append(mapped_record)
                    total_fetched += 1

                if total_fetched >= max_records:
                    break

                if offset_mode:
                    offset += batch_size
                    if offset >= total_available:
                        break
                else:
                    page += 1
                    if len(records) < batch_size:
                        break

                await asyncio.sleep(0.1)

        logger.info(
            "OA data import completed",
            total_imported=len(all_records),
            total_failed=len(failed_records),
            total_validation_errors=len(validation_errors),
        )

        return {
            "success": True,
            "data_type": data_type,
            "records": all_records,
            "statistics": {
                "total_imported": len(all_records),
                "total_available": total_available,
                "failed_batches": len(failed_records),
                "validation_errors": len(validation_errors),
                "duplicates_skipped": len(seen_ids) - len(all_records)
                if unique_fields
                else 0,
            },
            "errors": {
                "failed_batches": failed_records[:10],
                "validation_errors": validation_errors[:10],
            },
        }
