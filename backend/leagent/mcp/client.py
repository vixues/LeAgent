"""MCP client for connecting to MCP servers.

This module provides the MCPClient class for establishing connections
to MCP servers and invoking their tools, prompts, and resources.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

import httpx
import structlog

from leagent.utils.httpx_proxy import httpx_trust_env

from leagent.mcp.base import (
    MCPCapabilities,
    MCPPrompt,
    MCPResource,
    MCPServer,
    MCPServerInfo,
    MCPTool,
    MCPTransport,
)
from leagent.mcp.constants import CLIENT_INFO, MCP_PROTOCOL_VERSION

if TYPE_CHECKING:
    from asyncio.subprocess import Process

logger = structlog.get_logger(__name__)


class MCPConnectionError(Exception):
    """Raised when connection to MCP server fails."""

    def __init__(self, server_name: str, reason: str) -> None:
        self.server_name = server_name
        self.reason = reason
        super().__init__(f"Failed to connect to MCP server '{server_name}': {reason}")


class MCPProtocolError(Exception):
    """Raised when MCP protocol communication fails."""

    def __init__(self, message: str, code: int | None = None) -> None:
        self.code = code
        super().__init__(message)


class MCPClient:
    """Client for communicating with an MCP server.

    Supports stdio, HTTP, and SSE transports for flexible server connectivity.
    Handles the MCP JSON-RPC protocol for tool invocation and resource access.

    Example:
        >>> config = MCPServer(name="example", command="mcp-server")
        >>> client = MCPClient(config)
        >>> async with client.connect():
        ...     tools = await client.list_tools()
        ...     result = await client.call_tool("my_tool", {"arg": "value"})
    """

    def __init__(self, config: MCPServer) -> None:
        """Initialize the MCP client.

        Args:
            config: Server configuration.
        """
        self.config = config
        self._process: Process | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._request_id = 0
        self._connected = False
        self._server_info: MCPServerInfo | None = None
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        """Get server name."""
        return self.config.name

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    @property
    def server_info(self) -> MCPServerInfo | None:
        """Get server information from initialization."""
        return self._server_info

    @property
    def capabilities(self) -> MCPCapabilities:
        """Get server capabilities."""
        if self._server_info:
            return self._server_info.capabilities
        return MCPCapabilities()

    def _next_request_id(self) -> int:
        """Generate next request ID."""
        self._request_id += 1
        return self._request_id

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[MCPClient]:
        """Connect to the MCP server.

        Yields:
            The connected client instance.

        Raises:
            MCPConnectionError: If connection fails.
        """
        try:
            await self._establish_connection()
            await self._initialize()
            self._connected = True
            logger.info("MCP client connected", server=self.name)
            yield self
        finally:
            await self.disconnect()

    async def _establish_connection(self) -> None:
        """Establish the underlying connection based on transport type."""
        if self.config.transport == MCPTransport.STDIO:
            await self._connect_stdio()
        elif self.config.transport in (MCPTransport.HTTP, MCPTransport.SSE):
            await self._connect_http()
        else:
            raise MCPConnectionError(self.name, f"Unsupported transport: {self.config.transport}")

    async def _connect_stdio(self) -> None:
        """Establish stdio connection by spawning subprocess."""
        if not self.config.command:
            raise MCPConnectionError(self.name, "No command specified for stdio transport")

        cmd = [self.config.command] + self.config.args
        env = {**os.environ, **self.config.env}

        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            logger.debug("Spawned MCP server process", server=self.name, pid=self._process.pid)
        except FileNotFoundError:
            raise MCPConnectionError(self.name, f"Command not found: {self.config.command}")
        except PermissionError:
            raise MCPConnectionError(self.name, f"Permission denied: {self.config.command}")
        except Exception as e:
            raise MCPConnectionError(self.name, f"Failed to spawn process: {e}")

    async def _connect_http(self) -> None:
        """Establish HTTP/SSE connection, optionally acquiring an OAuth 2.0 token."""
        if not self.config.url:
            raise MCPConnectionError(self.name, "No URL specified for HTTP transport")

        headers: dict[str, str] = {}

        if self.config.oauth_token:
            # Pre-configured static OAuth token (XAA / personal access token)
            headers["Authorization"] = f"Bearer {self.config.oauth_token}"
        elif self.config.oauth_client_id and self.config.oauth_client_secret and self.config.oauth_token_url:
            # OAuth 2.0 client-credentials flow
            token = await self._fetch_oauth_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            else:
                logger.warning("OAuth token fetch failed, connecting without auth", server=self.name)
        elif self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        # Direct MCP connections must not inherit HTTP(S)_PROXY — localhost
        # traffic through a broken corporate proxy surfaces as 502 in tests.
        self._http_client = httpx.AsyncClient(
            base_url=self.config.url,
            headers=headers,
            timeout=httpx.Timeout(self.config.timeout_sec),
            trust_env=False,
        )

    async def _fetch_oauth_token(self) -> str | None:
        """Fetch an OAuth 2.0 access token using the client-credentials grant.

        Returns:
            Access token string, or None on failure.
        """
        if not (self.config.oauth_token_url and self.config.oauth_client_id and self.config.oauth_client_secret):
            return None

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10),
                trust_env=httpx_trust_env(),
            ) as tmp_client:
                payload: dict[str, str] = {
                    "grant_type": "client_credentials",
                    "client_id": self.config.oauth_client_id,
                    "client_secret": self.config.oauth_client_secret,
                }
                if self.config.oauth_scopes:
                    payload["scope"] = " ".join(self.config.oauth_scopes)

                resp = await tmp_client.post(self.config.oauth_token_url, data=payload)
                resp.raise_for_status()
                token_data = resp.json()
                token = token_data.get("access_token")
                logger.info("OAuth token acquired", server=self.name, expires_in=token_data.get("expires_in"))
                return token
        except Exception as e:
            logger.error("OAuth token fetch failed", server=self.name, error=str(e))
            return None

    async def _initialize(self) -> None:
        """Initialize the MCP connection by exchanging capabilities."""
        response = await self._send_request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )

        self._server_info = MCPServerInfo.from_dict(response)
        await self._send_notification("notifications/initialized", {})

        logger.debug(
            "MCP server initialized",
            server=self.name,
            capabilities=self._server_info.capabilities,
        )

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        self._connected = False

        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            except Exception:
                pass
            finally:
                self._process = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.debug("MCP client disconnected", server=self.name)

    async def _send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for response.

        Args:
            method: RPC method name.
            params: Method parameters.

        Returns:
            Response result data.

        Raises:
            MCPProtocolError: If request fails.
        """
        request_id = self._next_request_id()
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        if self.config.transport == MCPTransport.STDIO:
            return await self._send_stdio_request(request)
        else:
            return await self._send_http_request(request)

    async def _send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification (no response expected).

        Args:
            method: Notification method name.
            params: Notification parameters.
        """
        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            notification["params"] = params

        if self.config.transport == MCPTransport.STDIO:
            await self._write_stdio(notification)
        else:
            await self._send_http_notification(notification)

    async def _send_stdio_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send request over stdio transport."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise MCPProtocolError("Process not connected")

        await self._write_stdio(request)
        response = await self._read_stdio()

        if "error" in response:
            error = response["error"]
            raise MCPProtocolError(error.get("message", "Unknown error"), error.get("code"))

        return response.get("result", {})

    async def _write_stdio(self, data: dict[str, Any]) -> None:
        """Write JSON-RPC message to stdio."""
        if not self._process or not self._process.stdin:
            raise MCPProtocolError("Process stdin not available")

        async with self._write_lock:
            message = json.dumps(data) + "\n"
            self._process.stdin.write(message.encode())
            await self._process.stdin.drain()

    async def _read_stdio(self) -> dict[str, Any]:
        """Read JSON-RPC message from stdio."""
        if not self._process or not self._process.stdout:
            raise MCPProtocolError("Process stdout not available")

        async with self._read_lock:
            try:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(),
                    timeout=self.config.timeout_sec,
                )
            except asyncio.TimeoutError:
                raise MCPProtocolError("Read timeout")

            if not line:
                raise MCPProtocolError("Connection closed")

            try:
                return json.loads(line.decode())
            except json.JSONDecodeError as e:
                raise MCPProtocolError(f"Invalid JSON response: {e}")

    async def _send_http_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send request over HTTP transport."""
        if not self._http_client:
            raise MCPProtocolError("HTTP client not connected")

        try:
            response = await self._http_client.post("/rpc", json=request)
            response.raise_for_status()
            data = response.json()

            if "error" in data:
                error = data["error"]
                raise MCPProtocolError(error.get("message", "Unknown error"), error.get("code"))

            return data.get("result", {})

        except httpx.HTTPStatusError as e:
            raise MCPProtocolError(f"HTTP error: {e.response.status_code}")
        except httpx.RequestError as e:
            raise MCPProtocolError(f"Request failed: {e}")

    async def _send_http_notification(self, notification: dict[str, Any]) -> None:
        """Send notification over HTTP transport."""
        if not self._http_client:
            return

        try:
            await self._http_client.post("/rpc", json=notification)
        except Exception:
            pass

    async def list_tools(self) -> list[MCPTool]:
        """List all tools provided by the server.

        Returns:
            List of available tools.
        """
        if not self.capabilities.tools:
            return []

        response = await self._send_request("tools/list")
        tools_data = response.get("tools", [])
        return [MCPTool.from_dict(t, self.name) for t in tools_data]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call a tool on the server.

        Args:
            name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool execution result.

        Raises:
            MCPProtocolError: If tool call fails.
        """
        params: dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments

        response = await self._send_request("tools/call", params)
        content = response.get("content", [])

        if response.get("isError"):
            error_text = self._extract_text_content(content)
            raise MCPProtocolError(f"Tool error: {error_text}")

        return self._extract_content(content)

    async def list_prompts(self) -> list[MCPPrompt]:
        """List all prompts provided by the server.

        Returns:
            List of available prompts.
        """
        if not self.capabilities.prompts:
            return []

        response = await self._send_request("prompts/list")
        prompts_data = response.get("prompts", [])
        return [MCPPrompt.from_dict(p, self.name) for p in prompts_data]

    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Get a prompt with filled arguments.

        Args:
            name: Prompt name.
            arguments: Prompt arguments.

        Returns:
            Dictionary containing the prompt messages.
        """
        params: dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments

        return await self._send_request("prompts/get", params)

    async def list_resources(self) -> list[MCPResource]:
        """List all resources provided by the server.

        Returns:
            List of available resources.
        """
        if not self.capabilities.resources:
            return []

        response = await self._send_request("resources/list")
        resources_data = response.get("resources", [])
        return [MCPResource.from_dict(r, self.name) for r in resources_data]

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource by URI.

        Args:
            uri: Resource URI.

        Returns:
            Resource content.
        """
        return await self._send_request("resources/read", {"uri": uri})

    def _extract_content(self, content: list[dict[str, Any]]) -> Any:
        """Extract content from MCP content array."""
        if not content:
            return None

        if len(content) == 1:
            item = content[0]
            if item.get("type") == "text":
                return item.get("text")
            return item

        return content

    def _extract_text_content(self, content: list[dict[str, Any]]) -> str:
        """Extract text from content array."""
        texts = []
        for item in content:
            if item.get("type") == "text":
                texts.append(item.get("text", ""))
        return "\n".join(texts)
