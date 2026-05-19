"""MCP protocol constants shared by client and tests."""

# Must match what MCPClient sends in ``initialize`` and what servers return in ``initialize`` result.
MCP_PROTOCOL_VERSION = "2024-11-05"

CLIENT_INFO = {"name": "leagent", "version": "0.1.0"}
