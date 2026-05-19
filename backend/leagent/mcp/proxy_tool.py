"""MCPProxyTool: Wraps an MCP tool as a BaseTool for registration in ToolRegistry.

This is the bridge between the MCP layer and the agent's tool system.
Tools are named ``mcp__<server>__<tool>`` following the reference convention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

if TYPE_CHECKING:
    from leagent.mcp.base import MCPTool
    from leagent.mcp.client import MCPClient

logger = structlog.get_logger(__name__)


class MCPProxyTool(BaseTool):
    """Wraps an MCPTool as a BaseTool.

    The tool is registered under the ``mcp__<server>__<tool>`` naming
    convention, making it discoverable by the agent alongside native tools.
    """

    category = ToolCategory.INTEGRATION
    is_concurrency_safe = True   # MCP calls are generally stateless
    is_read_only = False          # conservative default

    def __init__(
        self,
        mcp_tool: MCPTool,
        server_name: str,
        client: MCPClient,
    ) -> None:
        self._mcp_tool = mcp_tool
        self._server_name = server_name
        self._client = client
        self.name = f"mcp__{server_name}__{mcp_tool.name}"
        self.description = (
            f"[MCP:{server_name}] {mcp_tool.description or mcp_tool.name}"
        )
        self.search_hint = f"mcp {server_name} {mcp_tool.name}"

    @property
    def parameters(self) -> dict[str, Any]:
        """Return the MCP tool's input schema."""
        return self._mcp_tool.input_schema or {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        """Forward the call to the MCP server and return the result."""
        if not self._client.is_connected:
            return {"error": f"MCP server '{self._server_name}' is not connected"}

        try:
            # Strip the namespace prefix before forwarding
            result = await self._client.call_tool(self._mcp_tool.name, params)
            logger.debug(
                "mcp_tool_called",
                server=self._server_name,
                tool=self._mcp_tool.name,
            )
            return result
        except Exception as e:
            logger.warning(
                "mcp_tool_failed",
                server=self._server_name,
                tool=self._mcp_tool.name,
                error=str(e),
            )
            return {"error": str(e)}
