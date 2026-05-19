"""Base MCP (Model Context Protocol) classes and models.

This module provides the foundational data models for MCP server configuration,
tools, prompts, and resources as defined by the MCP specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MCPTransport(str, Enum):
    """Transport protocol for MCP server communication."""

    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"


@dataclass
class MCPServer:
    """Configuration for an MCP server connection.

    Attributes:
        name: Unique identifier for this server.
        transport: Communication protocol to use.
        command: Command to execute for stdio transport.
        args: Arguments for the command.
        env: Environment variables for the process.
        url: URL for HTTP/SSE transports.
        api_key: Optional API key for authentication.
        timeout_sec: Connection and request timeout in seconds.
        enabled: Whether this server is enabled.
        auto_connect: Whether to connect automatically on startup.
        description: Optional human-readable description for UI / operators.
        metadata: Additional server metadata.
    """

    name: str
    transport: MCPTransport = MCPTransport.STDIO
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    api_key: str | None = None
    # OAuth 2.0 fields
    oauth_token: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_token_url: str | None = None
    oauth_scopes: list[str] = field(default_factory=list)
    timeout_sec: int = 30
    enabled: bool = True
    auto_connect: bool = True
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.transport == MCPTransport.STDIO and not self.command:
            raise ValueError("stdio transport requires a command")
        if self.transport in (MCPTransport.HTTP, MCPTransport.SSE) and not self.url:
            raise ValueError(f"{self.transport.value} transport requires a URL")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServer:
        """Create an MCPServer from a dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            MCPServer instance.
        """
        transport_str = data.get("transport", "stdio")
        transport = MCPTransport(transport_str) if isinstance(transport_str, str) else transport_str

        meta = dict(data.get("metadata") or {})
        description = data.get("description")
        if description is None:
            description = meta.pop("description", None)

        return cls(
            name=data["name"],
            transport=transport,
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env", {}),
            url=data.get("url"),
            api_key=data.get("api_key"),
            oauth_token=data.get("oauth_token"),
            oauth_client_id=data.get("oauth_client_id"),
            oauth_client_secret=data.get("oauth_client_secret"),
            oauth_token_url=data.get("oauth_token_url"),
            oauth_scopes=data.get("oauth_scopes", []),
            timeout_sec=data.get("timeout_sec", 30),
            enabled=data.get("enabled", True),
            auto_connect=data.get("auto_connect", True),
            description=description,
            metadata=meta,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "transport": self.transport.value,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "url": self.url,
            "api_key": self.api_key,
            "oauth_token": self.oauth_token,
            "oauth_client_id": self.oauth_client_id,
            "oauth_client_secret": self.oauth_client_secret,
            "oauth_token_url": self.oauth_token_url,
            "oauth_scopes": self.oauth_scopes,
            "timeout_sec": self.timeout_sec,
            "enabled": self.enabled,
            "auto_connect": self.auto_connect,
            "description": self.description,
            "metadata": self.metadata,
        }


@dataclass
class MCPTool:
    """Represents a tool provided by an MCP server.

    Attributes:
        name: Tool identifier.
        description: Human-readable description.
        input_schema: JSON Schema for tool parameters.
        server_name: Name of the server providing this tool.
    """

    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], server_name: str = "") -> MCPTool:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            input_schema=data.get("inputSchema", data.get("input_schema", {})),
            server_name=server_name,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "server_name": self.server_name,
        }

    def to_openai_schema(self) -> dict[str, Any]:
        """Generate OpenAI function-calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass
class MCPPrompt:
    """Represents a prompt template provided by an MCP server.

    Attributes:
        name: Prompt identifier.
        description: Human-readable description.
        arguments: List of argument definitions.
        server_name: Name of the server providing this prompt.
    """

    name: str
    description: str
    arguments: list[dict[str, Any]] = field(default_factory=list)
    server_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], server_name: str = "") -> MCPPrompt:
        """Create from dictionary."""
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            arguments=data.get("arguments", []),
            server_name=server_name,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
            "server_name": self.server_name,
        }

    def get_required_arguments(self) -> list[str]:
        """Get list of required argument names."""
        return [arg["name"] for arg in self.arguments if arg.get("required", False)]

    def get_optional_arguments(self) -> list[str]:
        """Get list of optional argument names."""
        return [arg["name"] for arg in self.arguments if not arg.get("required", False)]


@dataclass
class MCPResource:
    """Represents a resource provided by an MCP server.

    Attributes:
        uri: Resource URI.
        name: Human-readable name.
        description: Resource description.
        mime_type: MIME type of the resource.
        server_name: Name of the server providing this resource.
    """

    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"
    server_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], server_name: str = "") -> MCPResource:
        """Create from dictionary."""
        return cls(
            uri=data["uri"],
            name=data.get("name", data["uri"]),
            description=data.get("description", ""),
            mime_type=data.get("mimeType", data.get("mime_type", "text/plain")),
            server_name=server_name,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
            "server_name": self.server_name,
        }


@dataclass
class MCPCapabilities:
    """Server capability flags.

    Attributes:
        tools: Whether server supports tools.
        prompts: Whether server supports prompts.
        resources: Whether server supports resources.
        logging: Whether server supports logging.
    """

    tools: bool = False
    prompts: bool = False
    resources: bool = False
    logging: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPCapabilities:
        """Create from dictionary."""
        return cls(
            tools="tools" in data,
            prompts="prompts" in data,
            resources="resources" in data,
            logging="logging" in data,
        )


@dataclass
class MCPServerInfo:
    """Information about a connected MCP server.

    Attributes:
        name: Server name.
        version: Server version.
        protocol_version: MCP protocol version.
        capabilities: Server capabilities.
    """

    name: str
    version: str = ""
    protocol_version: str = ""
    capabilities: MCPCapabilities = field(default_factory=MCPCapabilities)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerInfo:
        """Create from dictionary."""
        caps_data = data.get("capabilities", {})
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            protocol_version=data.get("protocolVersion", ""),
            capabilities=MCPCapabilities.from_dict(caps_data),
        )
