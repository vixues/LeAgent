"""OA Export Tool - Export data to OA systems.

Provides data export capabilities to OA systems with format conversion,
batch processing, and status tracking.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class ExportFormat(str, Enum):
    """Export data formats."""

    JSON = "json"
    XML = "xml"
    FORM_DATA = "form_data"
    CSV = "csv"


class ExportDataType(str, Enum):
    """Data types for export."""

    WORKFLOW_INSTANCE = "workflow_instance"
    FORM_DATA = "form_data"
    APPROVAL_RECORD = "approval_record"
    USER = "user"
    DEPARTMENT = "department"
    ATTACHMENT = "attachment"
    CUSTOM = "custom"


class ExportStatus(str, Enum):
    """Export operation status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class OAExportTool(BaseTool):
    """Tool for exporting data to OA systems.

    Features:
    - Export to multiple formats (JSON, XML, form data, CSV)
    - Field mapping and transformation
    - Batch export with concurrency control
    - Status tracking and progress reporting
    - Retry logic for failed records
    - Partial success handling

    Example:
        >>> tool = OAExportTool()
        >>> result = await tool.run({
        ...     "base_url": "https://oa.company.com/api",
        ...     "data_type": "workflow_instance",
        ...     "records": [{"title": "请假申请", "applicant": "张三"}],
        ...     "field_mapping": {"form_title": "title", "creator": "applicant"},
        ...     "format": "json"
        ... }, context)
    """

    name = "oa_export"
    description = (
        "Export data to OA systems with format conversion and batch processing. "
        "Supports exporting workflow instances, forms, users, and more."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 300
    max_retries = 2
    aliases = ["oa_data_export", "export_oa"]
    search_hint = "OA export data format batch workflow forms users"
    is_concurrency_safe = False
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Exporting OA data"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "Base URL of the OA system API",
                },
                "data_type": {
                    "type": "string",
                    "enum": [d.value for d in ExportDataType],
                    "description": "Type of data to export",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Custom API endpoint (overrides data_type endpoint)",
                },
                "method": {
                    "type": "string",
                    "enum": ["POST", "PUT", "PATCH"],
                    "default": "POST",
                    "description": "HTTP method for export",
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
                "records": {
                    "type": "array",
                    "description": "Records to export",
                    "items": {"type": "object"},
                },
                "field_mapping": {
                    "type": "object",
                    "description": "Field mapping from source to target format. Keys are target fields, values are source fields.",
                    "additionalProperties": {"type": "string"},
                },
                "field_transforms": {
                    "type": "object",
                    "description": "Field transformations for export",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "format": {"type": "string"},
                            "default": {},
                        },
                    },
                },
                "format": {
                    "type": "string",
                    "enum": [f.value for f in ExportFormat],
                    "default": "json",
                    "description": "Export data format",
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Number of records per batch request",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500,
                },
                "concurrency": {
                    "type": "integer",
                    "description": "Maximum concurrent requests",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "retry_failed": {
                    "type": "boolean",
                    "description": "Retry failed records",
                    "default": True,
                },
                "max_retries": {
                    "type": "integer",
                    "description": "Maximum retry attempts per record",
                    "default": 3,
                    "minimum": 0,
                    "maximum": 10,
                },
                "stop_on_error": {
                    "type": "boolean",
                    "description": "Stop export on first error",
                    "default": False,
                },
                "id_field": {
                    "type": "string",
                    "description": "Field to use as record identifier for tracking",
                    "default": "id",
                },
                "headers": {
                    "type": "object",
                    "description": "Additional HTTP headers",
                },
                "response_id_path": {
                    "type": "string",
                    "description": "Path to extract created ID from response",
                    "default": "id",
                },
            },
            "required": ["base_url", "data_type", "records"],
        }

    def _get_endpoint_for_type(self, data_type: str, method: str) -> str:
        """Get default endpoint for data type."""
        endpoints = {
            ExportDataType.WORKFLOW_INSTANCE.value: "/api/workflow/instances",
            ExportDataType.FORM_DATA.value: "/api/forms",
            ExportDataType.APPROVAL_RECORD.value: "/api/approvals",
            ExportDataType.USER.value: "/api/users",
            ExportDataType.DEPARTMENT.value: "/api/departments",
            ExportDataType.ATTACHMENT.value: "/api/attachments",
            ExportDataType.CUSTOM.value: "",
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
        """Apply field mapping and transformations for export."""
        if not mapping:
            return record.copy()

        result: dict[str, Any] = {}

        for target_field, source_field in mapping.items():
            value = self._extract_nested_value(record, source_field)

            if target_field in transforms:
                transform = transforms[target_field]
                value = self._transform_value(value, transform)

            result[target_field] = value

        return result

    def _transform_value(self, value: Any, transform: dict[str, Any]) -> Any:
        """Apply transformation to a value for export."""
        transform_type = transform.get("type", "string")
        default = transform.get("default")
        fmt = transform.get("format")

        if value is None:
            return default

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
                if isinstance(value, datetime):
                    return value.strftime(fmt or "%Y-%m-%d")
                return value
            elif transform_type == "datetime":
                if isinstance(value, datetime):
                    return value.strftime(fmt or "%Y-%m-%d %H:%M:%S")
                return value
            elif transform_type == "json":
                import json

                return json.dumps(value, ensure_ascii=False)
        except (ValueError, TypeError) as e:
            logger.warning(
                "Transform failed, using default",
                value=value,
                transform_type=transform_type,
                error=str(e),
            )
            return default

        return value

    def _convert_to_format(
        self, record: dict[str, Any], export_format: str
    ) -> Any:
        """Convert record to specified export format."""
        if export_format == ExportFormat.JSON.value:
            return record

        elif export_format == ExportFormat.XML.value:
            xml_parts = ["<record>"]
            for key, value in record.items():
                if value is None:
                    xml_parts.append(f"<{key}/>")
                else:
                    escaped = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    xml_parts.append(f"<{key}>{escaped}</{key}>")
            xml_parts.append("</record>")
            return "".join(xml_parts)

        elif export_format == ExportFormat.FORM_DATA.value:
            return {k: str(v) if v is not None else "" for k, v in record.items()}

        elif export_format == ExportFormat.CSV.value:
            import csv
            import io

            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=record.keys())
            writer.writerow(record)
            return output.getvalue()

        return record

    async def _export_record(
        self,
        client: httpx.AsyncClient,
        url: str,
        method: str,
        headers: dict[str, str],
        record: dict[str, Any],
        export_format: str,
        response_id_path: str,
    ) -> dict[str, Any]:
        """Export a single record to the OA system."""
        converted_data = self._convert_to_format(record, export_format)

        content_type = "application/json"
        if export_format == ExportFormat.XML.value:
            content_type = "application/xml"
        elif export_format == ExportFormat.FORM_DATA.value:
            content_type = "application/x-www-form-urlencoded"

        request_headers = {**headers, "Content-Type": content_type}

        if method == "POST":
            if export_format == ExportFormat.FORM_DATA.value:
                response = await client.post(url, data=converted_data, headers=request_headers)
            elif export_format == ExportFormat.XML.value:
                response = await client.post(url, content=converted_data, headers=request_headers)
            else:
                response = await client.post(url, json=converted_data, headers=request_headers)
        elif method == "PUT":
            response = await client.put(url, json=converted_data, headers=request_headers)
        elif method == "PATCH":
            response = await client.patch(url, json=converted_data, headers=request_headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        response.raise_for_status()

        try:
            response_data = response.json()
            created_id = self._extract_nested_value(response_data, response_id_path)
        except Exception:
            response_data = {"raw_response": response.text}
            created_id = None

        return {
            "status": "success",
            "status_code": response.status_code,
            "created_id": created_id,
            "response": response_data,
        }

    async def _export_batch(
        self,
        client: httpx.AsyncClient,
        url: str,
        method: str,
        headers: dict[str, str],
        records: list[dict[str, Any]],
        export_format: str,
        id_field: str,
        response_id_path: str,
        max_retries: int,
        retry_failed: bool,
    ) -> list[dict[str, Any]]:
        """Export a batch of records with retry logic."""
        results = []

        for record in records:
            record_id = record.get(id_field, str(uuid.uuid4()))
            attempts = 0
            last_error = None

            while attempts <= max_retries:
                try:
                    result = await self._export_record(
                        client, url, method, headers, record,
                        export_format, response_id_path
                    )
                    result["record_id"] = record_id
                    result["attempts"] = attempts + 1
                    results.append(result)
                    break

                except httpx.HTTPError as e:
                    last_error = str(e)
                    attempts += 1
                    if attempts <= max_retries and retry_failed:
                        await asyncio.sleep(2 ** attempts * 0.5)
                    else:
                        break

            if attempts > max_retries or (attempts > 0 and not retry_failed):
                results.append({
                    "status": "failed",
                    "record_id": record_id,
                    "error": last_error,
                    "attempts": attempts,
                })

        return results

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute data export to OA system.

        Args:
            params: Export parameters including URL, data type, records, and mapping.
            context: Tool execution context.

        Returns:
            Dictionary containing export results and statistics.

        Raises:
            ValueError: If required parameters are missing.
            httpx.HTTPError: If API requests fail.
        """
        base_url = params["base_url"].rstrip("/")
        data_type = params["data_type"]
        records = params["records"]
        method = params.get("method", "POST")
        auth_type = params.get("auth_type", "none")
        auth_credentials = params.get("auth_credentials", {})
        field_mapping = params.get("field_mapping", {})
        field_transforms = params.get("field_transforms", {})
        export_format = params.get("format", ExportFormat.JSON.value)
        batch_size = params.get("batch_size", 50)
        concurrency = params.get("concurrency", 5)
        retry_failed = params.get("retry_failed", True)
        max_retries = params.get("max_retries", 3)
        stop_on_error = params.get("stop_on_error", False)
        id_field = params.get("id_field", "id")
        custom_headers = params.get("headers", {})
        response_id_path = params.get("response_id_path", "id")

        if not records:
            return {
                "success": True,
                "data_type": data_type,
                "status": ExportStatus.COMPLETED.value,
                "statistics": {"total": 0, "success": 0, "failed": 0},
                "results": [],
            }

        endpoint = params.get("endpoint") or self._get_endpoint_for_type(data_type, method)
        if not endpoint:
            raise ValueError(f"No endpoint for data type: {data_type}")

        url = urljoin(base_url + "/", endpoint.lstrip("/"))

        auth_headers = self._build_auth_headers(auth_type, auth_credentials)
        headers = {
            "Accept": "application/json",
            **auth_headers,
            **custom_headers,
        }

        mapped_records = []
        for record in records:
            if field_mapping:
                mapped_record = self._apply_field_mapping(
                    record, field_mapping, field_transforms
                )
            else:
                mapped_record = record.copy()
            if id_field not in mapped_record:
                mapped_record[id_field] = record.get(id_field, str(uuid.uuid4()))
            mapped_records.append(mapped_record)

        logger.info(
            "Starting OA data export",
            url=url,
            data_type=data_type,
            total_records=len(mapped_records),
            batch_size=batch_size,
            concurrency=concurrency,
        )

        export_id = str(uuid.uuid4())
        started_at = datetime.utcnow()

        all_results: list[dict[str, Any]] = []
        batches = [
            mapped_records[i:i + batch_size]
            for i in range(0, len(mapped_records), batch_size)
        ]

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            semaphore = asyncio.Semaphore(concurrency)

            async def process_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
                async with semaphore:
                    return await self._export_batch(
                        client, url, method, headers, batch,
                        export_format, id_field, response_id_path,
                        max_retries, retry_failed
                    )

            error_occurred = False
            for batch_idx, batch in enumerate(batches):
                if stop_on_error and error_occurred:
                    break

                try:
                    batch_results = await process_batch(batch)
                    all_results.extend(batch_results)

                    for result in batch_results:
                        if result.get("status") == "failed":
                            error_occurred = True
                            if stop_on_error:
                                break

                except Exception as e:
                    logger.error("Batch export failed", batch_idx=batch_idx, error=str(e))
                    error_occurred = True
                    for record in batch:
                        all_results.append({
                            "status": "failed",
                            "record_id": record.get(id_field),
                            "error": str(e),
                        })
                    if stop_on_error:
                        break

        completed_at = datetime.utcnow()

        success_count = sum(1 for r in all_results if r.get("status") == "success")
        failed_count = sum(1 for r in all_results if r.get("status") == "failed")

        if failed_count == 0:
            status = ExportStatus.COMPLETED.value
        elif success_count == 0:
            status = ExportStatus.FAILED.value
        else:
            status = ExportStatus.PARTIAL.value

        logger.info(
            "OA data export completed",
            export_id=export_id,
            status=status,
            success=success_count,
            failed=failed_count,
            duration_ms=int((completed_at - started_at).total_seconds() * 1000),
        )

        return {
            "success": status != ExportStatus.FAILED.value,
            "export_id": export_id,
            "data_type": data_type,
            "status": status,
            "statistics": {
                "total": len(records),
                "success": success_count,
                "failed": failed_count,
                "batches_processed": len(batches),
            },
            "timing": {
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "duration_ms": int((completed_at - started_at).total_seconds() * 1000),
            },
            "results": all_results,
            "failed_records": [r for r in all_results if r.get("status") == "failed"][:20],
        }
