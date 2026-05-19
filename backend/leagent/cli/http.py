"""HTTP client helpers for CLI commands that call the running FastAPI app.

``LEAGENT_API_URL`` (default ``http://localhost:7860``) and optional ``LEAGENT_API_KEY``
select the target deployment; most subcommands assume the monolith is already up
(``leagent run`` / ``leagent app start``).
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import httpx

from leagent.cli.utils import exit_with_error

DEFAULT_BASE_URL = "http://localhost:7860"
DEFAULT_TIMEOUT = 30.0


class CLIHttpClient:
    """HTTP client wrapper for CLI commands."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the HTTP client.

        Args:
            base_url: Base URL of the LeAgent server.
            api_key: API key for authentication.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url or os.getenv("LEAGENT_API_URL", DEFAULT_BASE_URL)
        self.api_key = api_key or os.getenv("LEAGENT_API_KEY", "")
        self.timeout = timeout
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialize and return the httpx client."""
        if self._client is None:
            headers = {
                "User-Agent": "LeAgent-CLI/1.0",
                "Accept": "application/json",
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    def _build_url(self, endpoint: str) -> str:
        """Build full URL from endpoint."""
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]
        return urljoin(self.base_url, endpoint)

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle response and return JSON data or raise error."""
        try:
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_data = e.response.json()
                error_detail = error_data.get("detail", str(error_data))
            except Exception:
                error_detail = e.response.text or str(e)
            raise CLIHttpError(
                f"HTTP {e.response.status_code}: {error_detail}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise CLIHttpError(f"Request failed: {e}") from e

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint path.
            params: Query parameters.

        Returns:
            Response JSON data.
        """
        response = self.client.get(endpoint, params=params)
        return self._handle_response(response)

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path.
            data: Form data.
            json: JSON body data.

        Returns:
            Response JSON data.
        """
        response = self.client.post(endpoint, data=data, json=json)
        return self._handle_response(response)

    def put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint path.
            data: Form data.
            json: JSON body data.

        Returns:
            Response JSON data.
        """
        response = self.client.put(endpoint, data=data, json=json)
        return self._handle_response(response)

    def patch(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a PATCH request.

        Args:
            endpoint: API endpoint path.
            data: Form data.
            json: JSON body data.

        Returns:
            Response JSON data.
        """
        response = self.client.patch(endpoint, data=data, json=json)
        return self._handle_response(response)

    def delete(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint path.
            params: Query parameters.

        Returns:
            Response JSON data.
        """
        response = self.client.delete(endpoint, params=params)
        return self._handle_response(response)

    def stream_sse(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ):
        """Make a POST request and yield SSE events as dicts.

        Yields parsed SSE event dicts with 'event' and 'data' keys.
        """
        with httpx.Client(
            base_url=self.base_url,
            headers=self.client._headers,
            timeout=None,
            follow_redirects=True,
        ) as stream_client:
            with stream_client.stream("POST", endpoint, data=data, json=json) as response:
                response.raise_for_status()
                event_type = ""
                event_data = ""
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        event_data = line[5:].strip()
                    elif line == "":
                        if event_data:
                            import json as json_mod
                            parsed: Any = event_data
                            try:
                                parsed = json_mod.loads(event_data)
                            except (json_mod.JSONDecodeError, ValueError):
                                pass
                            yield {"event": event_type or "message", "data": parsed}
                            event_type = ""
                            event_data = ""

    def health_check(self) -> bool:
        """Check if the server is healthy.

        Returns:
            True if server is healthy, False otherwise.
        """
        try:
            response = self.client.get("/health")
            return response.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "CLIHttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class CLIHttpError(Exception):
    """Exception raised for CLI HTTP errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


_default_client: CLIHttpClient | None = None


def get_client(
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> CLIHttpClient:
    """Get or create a shared HTTP client instance.

    Args:
        base_url: Base URL of the LeAgent server.
        api_key: API key for authentication.
        timeout: Request timeout in seconds.

    Returns:
        CLIHttpClient instance.
    """
    global _default_client

    if base_url or api_key or _default_client is None:
        _default_client = CLIHttpClient(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
        )

    return _default_client


def require_server(func):
    """Decorator that ensures server is running before executing command."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        client = get_client()
        if not client.health_check():
            exit_with_error(
                f"Cannot connect to LeAgent server at {client.base_url}. "
                "Is the server running? Start it with: leagent app"
            )
        return func(*args, **kwargs)

    return wrapper
