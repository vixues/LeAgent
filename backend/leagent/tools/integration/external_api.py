"""External API Tool - Make HTTP requests to external APIs.

Provides a flexible HTTP client for integrating with external services
with support for various authentication methods, request/response
transformation, and rate limiting.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx
import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class AuthType(str, Enum):
    """Authentication types for external APIs."""

    NONE = "none"
    BASIC = "basic"
    BEARER = "bearer"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    HMAC = "hmac"
    DIGEST = "digest"
    AWS_SIGNATURE = "aws_signature"
    CUSTOM = "custom"


class ContentType(str, Enum):
    """Request content types."""

    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    MULTIPART = "multipart/form-data"
    XML = "application/xml"
    TEXT = "text/plain"


class RateLimiter:
    """Simple rate limiter for API requests."""

    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, float]:
        """Acquire permission to make a request.

        Returns:
            Tuple of (allowed, wait_seconds).
        """
        async with self._lock:
            now = time.time()
            window_start = now - window_seconds

            self._requests[key] = [
                ts for ts in self._requests[key] if ts > window_start
            ]

            if len(self._requests[key]) >= max_requests:
                oldest = min(self._requests[key])
                wait_time = oldest + window_seconds - now
                return False, max(0, wait_time)

            self._requests[key].append(now)
            return True, 0


_rate_limiter = RateLimiter()


class ExternalApiTool(BaseTool):
    """Tool for making HTTP requests to external APIs.

    Features:
    - Multiple authentication methods (Basic, Bearer, API Key, OAuth2, HMAC)
    - Request/response transformation
    - Rate limiting per endpoint
    - Retry logic with exponential backoff
    - Request/response logging
    - Timeout handling
    - SSL/TLS configuration

    Example:
        >>> tool = ExternalApiTool()
        >>> result = await tool.run({
        ...     "url": "https://api.example.com/users",
        ...     "method": "GET",
        ...     "auth_type": "bearer",
        ...     "auth_credentials": {"token": "xxx"},
        ...     "query_params": {"page": 1, "limit": 10}
        ... }, context)
    """

    name = "external_api"
    description = (
        "Make HTTP requests to external APIs with support for authentication, "
        "request/response transformation, and rate limiting."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 60
    max_retries = 2
    aliases = ["api", "http", "rest_api", "http_request"]
    search_hint = "HTTP API REST request GET POST PUT DELETE authentication rate limit"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        method = (params or {}).get("method", "GET")
        url = (params or {}).get("url", "")
        return f"Calling API: {method}{f' {url}' if url else ''}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL or base URL for the request",
                },
                "endpoint": {
                    "type": "string",
                    "description": "Endpoint path to append to URL",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                    "default": "GET",
                    "description": "HTTP method",
                },
                "auth_type": {
                    "type": "string",
                    "enum": [a.value for a in AuthType],
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
                        "api_key_param": {"type": "string"},
                        "client_id": {"type": "string"},
                        "client_secret": {"type": "string"},
                        "token_url": {"type": "string"},
                        "scope": {"type": "string"},
                        "hmac_key": {"type": "string"},
                        "hmac_algorithm": {"type": "string"},
                        "hmac_header": {"type": "string"},
                        "aws_access_key": {"type": "string"},
                        "aws_secret_key": {"type": "string"},
                        "aws_region": {"type": "string"},
                        "aws_service": {"type": "string"},
                        "custom_headers": {"type": "object"},
                    },
                },
                "headers": {
                    "type": "object",
                    "description": "Additional HTTP headers",
                },
                "query_params": {
                    "type": "object",
                    "description": "URL query parameters",
                },
                "body": {
                    "type": "object",
                    "description": "Request body data (for POST/PUT/PATCH)",
                },
                "raw_body": {
                    "type": "string",
                    "description": "Raw request body string",
                },
                "content_type": {
                    "type": "string",
                    "enum": [ct.value for ct in ContentType],
                    "default": "application/json",
                    "description": "Request content type",
                },
                "accept": {
                    "type": "string",
                    "description": "Accept header value",
                    "default": "application/json",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 300,
                },
                "follow_redirects": {
                    "type": "boolean",
                    "description": "Follow HTTP redirects",
                    "default": True,
                },
                "verify_ssl": {
                    "type": "boolean",
                    "description": "Verify SSL certificates",
                    "default": True,
                },
                "rate_limit": {
                    "type": "object",
                    "description": "Rate limiting configuration",
                    "properties": {
                        "max_requests": {"type": "integer", "default": 60},
                        "window_seconds": {"type": "integer", "default": 60},
                        "wait_on_limit": {"type": "boolean", "default": True},
                    },
                },
                "retry_config": {
                    "type": "object",
                    "description": "Retry configuration",
                    "properties": {
                        "max_retries": {"type": "integer", "default": 3},
                        "retry_on_status": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "default": [429, 500, 502, 503, 504],
                        },
                        "backoff_factor": {"type": "number", "default": 1.0},
                    },
                },
                "request_transform": {
                    "type": "object",
                    "description": "Transform request data before sending",
                    "properties": {
                        "field_mapping": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                        "add_fields": {"type": "object"},
                        "remove_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
                "response_transform": {
                    "type": "object",
                    "description": "Transform response data",
                    "properties": {
                        "data_path": {"type": "string"},
                        "field_mapping": {
                            "type": "object",
                            "additionalProperties": {"type": "string"},
                        },
                        "flatten": {"type": "boolean"},
                    },
                },
            },
            "required": ["url"],
        }

    async def _get_oauth2_token(
        self, credentials: dict[str, Any], client: httpx.AsyncClient
    ) -> str:
        """Obtain OAuth2 access token using client credentials flow."""
        token_url = credentials.get("token_url", "")
        client_id = credentials.get("client_id", "")
        client_secret = credentials.get("client_secret", "")
        scope = credentials.get("scope", "")

        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if scope:
            data["scope"] = scope

        response = await client.post(
            token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response.raise_for_status()

        token_data = response.json()
        return token_data.get("access_token", "")

    def _generate_hmac_signature(
        self,
        method: str,
        url: str,
        body: bytes | None,
        credentials: dict[str, Any],
    ) -> dict[str, str]:
        """Generate HMAC signature for request."""
        hmac_key = credentials.get("hmac_key", "")
        algorithm = credentials.get("hmac_algorithm", "sha256")
        header_name = credentials.get("hmac_header", "X-Signature")

        timestamp = str(int(time.time()))
        nonce = hashlib.md5(f"{timestamp}{url}".encode()).hexdigest()[:16]

        sign_parts = [method.upper(), url, timestamp, nonce]
        if body:
            body_hash = hashlib.sha256(body).hexdigest()
            sign_parts.append(body_hash)

        sign_string = "\n".join(sign_parts)

        hash_func = getattr(hashlib, algorithm, hashlib.sha256)
        signature = hmac.new(
            hmac_key.encode(), sign_string.encode(), hash_func
        ).hexdigest()

        return {
            header_name: signature,
            "X-Timestamp": timestamp,
            "X-Nonce": nonce,
        }

    def _build_auth_headers(
        self,
        auth_type: str,
        credentials: dict[str, Any],
        method: str,
        url: str,
        body: bytes | None,
        oauth2_token: str | None = None,
    ) -> dict[str, str]:
        """Build authentication headers."""
        headers: dict[str, str] = {}

        if auth_type == AuthType.NONE.value:
            pass

        elif auth_type == AuthType.BASIC.value:
            username = credentials.get("username", "")
            password = credentials.get("password", "")
            auth_string = base64.b64encode(f"{username}:{password}".encode()).decode()
            headers["Authorization"] = f"Basic {auth_string}"

        elif auth_type == AuthType.BEARER.value:
            token = credentials.get("token", "")
            headers["Authorization"] = f"Bearer {token}"

        elif auth_type == AuthType.API_KEY.value:
            api_key = credentials.get("api_key", "")
            header_name = credentials.get("api_key_header")
            if header_name:
                headers[header_name] = api_key

        elif auth_type == AuthType.OAUTH2.value:
            if oauth2_token:
                headers["Authorization"] = f"Bearer {oauth2_token}"

        elif auth_type == AuthType.HMAC.value:
            hmac_headers = self._generate_hmac_signature(
                method, url, body, credentials
            )
            headers.update(hmac_headers)

        elif auth_type == AuthType.CUSTOM.value:
            custom_headers = credentials.get("custom_headers", {})
            headers.update(custom_headers)

        return headers

    def _transform_request(
        self, data: dict[str, Any], transform: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply transformations to request data."""
        result = data.copy()

        field_mapping = transform.get("field_mapping", {})
        for target, source in field_mapping.items():
            if source in result:
                result[target] = result.pop(source)

        add_fields = transform.get("add_fields", {})
        result.update(add_fields)

        remove_fields = transform.get("remove_fields", [])
        for field in remove_fields:
            result.pop(field, None)

        return result

    def _extract_nested_value(self, data: Any, path: str) -> Any:
        """Extract value from nested structure using dot notation."""
        if not path:
            return data

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

    def _transform_response(
        self, data: Any, transform: dict[str, Any]
    ) -> Any:
        """Apply transformations to response data."""
        data_path = transform.get("data_path", "")
        if data_path:
            data = self._extract_nested_value(data, data_path)

        if not isinstance(data, dict):
            return data

        field_mapping = transform.get("field_mapping", {})
        if field_mapping:
            result = {}
            for target, source in field_mapping.items():
                result[target] = self._extract_nested_value(data, source)
            for key, value in data.items():
                if key not in result and key not in field_mapping.values():
                    result[key] = value
            data = result

        if transform.get("flatten") and isinstance(data, dict):
            data = self._flatten_dict(data)

        return data

    def _flatten_dict(
        self, d: dict[str, Any], parent_key: str = "", sep: str = "_"
    ) -> dict[str, Any]:
        """Flatten nested dictionary."""
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            else:
                items.append((new_key, v))
        return dict(items)

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute HTTP request to external API.

        Args:
            params: Request parameters.
            context: Tool execution context.

        Returns:
            Dictionary containing response data and metadata.

        Raises:
            ValueError: If request parameters are invalid.
            httpx.HTTPError: If the request fails.
        """
        base_url = params["url"].rstrip("/")
        endpoint = params.get("endpoint", "")
        method = params.get("method", "GET").upper()
        auth_type = params.get("auth_type", AuthType.NONE.value)
        auth_credentials = params.get("auth_credentials", {})
        custom_headers = params.get("headers", {})
        query_params = params.get("query_params", {})
        body_data = params.get("body", {})
        raw_body = params.get("raw_body")
        content_type = params.get("content_type", ContentType.JSON.value)
        accept = params.get("accept", "application/json")
        timeout = params.get("timeout", 30)
        follow_redirects = params.get("follow_redirects", True)
        verify_ssl = params.get("verify_ssl", True)
        rate_limit_config = params.get("rate_limit", {})
        retry_config = params.get("retry_config", {})
        request_transform = params.get("request_transform", {})
        response_transform = params.get("response_transform", {})

        if endpoint:
            url = urljoin(base_url + "/", endpoint.lstrip("/"))
        else:
            url = base_url

        if auth_type == AuthType.API_KEY.value:
            api_key_param = auth_credentials.get("api_key_param")
            if api_key_param:
                query_params[api_key_param] = auth_credentials.get("api_key", "")

        if rate_limit_config:
            max_requests = rate_limit_config.get("max_requests", 60)
            window_seconds = rate_limit_config.get("window_seconds", 60)
            wait_on_limit = rate_limit_config.get("wait_on_limit", True)

            rate_key = hashlib.md5(base_url.encode()).hexdigest()
            allowed, wait_time = await _rate_limiter.acquire(
                rate_key, max_requests, window_seconds
            )

            if not allowed:
                if wait_on_limit:
                    logger.info("Rate limited, waiting", wait_seconds=wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    raise RuntimeError(
                        f"Rate limit exceeded. Retry after {wait_time:.1f}s"
                    )

        if request_transform and body_data:
            body_data = self._transform_request(body_data, request_transform)

        body_bytes: bytes | None = None
        if method in ["POST", "PUT", "PATCH"]:
            if raw_body:
                body_bytes = raw_body.encode()
            elif body_data:
                if content_type == ContentType.JSON.value:
                    body_bytes = json.dumps(body_data).encode()
                elif content_type == ContentType.FORM.value:
                    body_bytes = urlencode(body_data).encode()
                elif content_type == ContentType.XML.value:
                    body_bytes = self._dict_to_xml(body_data).encode()

        max_retries = retry_config.get("max_retries", 3)
        retry_on_status = retry_config.get("retry_on_status", [429, 500, 502, 503, 504])
        backoff_factor = retry_config.get("backoff_factor", 1.0)

        logger.info(
            "Making external API request",
            url=url,
            method=method,
            auth_type=auth_type,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
            verify=verify_ssl,
        ) as client:
            oauth2_token = None
            if auth_type == AuthType.OAUTH2.value:
                oauth2_token = await self._get_oauth2_token(auth_credentials, client)

            auth_headers = self._build_auth_headers(
                auth_type, auth_credentials, method, url, body_bytes, oauth2_token
            )

            headers = {
                "Content-Type": content_type,
                "Accept": accept,
                **auth_headers,
                **custom_headers,
            }

            last_error: Exception | None = None
            response: httpx.Response | None = None

            for attempt in range(max_retries + 1):
                try:
                    request_kwargs: dict[str, Any] = {
                        "headers": headers,
                        "params": query_params,
                    }

                    if method == "GET":
                        response = await client.get(url, **request_kwargs)
                    elif method == "POST":
                        if content_type == ContentType.MULTIPART.value:
                            response = await client.post(
                                url, data=body_data, **request_kwargs
                            )
                        else:
                            response = await client.post(
                                url, content=body_bytes, **request_kwargs
                            )
                    elif method == "PUT":
                        response = await client.put(
                            url, content=body_bytes, **request_kwargs
                        )
                    elif method == "PATCH":
                        response = await client.patch(
                            url, content=body_bytes, **request_kwargs
                        )
                    elif method == "DELETE":
                        response = await client.delete(url, **request_kwargs)
                    elif method == "HEAD":
                        response = await client.head(url, **request_kwargs)
                    elif method == "OPTIONS":
                        response = await client.options(url, **request_kwargs)
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    if response.status_code in retry_on_status:
                        if attempt < max_retries:
                            wait_time = backoff_factor * (2 ** attempt)
                            logger.warning(
                                "Retryable status code",
                                status=response.status_code,
                                attempt=attempt + 1,
                                wait=wait_time,
                            )
                            await asyncio.sleep(wait_time)
                            continue

                    response.raise_for_status()
                    break

                except httpx.HTTPStatusError as e:
                    last_error = e
                    if e.response.status_code not in retry_on_status:
                        raise
                    if attempt >= max_retries:
                        raise

                except httpx.RequestError as e:
                    last_error = e
                    if attempt >= max_retries:
                        raise
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        "Request error, retrying",
                        error=str(e),
                        attempt=attempt + 1,
                        wait=wait_time,
                    )
                    await asyncio.sleep(wait_time)

        if response is None:
            raise RuntimeError(f"Request failed after {max_retries} retries: {last_error}")

        try:
            response_data = response.json()
        except Exception:
            response_data = {"raw_response": response.text}

        if response_transform:
            response_data = self._transform_response(response_data, response_transform)

        logger.info(
            "External API request completed",
            url=url,
            method=method,
            status_code=response.status_code,
        )

        return {
            "success": True,
            "url": url,
            "method": method,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "data": response_data,
            "elapsed_ms": int(response.elapsed.total_seconds() * 1000),
        }

    def _dict_to_xml(self, data: dict[str, Any], root: str = "request") -> str:
        """Convert dictionary to XML string."""
        xml_parts = [f"<{root}>"]

        def convert_value(key: str, value: Any) -> str:
            if value is None:
                return f"<{key}/>"
            elif isinstance(value, dict):
                inner = "".join(convert_value(k, v) for k, v in value.items())
                return f"<{key}>{inner}</{key}>"
            elif isinstance(value, list):
                items = "".join(convert_value("item", item) for item in value)
                return f"<{key}>{items}</{key}>"
            else:
                escaped = (
                    str(value)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                return f"<{key}>{escaped}</{key}>"

        for key, value in data.items():
            xml_parts.append(convert_value(key, value))

        xml_parts.append(f"</{root}>")
        return "".join(xml_parts)
