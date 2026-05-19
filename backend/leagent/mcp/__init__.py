"""MCP (Model Context Protocol) package.

This package provides client connectivity to MCP servers for tool,
prompt, and resource integration.
"""

from leagent.mcp.base import (
    MCPCapabilities,
    MCPPrompt,
    MCPResource,
    MCPServer,
    MCPServerInfo,
    MCPTool,
    MCPTransport,
)
from leagent.mcp.client import (
    MCPClient,
    MCPConnectionError,
    MCPProtocolError,
)
from leagent.mcp.manager import (
    MCPClientManager,
    ManagedClient,
    ServerHealth,
    get_mcp_manager,
    reset_mcp_manager,
)

__all__ = [
    "MCPCapabilities",
    "MCPClient",
    "MCPClientManager",
    "MCPConnectionError",
    "MCPPrompt",
    "MCPProtocolError",
    "MCPResource",
    "MCPServer",
    "MCPServerInfo",
    "MCPTool",
    "MCPTransport",
    "ManagedClient",
    "ServerHealth",
    "get_mcp_manager",
    "reset_mcp_manager",
]
