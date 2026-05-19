"""Tests for MCP base models: MCPServer, MCPTool, MCPCapabilities, and MCPProxyTool."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from leagent.mcp.base import (
    MCPCapabilities,
    MCPPrompt,
    MCPResource,
    MCPServer,
    MCPServerInfo,
    MCPTool,
    MCPTransport,
)


# ===========================================================================
# MCPServer
# ===========================================================================


class TestMCPServer:
    def test_stdio_construction(self) -> None:
        server = MCPServer(name="my_server", transport=MCPTransport.STDIO, command="python3")
        assert server.name == "my_server"
        assert server.transport == MCPTransport.STDIO
        assert server.command == "python3"

    def test_http_construction(self) -> None:
        server = MCPServer(name="http_server", transport=MCPTransport.HTTP, url="http://localhost:8000")
        assert server.transport == MCPTransport.HTTP

    def test_stdio_without_command_raises(self) -> None:
        with pytest.raises(ValueError, match="requires a command"):
            MCPServer(name="bad", transport=MCPTransport.STDIO, command=None)

    def test_http_without_url_raises(self) -> None:
        with pytest.raises(ValueError, match="requires a URL"):
            MCPServer(name="bad", transport=MCPTransport.HTTP, url=None)

    def test_from_dict(self) -> None:
        data = {
            "name": "test_server",
            "transport": "stdio",
            "command": "my_cmd",
            "args": ["--flag"],
            "timeout_sec": 60,
            "enabled": True,
        }
        server = MCPServer.from_dict(data)
        assert server.name == "test_server"
        assert server.command == "my_cmd"
        assert server.args == ["--flag"]
        assert server.timeout_sec == 60

    def test_to_dict(self) -> None:
        server = MCPServer(name="srv", transport=MCPTransport.STDIO, command="cmd")
        d = server.to_dict()
        assert d["name"] == "srv"
        assert d["transport"] == "stdio"
        assert d["command"] == "cmd"

    def test_roundtrip(self) -> None:
        server = MCPServer(
            name="srv",
            transport=MCPTransport.STDIO,
            command="my_cmd",
            args=["--a", "--b"],
            env={"KEY": "VALUE"},
            timeout_sec=45,
        )
        restored = MCPServer.from_dict(server.to_dict())
        assert restored.name == server.name
        assert restored.args == server.args
        assert restored.env == server.env
        assert restored.timeout_sec == server.timeout_sec

    def test_disabled_server(self) -> None:
        server = MCPServer(name="s", transport=MCPTransport.STDIO, command="c", enabled=False)
        assert not server.enabled

    def test_oauth_fields(self) -> None:
        data = {
            "name": "oauth_server",
            "transport": "http",
            "url": "https://api.example.com",
            "oauth_token": "tok",
            "oauth_client_id": "cid",
        }
        server = MCPServer.from_dict(data)
        assert server.oauth_token == "tok"
        assert server.oauth_client_id == "cid"


# ===========================================================================
# MCPTool
# ===========================================================================


class TestMCPTool:
    def test_basic_construction(self) -> None:
        tool = MCPTool(
            name="read_file",
            description="Reads a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            server_name="my_server",
        )
        assert tool.name == "read_file"
        assert tool.server_name == "my_server"

    def test_from_dict(self) -> None:
        data = {
            "name": "list_files",
            "description": "Lists files in directory",
            "inputSchema": {"type": "object", "properties": {}},
        }
        tool = MCPTool.from_dict(data, server_name="srv")
        assert tool.name == "list_files"
        assert tool.server_name == "srv"

    def test_from_dict_alternate_schema_key(self) -> None:
        data = {
            "name": "tool",
            "description": "A tool",
            "input_schema": {"type": "object"},
        }
        tool = MCPTool.from_dict(data)
        assert tool.input_schema == {"type": "object"}

    def test_to_dict(self) -> None:
        tool = MCPTool(
            name="my_tool",
            description="desc",
            input_schema={"type": "object"},
            server_name="srv",
        )
        d = tool.to_dict()
        assert d["name"] == "my_tool"
        assert d["inputSchema"] == {"type": "object"}

    def test_roundtrip(self) -> None:
        tool = MCPTool(
            name="t",
            description="d",
            input_schema={"type": "object", "required": ["x"]},
            server_name="s",
        )
        restored = MCPTool.from_dict(tool.to_dict(), server_name="s")
        assert restored.name == tool.name
        assert restored.input_schema == tool.input_schema

    def test_to_openai_schema(self) -> None:
        tool = MCPTool(
            name="my_tool",
            description="A helpful tool",
            input_schema={"type": "object", "properties": {}},
        )
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "my_tool"
        assert "parameters" in schema["function"]


# ===========================================================================
# MCPCapabilities
# ===========================================================================


class TestMCPCapabilities:
    def test_defaults_all_false(self) -> None:
        caps = MCPCapabilities()
        assert not caps.tools
        assert not caps.prompts
        assert not caps.resources
        assert not caps.logging

    def test_from_dict_with_tools(self) -> None:
        data = {"tools": {}, "prompts": {}}
        caps = MCPCapabilities.from_dict(data)
        assert caps.tools is True
        assert caps.prompts is True
        assert caps.resources is False

    def test_from_dict_full(self) -> None:
        data = {"tools": {}, "prompts": {}, "resources": {}, "logging": {}}
        caps = MCPCapabilities.from_dict(data)
        assert all([caps.tools, caps.prompts, caps.resources, caps.logging])

    def test_from_dict_empty(self) -> None:
        caps = MCPCapabilities.from_dict({})
        assert not caps.tools


# ===========================================================================
# MCPPrompt
# ===========================================================================


class TestMCPPrompt:
    def test_from_dict(self) -> None:
        data = {
            "name": "analyze_code",
            "description": "Analyzes code for issues",
            "arguments": [
                {"name": "code", "required": True},
                {"name": "language", "required": False},
            ],
        }
        prompt = MCPPrompt.from_dict(data, server_name="srv")
        assert prompt.name == "analyze_code"
        assert prompt.server_name == "srv"

    def test_required_arguments(self) -> None:
        data = {
            "name": "p",
            "description": "d",
            "arguments": [
                {"name": "required_arg", "required": True},
                {"name": "optional_arg", "required": False},
            ],
        }
        prompt = MCPPrompt.from_dict(data)
        assert "required_arg" in prompt.get_required_arguments()
        assert "optional_arg" not in prompt.get_required_arguments()
        assert "optional_arg" in prompt.get_optional_arguments()


# ===========================================================================
# MCPProxyTool
# ===========================================================================


class TestMCPProxyTool:
    def _make_proxy(
        self,
        tool_name: str = "read_file",
        server_name: str = "file_server",
    ):
        from leagent.mcp.proxy_tool import MCPProxyTool

        mcp_tool = MCPTool(
            name=tool_name,
            description="Reads a file",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        )
        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.call_tool = AsyncMock(return_value={"content": "file content"})

        return MCPProxyTool(
            mcp_tool=mcp_tool,
            server_name=server_name,
            client=mock_client,
        )

    def test_naming_convention(self) -> None:
        proxy = self._make_proxy("read_file", "file_server")
        assert proxy.name == "mcp__file_server__read_file"

    def test_description_includes_server(self) -> None:
        proxy = self._make_proxy("read_file", "my_server")
        assert "my_server" in proxy.description

    def test_parameters_passthrough(self) -> None:
        proxy = self._make_proxy()
        params = proxy.parameters
        assert "properties" in params

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        from leagent.tools.base import ToolContext
        proxy = self._make_proxy()
        ctx = ToolContext(user_id="u", session_id="s")
        result = await proxy.execute({"path": "/tmp/test.txt"}, ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_disconnected_returns_error(self) -> None:
        from leagent.tools.base import ToolContext
        from leagent.mcp.proxy_tool import MCPProxyTool

        mcp_tool = MCPTool(name="t", description="d", input_schema={"type": "object"})
        mock_client = MagicMock()
        mock_client.is_connected = False

        proxy = MCPProxyTool(mcp_tool, "srv", mock_client)
        ctx = ToolContext(user_id="u", session_id="s")
        result = await proxy.execute({}, ctx)
        assert "error" in result


# ===========================================================================
# MCPServerInfo
# ===========================================================================


class TestMCPServerInfo:
    def test_from_dict(self) -> None:
        data = {
            "name": "my_mcp",
            "version": "1.2.3",
            "protocolVersion": "2024-11",
            "capabilities": {"tools": {}, "resources": {}},
        }
        info = MCPServerInfo.from_dict(data)
        assert info.name == "my_mcp"
        assert info.version == "1.2.3"
        assert info.protocol_version == "2024-11"
        assert info.capabilities.tools is True
        assert info.capabilities.resources is True
