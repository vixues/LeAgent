"""MCP client manager for managing multiple server connections.

This module provides the MCPClientManager class for centralized management
of MCP server connections, including hot-reload and health monitoring.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import structlog
import yaml

from leagent.mcp.base import MCPPrompt, MCPResource, MCPServer, MCPTool
from leagent.mcp.client import MCPClient, MCPConnectionError, MCPProtocolError
from leagent.mcp.proxy_tool import MCPProxyTool

logger = structlog.get_logger(__name__)


@dataclass
class ServerHealth:
    """Health status for an MCP server connection.

    Attributes:
        server_name: Name of the server.
        connected: Whether currently connected.
        last_check: Timestamp of last health check.
        last_error: Last error message if any.
        consecutive_failures: Number of consecutive failed checks.
        latency_ms: Last measured latency in milliseconds.
    """

    server_name: str
    connected: bool = False
    last_check: float = 0.0
    last_error: str | None = None
    consecutive_failures: int = 0
    latency_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "server_name": self.server_name,
            "connected": self.connected,
            "last_check": self.last_check,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "latency_ms": self.latency_ms,
        }


@dataclass
class ManagedClient:
    """Wrapper for a managed MCP client with metadata.

    Attributes:
        config: Server configuration.
        client: The MCP client instance.
        health: Current health status.
        tools: Cached tools list.
        prompts: Cached prompts list.
        resources: Cached resources list.
    """

    config: MCPServer
    client: MCPClient | None = None
    health: ServerHealth = field(default_factory=lambda: ServerHealth(""))
    tools: list[MCPTool] = field(default_factory=list)
    prompts: list[MCPPrompt] = field(default_factory=list)
    resources: list[MCPResource] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.health = ServerHealth(self.config.name)


class MCPClientManager:
    """Manager for multiple MCP server connections.

    Provides centralized management of MCP servers including:
    - Connection lifecycle management
    - Configuration hot-reload
    - Health monitoring and automatic reconnection
    - Aggregated tool/prompt/resource listings

    Example:
        >>> manager = MCPClientManager()
        >>> await manager.load_config("mcp_servers.yaml")
        >>> await manager.connect_all()
        >>> tools = manager.list_all_tools()
        >>> result = await manager.call_tool("server_name", "tool_name", {"arg": "val"})
    """

    def __init__(
        self,
        config_path: str | Path | None = None,
        health_check_interval: int = 60,
        max_reconnect_attempts: int = 3,
    ) -> None:
        """Initialize the manager.

        Args:
            config_path: Path to MCP servers configuration file.
            health_check_interval: Seconds between health checks.
            max_reconnect_attempts: Maximum reconnection attempts.
        """
        if config_path is not None:
            self._config_path = Path(config_path)
        else:
            from leagent.config.constants import LEAGENT_HOME

            self._config_path = LEAGENT_HOME / "mcp_servers.yaml"
        self._health_check_interval = health_check_interval
        self._max_reconnect_attempts = max_reconnect_attempts

        self._clients: dict[str, ManagedClient] = {}
        self._config_hash: str | None = None
        self._watch_task: asyncio.Task[None] | None = None
        self._health_task: asyncio.Task[None] | None = None
        self._running = False
        self._lock = asyncio.Lock()

        self._on_connect_callbacks: list[Callable[[str], None]] = []
        self._on_disconnect_callbacks: list[Callable[[str], None]] = []
        self._on_error_callbacks: list[Callable[[str, Exception], None]] = []

    @property
    def config_path(self) -> Path:
        """Path used for MCP server YAML persistence."""
        return self._config_path
    @property
    def server_names(self) -> list[str]:
        """Get list of configured server names."""
        return list(self._clients.keys())

    @property
    def connected_servers(self) -> list[str]:
        """Get list of currently connected server names."""
        return [name for name, mc in self._clients.items() if mc.client and mc.client.is_connected]

    def on_connect(self, callback: Callable[[str], None]) -> None:
        """Register callback for server connection events."""
        self._on_connect_callbacks.append(callback)

    def on_disconnect(self, callback: Callable[[str], None]) -> None:
        """Register callback for server disconnection events."""
        self._on_disconnect_callbacks.append(callback)

    def on_error(self, callback: Callable[[str, Exception], None]) -> None:
        """Register callback for server error events."""
        self._on_error_callbacks.append(callback)

    async def load_config(self, config_path: str | Path | None = None) -> int:
        """Load server configurations from YAML file.

        Args:
            config_path: Path to configuration file. Uses instance path if not provided.

        Returns:
            Number of servers configured.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If config file is invalid.
        """
        if config_path:
            self._config_path = Path(config_path)

        if not self._config_path:
            raise ValueError("No configuration path specified")

        if not self._config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self._config_path}")

        content = self._config_path.read_text()
        new_hash = hashlib.md5(content.encode()).hexdigest()

        if new_hash == self._config_hash:
            return len(self._clients)

        try:
            config_data = yaml.safe_load(content) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML configuration: {e}")

        servers_data = config_data.get("mcpServers", config_data.get("servers", {}))

        async with self._lock:
            new_configs: dict[str, MCPServer] = {}

            for name, server_data in servers_data.items():
                try:
                    server_data["name"] = name
                    config = MCPServer.from_dict(server_data)
                    new_configs[name] = config
                except Exception as e:
                    logger.warning("Failed to parse server config", server=name, error=str(e))

            removed = set(self._clients.keys()) - set(new_configs.keys())
            for name in removed:
                await self._disconnect_server(name)
                del self._clients[name]

            for name, config in new_configs.items():
                if name in self._clients:
                    existing = self._clients[name]
                    if self._config_changed(existing.config, config):
                        await self._disconnect_server(name)
                        existing.config = config
                        existing.client = None
                else:
                    self._clients[name] = ManagedClient(config=config)

            self._config_hash = new_hash

        logger.info(
            "MCP configuration loaded",
            total=len(self._clients),
            removed=len(removed),
            path=str(self._config_path),
        )
        return len(self._clients)

    def _config_changed(self, old: MCPServer, new: MCPServer) -> bool:
        """Check if configuration has changed."""
        return (
            old.transport != new.transport
            or old.command != new.command
            or old.args != new.args
            or old.url != new.url
            or old.env != new.env
            or old.description != new.description
        )

    def save_config(self, config_path: str | Path | None = None) -> Path:
        """Persist configured servers to YAML (``mcpServers`` dict format).

        Args:
            config_path: Optional override path; defaults to instance path.

        Returns:
            Path written.
        """
        path = Path(config_path) if config_path else self._config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        servers: dict[str, Any] = {}
        for name, managed in self._clients.items():
            data = managed.config.to_dict()
            # Name is the dict key; omit redundant field for cleaner YAML.
            data.pop("name", None)
            # Drop empty optional blobs to keep files readable.
            for empty_key in ("api_key", "oauth_token", "oauth_client_id", "oauth_client_secret", "oauth_token_url"):
                if not data.get(empty_key):
                    data.pop(empty_key, None)
            if not data.get("oauth_scopes"):
                data.pop("oauth_scopes", None)
            if not data.get("env"):
                data.pop("env", None)
            if not data.get("metadata"):
                data.pop("metadata", None)
            if not data.get("description"):
                data.pop("description", None)
            if data.get("transport") == "stdio":
                data.pop("url", None)
            elif data.get("transport") in ("http", "sse"):
                data.pop("command", None)
                if not data.get("args"):
                    data.pop("args", None)
            servers[name] = data

        payload = {"mcpServers": servers}
        content = yaml.safe_dump(
            payload,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        path.write_text(content, encoding="utf-8")
        self._config_hash = hashlib.md5(content.encode()).hexdigest()
        self._config_path = path
        logger.info("MCP configuration saved", path=str(path), total=len(servers))
        return path

    def add_server(self, config: MCPServer, *, persist: bool = False) -> None:
        """Add a server configuration programmatically.

        Args:
            config: Server configuration to add.
            persist: When True, write ``mcp_servers.yaml`` after add.
        """
        self._clients[config.name] = ManagedClient(config=config)
        logger.info("MCP server added", server=config.name)
        if persist:
            self.save_config()

    def remove_server(self, name: str, *, persist: bool = False) -> bool:
        """Remove a server configuration.

        Args:
            name: Server name to remove.
            persist: When True, write ``mcp_servers.yaml`` after remove.

        Returns:
            True if server was removed.
        """
        if name not in self._clients:
            return False

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._disconnect_server(name))
        except RuntimeError:
            # No running loop (e.g. sync test / CLI) — drop client only.
            pass
        del self._clients[name]
        logger.info("MCP server removed", server=name)
        if persist:
            self.save_config()
        return True
    async def connect_server(self, name: str) -> bool:
        """Connect to a specific server.

        Args:
            name: Server name to connect.

        Returns:
            True if connection successful.
        """
        if name not in self._clients:
            logger.warning("Server not found", server=name)
            return False

        managed = self._clients[name]

        if not managed.config.enabled:
            logger.debug("Server disabled, skipping connect", server=name)
            return False

        if managed.client and managed.client.is_connected:
            return True

        try:
            client = MCPClient(managed.config)
            await client._establish_connection()
            await client._initialize()
            client._connected = True

            managed.client = client
            managed.health.connected = True
            managed.health.last_check = time.time()
            managed.health.last_error = None
            managed.health.consecutive_failures = 0

            managed.tools = await client.list_tools()
            managed.prompts = await client.list_prompts()
            managed.resources = await client.list_resources()

            for callback in self._on_connect_callbacks:
                try:
                    callback(name)
                except Exception:
                    pass

            logger.info(
                "MCP server connected",
                server=name,
                tools=len(managed.tools),
                prompts=len(managed.prompts),
            )
            return True

        except MCPConnectionError as e:
            managed.health.connected = False
            managed.health.last_error = str(e)
            managed.health.consecutive_failures += 1

            for callback in self._on_error_callbacks:
                try:
                    callback(name, e)
                except Exception:
                    pass

            logger.error("Failed to connect to MCP server", server=name, error=str(e))
            return False

        except Exception as e:
            managed.health.connected = False
            managed.health.last_error = str(e)
            managed.health.consecutive_failures += 1

            for callback in self._on_error_callbacks:
                try:
                    callback(name, e)
                except Exception:
                    pass

            logger.exception("Unexpected error connecting to MCP server", server=name)
            return False

    async def _disconnect_server(self, name: str) -> None:
        """Disconnect from a server."""
        if name not in self._clients:
            return

        managed = self._clients[name]
        if managed.client:
            try:
                await managed.client.disconnect()
            except Exception:
                pass
            finally:
                managed.client = None
                managed.health.connected = False

        for callback in self._on_disconnect_callbacks:
            try:
                callback(name)
            except Exception:
                pass

        logger.debug("MCP server disconnected", server=name)

    async def connect_all(self) -> dict[str, bool]:
        """Connect to all configured and enabled servers.

        Returns:
            Dictionary mapping server names to connection success.
        """
        results = {}
        tasks = []

        for name, managed in self._clients.items():
            if managed.config.enabled and managed.config.auto_connect:
                tasks.append((name, self.connect_server(name)))

        for name, task in tasks:
            results[name] = await task

        connected = sum(1 for v in results.values() if v)
        logger.info("MCP connect_all complete", connected=connected, total=len(results))
        return results

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        for name in list(self._clients.keys()):
            await self._disconnect_server(name)
        logger.info("All MCP servers disconnected")

    def get_client(self, name: str) -> MCPClient | None:
        """Get a client by server name.

        Args:
            name: Server name.

        Returns:
            The MCPClient or None if not found/connected.
        """
        managed = self._clients.get(name)
        if managed and managed.client and managed.client.is_connected:
            return managed.client
        return None

    def get_server_health(self, name: str) -> ServerHealth | None:
        """Get health status for a server.

        Args:
            name: Server name.

        Returns:
            ServerHealth or None if server not found.
        """
        managed = self._clients.get(name)
        return managed.health if managed else None

    def get_all_health(self) -> dict[str, ServerHealth]:
        """Get health status for all servers."""
        return {name: mc.health for name, mc in self._clients.items()}

    def list_all_tools(self) -> list[MCPTool]:
        """List tools from all connected servers.

        Returns:
            Aggregated list of tools from all servers.
        """
        tools = []
        for managed in self._clients.values():
            if managed.client and managed.client.is_connected:
                tools.extend(managed.tools)
        return tools

    def list_server_tools(self, name: str) -> list[MCPTool]:
        """List tools from a specific server.

        Args:
            name: Server name.

        Returns:
            List of tools from the server.
        """
        managed = self._clients.get(name)
        if managed and managed.client and managed.client.is_connected:
            return managed.tools
        return []

    def list_all_prompts(self) -> list[MCPPrompt]:
        """List prompts from all connected servers."""
        prompts = []
        for managed in self._clients.values():
            if managed.client and managed.client.is_connected:
                prompts.extend(managed.prompts)
        return prompts

    def list_all_resources(self) -> list[MCPResource]:
        """List resources from all connected servers."""
        resources = []
        for managed in self._clients.values():
            if managed.client and managed.client.is_connected:
                resources.extend(managed.resources)
        return resources

    def find_tool(self, tool_name: str) -> tuple[str, MCPTool] | None:
        """Find a tool by name across all servers.

        Args:
            tool_name: Tool name to find.

        Returns:
            Tuple of (server_name, tool) or None if not found.
        """
        for name, managed in self._clients.items():
            for tool in managed.tools:
                if tool.name == tool_name:
                    return (name, tool)
        return None

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a tool on a specific server.

        Args:
            server_name: Name of the server.
            tool_name: Name of the tool to call.
            arguments: Tool arguments.

        Returns:
            Tool result.

        Raises:
            ValueError: If server not found or not connected.
            MCPProtocolError: If tool call fails.
        """
        client = self.get_client(server_name)
        if not client:
            raise ValueError(f"Server '{server_name}' not found or not connected")

        start_time = time.time()
        try:
            result = await client.call_tool(tool_name, arguments)
            latency = int((time.time() - start_time) * 1000)
            self._clients[server_name].health.latency_ms = latency
            return result
        except MCPProtocolError:
            raise
        except Exception as e:
            raise MCPProtocolError(f"Tool call failed: {e}")

    async def call_tool_by_name(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call a tool by name, finding the server automatically.

        Args:
            tool_name: Tool name.
            arguments: Tool arguments.

        Returns:
            Tool result.

        Raises:
            ValueError: If tool not found.
        """
        found = self.find_tool(tool_name)
        if not found:
            raise ValueError(f"Tool '{tool_name}' not found on any server")

        server_name, _ = found
        return await self.call_tool(server_name, tool_name, arguments)

    async def get_prompt(
        self,
        server_name: str,
        prompt_name: str,
        arguments: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Get a prompt from a specific server.

        Args:
            server_name: Server name.
            prompt_name: Prompt name.
            arguments: Prompt arguments.

        Returns:
            Prompt messages.
        """
        client = self.get_client(server_name)
        if not client:
            raise ValueError(f"Server '{server_name}' not found or not connected")

        return await client.get_prompt(prompt_name, arguments)

    async def read_resource(self, server_name: str, uri: str) -> dict[str, Any]:
        """Read a resource from a specific server.

        Args:
            server_name: Server name.
            uri: Resource URI.

        Returns:
            Resource content.
        """
        client = self.get_client(server_name)
        if not client:
            raise ValueError(f"Server '{server_name}' not found or not connected")

        return await client.read_resource(uri)

    async def start_background_tasks(self) -> None:
        """Start background health monitoring and config watching."""
        if self._running:
            return

        self._running = True

        if self._config_path:
            self._watch_task = asyncio.create_task(self._watch_config())

        self._health_task = asyncio.create_task(self._health_check_loop())

        logger.info("MCP manager background tasks started")

    async def stop_background_tasks(self) -> None:
        """Stop background tasks."""
        self._running = False

        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None

        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
            self._health_task = None

        logger.info("MCP manager background tasks stopped")

    async def _watch_config(self) -> None:
        """Watch configuration file for changes."""
        while self._running:
            try:
                await asyncio.sleep(5)

                if self._config_path and self._config_path.exists():
                    content = self._config_path.read_text()
                    new_hash = hashlib.md5(content.encode()).hexdigest()

                    if new_hash != self._config_hash:
                        logger.info("MCP config changed, reloading")
                        await self.load_config()
                        await self.connect_all()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error watching config", error=str(e))

    async def _health_check_loop(self) -> None:
        """Periodic health check for all servers."""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._check_all_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health check error", error=str(e))

    async def _check_all_health(self) -> None:
        """Check health of all servers and attempt reconnection if needed."""
        for name, managed in self._clients.items():
            if not managed.config.enabled:
                continue

            managed.health.last_check = time.time()

            if managed.client and managed.client.is_connected:
                try:
                    start = time.time()
                    await managed.client.list_tools()
                    managed.health.latency_ms = int((time.time() - start) * 1000)
                    managed.health.connected = True
                    managed.health.consecutive_failures = 0
                except Exception as e:
                    managed.health.connected = False
                    managed.health.last_error = str(e)
                    managed.health.consecutive_failures += 1
                    logger.warning("Health check failed", server=name, error=str(e))

            elif managed.health.consecutive_failures < self._max_reconnect_attempts:
                logger.info("Attempting reconnection", server=name)
                await self.connect_server(name)

    def get_openai_tool_schemas(self, server_names: list[str] | None = None) -> list[dict[str, Any]]:
        """Get OpenAI function-calling schemas for all MCP tools.

        Tool names follow the ``mcp__<server>__<tool>`` naming convention
        matching the reference architecture.

        Args:
            server_names: Optional list of server names to include.

        Returns:
            List of OpenAI function schemas with namespaced tool names.
        """
        tools = []

        for name, managed in self._clients.items():
            if server_names and name not in server_names:
                continue
            if managed.client and managed.client.is_connected:
                for tool in managed.tools:
                    schema = tool.to_openai_schema()
                    # Prefix tool name with server namespace
                    if "function" in schema:
                        schema["function"]["name"] = f"mcp__{name}__{schema['function']['name']}"
                    tools.append(schema)

        return tools

    async def register_tools_in_registry(
        self,
        registry: Any | None = None,
    ) -> int:
        """Register all connected MCP tools into the ToolRegistry.

        Creates thin ``MCPProxyTool`` wrappers for each tool discovered on
        connected servers and registers them under ``mcp__<server>__<tool>``
        names.

        Args:
            registry: ToolRegistry to register into.  Uses global registry
                      if not provided.

        Returns:
            Number of tools registered.
        """
        if registry is None:
            from leagent.tools.registry import get_registry
            registry = get_registry()

        count = 0
        for server_name, managed in self._clients.items():
            if not (managed.client and managed.client.is_connected):
                continue
            for mcp_tool in managed.tools:
                try:
                    proxy = MCPProxyTool(
                        mcp_tool=mcp_tool,
                        server_name=server_name,
                        client=managed.client,
                    )
                    registry.register(proxy)
                    count += 1
                except Exception as e:
                    logger.debug(
                        "mcp_tool_register_failed",
                        server=server_name,
                        tool=mcp_tool.name,
                        error=str(e),
                    )

        logger.info("mcp_tools_registered", count=count)
        return count

    async def list_resources(self, server_name: str) -> list[dict[str, Any]]:
        """List resources from a connected MCP server.

        Args:
            server_name: Name of the server to list resources from.

        Returns:
            List of resource dicts with uri, name, description.
        """
        managed = self._clients.get(server_name)
        if not managed or not managed.client or not managed.client.is_connected:
            return []

        try:
            resources = await managed.client.list_resources()
            return [
                {
                    "uri": r.uri,
                    "name": r.name,
                    "description": r.description,
                    "mime_type": r.mime_type,
                }
                for r in resources
            ]
        except Exception as e:
            logger.warning("mcp_list_resources_failed", server=server_name, error=str(e))
            return []

    async def read_resource(self, server_name: str, uri: str) -> str | None:
        """Read a resource from an MCP server.

        Args:
            server_name: Name of the server.
            uri: Resource URI to read.

        Returns:
            Resource content as string, or None on failure.
        """
        managed = self._clients.get(server_name)
        if not managed or not managed.client or not managed.client.is_connected:
            return None

        try:
            content = await managed.client.read_resource(uri)
            return content
        except Exception as e:
            logger.warning("mcp_read_resource_failed", server=server_name, uri=uri, error=str(e))
            return None

    async def shutdown(self) -> None:
        """Shutdown the manager, disconnecting all servers."""
        await self.stop_background_tasks()
        await self.disconnect_all()
        logger.info("MCP client manager shutdown complete")


_default_manager: MCPClientManager | None = None


def get_mcp_manager() -> MCPClientManager:
    """Get the default global MCP client manager.

    Returns:
        The singleton MCPClientManager instance.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = MCPClientManager()
    return _default_manager


def reset_mcp_manager() -> None:
    """Reset the default global manager (mainly for testing)."""
    global _default_manager
    _default_manager = None
