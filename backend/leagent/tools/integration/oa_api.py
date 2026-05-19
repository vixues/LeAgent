"""OA API Tool - Connect to OA systems via REST API.

Provides generic OA system integration with authentication handling
and common operations like submit, approve, and query.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from enum import Enum
from typing import Any
from urllib.parse import urljoin

import httpx
import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class OAAuthType(str, Enum):
    """Authentication types for OA systems."""

    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    HMAC = "hmac"


class OAOperation(str, Enum):
    """Standard OA operations."""

    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    QUERY = "query"
    CANCEL = "cancel"
    WITHDRAW = "withdraw"
    FORWARD = "forward"
    DELEGATE = "delegate"
    COMMENT = "comment"
    CUSTOM = "custom"


class OAApiTool(BaseTool):
    """Tool for connecting to OA systems via REST API.

    Features:
    - Multiple authentication methods (Basic, Bearer, API Key, OAuth2, HMAC)
    - Standard OA operations (submit, approve, reject, query, etc.)
    - Flexible endpoint configuration
    - Request/response transformation
    - Error handling and retry logic

    Example:
        >>> tool = OAApiTool()
        >>> result = await tool.run({
        ...     "base_url": "https://oa.company.com/api",
        ...     "operation": "submit",
        ...     "auth_type": "bearer",
        ...     "auth_credentials": {"token": "xxx"},
        ...     "data": {"form_id": "leave_request", "applicant": "张三"}
        ... }, context)
    """

    name = "oa_api"
    description = (
        "Connect to OA systems via REST API. Supports common operations like "
        "submit, approve, reject, query with multiple authentication methods."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 60
    max_retries = 2
    aliases = ["oa_rest", "oa_connect"]
    search_hint = "OA API REST submit approve reject query authentication"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "query")
        return f"OA API: {op}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "description": "Base URL of the OA system API",
                },
                "operation": {
                    "type": "string",
                    "enum": [op.value for op in OAOperation],
                    "description": "OA operation to perform",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Custom endpoint path (overrides operation-based endpoint)",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                    "default": "POST",
                    "description": "HTTP method to use",
                },
                "auth_type": {
                    "type": "string",
                    "enum": [auth.value for auth in OAAuthType],
                    "default": "none",
                    "description": "Authentication type",
                },
                "auth_credentials": {
                    "type": "object",
                    "description": "Authentication credentials based on auth_type",
                    "properties": {
                        "username": {"type": "string"},
                        "password": {"type": "string"},
                        "token": {"type": "string"},
                        "api_key": {"type": "string"},
                        "api_key_header": {"type": "string", "default": "X-API-Key"},
                        "client_id": {"type": "string"},
                        "client_secret": {"type": "string"},
                        "hmac_key": {"type": "string"},
                        "hmac_algorithm": {
                            "type": "string",
                            "enum": ["sha256", "sha512"],
                            "default": "sha256",
                        },
                    },
                },
                "data": {
                    "type": "object",
                    "description": "Request payload data",
                },
                "query_params": {
                    "type": "object",
                    "description": "URL query parameters",
                },
                "headers": {
                    "type": "object",
                    "description": "Additional HTTP headers",
                },
                "instance_id": {
                    "type": "string",
                    "description": "Workflow instance ID (for approve/reject/query operations)",
                },
                "task_id": {
                    "type": "string",
                    "description": "Task ID for approval operations",
                },
                "comment": {
                    "type": "string",
                    "description": "Comment for approval/rejection",
                },
                "assignee": {
                    "type": "string",
                    "description": "Assignee user ID (for forward/delegate operations)",
                },
                "response_mapping": {
                    "type": "object",
                    "description": "Field mapping for response transformation",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["base_url", "operation"],
        }

    def _get_operation_config(self, operation: str) -> dict[str, Any]:
        """Get default endpoint and method for standard operations."""
        configs = {
            OAOperation.SUBMIT.value: {"endpoint": "/workflow/submit", "method": "POST"},
            OAOperation.APPROVE.value: {"endpoint": "/workflow/approve", "method": "POST"},
            OAOperation.REJECT.value: {"endpoint": "/workflow/reject", "method": "POST"},
            OAOperation.QUERY.value: {"endpoint": "/workflow/query", "method": "GET"},
            OAOperation.CANCEL.value: {"endpoint": "/workflow/cancel", "method": "POST"},
            OAOperation.WITHDRAW.value: {"endpoint": "/workflow/withdraw", "method": "POST"},
            OAOperation.FORWARD.value: {"endpoint": "/workflow/forward", "method": "POST"},
            OAOperation.DELEGATE.value: {"endpoint": "/workflow/delegate", "method": "POST"},
            OAOperation.COMMENT.value: {"endpoint": "/workflow/comment", "method": "POST"},
            OAOperation.CUSTOM.value: {"endpoint": "", "method": "POST"},
        }
        return configs.get(operation, {"endpoint": "", "method": "POST"})

    def _build_auth_headers(
        self,
        auth_type: str,
        credentials: dict[str, Any],
        method: str,
        url: str,
        body: bytes | None,
    ) -> dict[str, str]:
        """Build authentication headers based on auth type."""
        headers: dict[str, str] = {}

        if auth_type == OAAuthType.NONE.value:
            pass

        elif auth_type == OAAuthType.BASIC.value:
            import base64

            username = credentials.get("username", "")
            password = credentials.get("password", "")
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"

        elif auth_type == OAAuthType.BEARER.value:
            token = credentials.get("token", "")
            headers["Authorization"] = f"Bearer {token}"

        elif auth_type == OAAuthType.API_KEY.value:
            api_key = credentials.get("api_key", "")
            header_name = credentials.get("api_key_header", "X-API-Key")
            headers[header_name] = api_key

        elif auth_type == OAAuthType.HMAC.value:
            hmac_key = credentials.get("hmac_key", "")
            algorithm = credentials.get("hmac_algorithm", "sha256")
            timestamp = str(int(time.time()))

            sign_content = f"{method}\n{url}\n{timestamp}\n"
            if body:
                sign_content += body.decode()

            hash_func = hashlib.sha256 if algorithm == "sha256" else hashlib.sha512
            signature = hmac.new(
                hmac_key.encode(), sign_content.encode(), hash_func
            ).hexdigest()

            headers["X-Timestamp"] = timestamp
            headers["X-Signature"] = signature

        return headers

    def _build_request_data(
        self, operation: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        """Build request data based on operation type."""
        data = params.get("data", {}).copy()
        instance_id = params.get("instance_id")
        task_id = params.get("task_id")
        comment = params.get("comment")
        assignee = params.get("assignee")

        if instance_id:
            data["instance_id"] = instance_id
        if task_id:
            data["task_id"] = task_id

        if operation in [OAOperation.APPROVE.value, OAOperation.REJECT.value]:
            if comment:
                data["comment"] = comment
            data["action"] = operation

        elif operation in [OAOperation.FORWARD.value, OAOperation.DELEGATE.value]:
            if assignee:
                data["assignee"] = assignee
            if comment:
                data["comment"] = comment

        elif operation == OAOperation.COMMENT.value:
            if comment:
                data["content"] = comment

        return data

    def _apply_response_mapping(
        self, response_data: Any, mapping: dict[str, str]
    ) -> dict[str, Any]:
        """Apply field mapping to transform response."""
        if not mapping or not isinstance(response_data, dict):
            return response_data

        result = {}
        for target_field, source_path in mapping.items():
            value = response_data
            for key in source_path.split("."):
                if isinstance(value, dict):
                    value = value.get(key)
                elif isinstance(value, list) and key.isdigit():
                    idx = int(key)
                    value = value[idx] if idx < len(value) else None
                else:
                    value = None
                    break
            result[target_field] = value

        for key, value in response_data.items():
            if key not in result:
                result[key] = value

        return result

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute OA API request.

        Args:
            params: Request parameters including URL, operation, auth, and data.
            context: Tool execution context.

        Returns:
            Dictionary containing response data and metadata.

        Raises:
            ValueError: If required parameters are missing.
            httpx.HTTPError: If the HTTP request fails.
        """
        base_url = params["base_url"].rstrip("/")
        operation = params["operation"]
        auth_type = params.get("auth_type", OAAuthType.NONE.value)
        auth_credentials = params.get("auth_credentials", {})
        custom_headers = params.get("headers", {})
        query_params = params.get("query_params", {})
        response_mapping = params.get("response_mapping", {})

        op_config = self._get_operation_config(operation)
        endpoint = params.get("endpoint") or op_config["endpoint"]
        method = params.get("method") or op_config["method"]

        if operation == OAOperation.CUSTOM.value and not endpoint:
            raise ValueError("Custom operation requires 'endpoint' parameter")

        url = urljoin(base_url + "/", endpoint.lstrip("/"))

        request_data = self._build_request_data(operation, params)

        body_bytes: bytes | None = None
        if method in ["POST", "PUT", "PATCH"] and request_data:
            import json

            body_bytes = json.dumps(request_data).encode()

        auth_headers = self._build_auth_headers(
            auth_type, auth_credentials, method, url, body_bytes
        )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **auth_headers,
            **custom_headers,
        }

        logger.info(
            "Executing OA API request",
            url=url,
            operation=operation,
            method=method,
            auth_type=auth_type,
        )

        async with httpx.AsyncClient(timeout=self.timeout_sec) as client:
            if method == "GET":
                merged_params = {**query_params, **request_data}
                response = await client.get(url, params=merged_params, headers=headers)
            elif method == "POST":
                response = await client.post(
                    url, json=request_data, params=query_params, headers=headers
                )
            elif method == "PUT":
                response = await client.put(
                    url, json=request_data, params=query_params, headers=headers
                )
            elif method == "PATCH":
                response = await client.patch(
                    url, json=request_data, params=query_params, headers=headers
                )
            elif method == "DELETE":
                response = await client.delete(
                    url, params=query_params, headers=headers
                )
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()

            try:
                response_data = response.json()
            except Exception:
                response_data = {"raw_response": response.text}

        if response_mapping:
            response_data = self._apply_response_mapping(response_data, response_mapping)

        logger.info(
            "OA API request completed",
            url=url,
            operation=operation,
            status_code=response.status_code,
        )

        return {
            "success": True,
            "operation": operation,
            "status_code": response.status_code,
            "data": response_data,
            "url": url,
        }
