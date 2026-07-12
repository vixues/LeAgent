"""Tests for MCP manager YAML persistence."""

from __future__ import annotations

import pytest
import yaml

from leagent.mcp.base import MCPServer, MCPTransport
from leagent.mcp.manager import MCPClientManager, reset_mcp_manager


@pytest.fixture(autouse=True)
def _reset_mgr() -> None:
    reset_mcp_manager()
    yield
    reset_mcp_manager()


@pytest.mark.asyncio
async def test_save_and_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "mcp_servers.yaml"
    mgr = MCPClientManager(config_path=path)
    mgr.add_server(
        MCPServer(
            name="filesystem",
            transport=MCPTransport.STDIO,
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            description="fs",
        ),
        persist=True,
    )
    assert path.is_file()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "mcpServers" in raw
    assert "filesystem" in raw["mcpServers"]
    assert raw["mcpServers"]["filesystem"]["command"] == "npx"

    mgr2 = MCPClientManager(config_path=path)
    count = await mgr2.load_config()
    assert count == 1
    assert "filesystem" in mgr2.server_names
    managed = mgr2._clients["filesystem"]
    assert managed.config.command == "npx"
    assert managed.config.args[0] == "-y"


def test_remove_persists(tmp_path) -> None:
    path = tmp_path / "mcp_servers.yaml"
    mgr = MCPClientManager(config_path=path)
    mgr.add_server(
        MCPServer(name="demo", transport=MCPTransport.STDIO, command="echo"),
        persist=True,
    )
    assert mgr.remove_server("demo", persist=True)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert raw["mcpServers"] == {}
