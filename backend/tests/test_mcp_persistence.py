"""Tests for MCP manager JSON persistence."""

from __future__ import annotations

import json

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
async def test_save_and_load_roundtrip_json(tmp_path) -> None:
    path = tmp_path / "mcp_servers.json"
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
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "mcpServers" in raw
    assert "filesystem" in raw["mcpServers"]
    entry = raw["mcpServers"]["filesystem"]
    assert entry["transportType"] == "stdio"
    assert entry["command"] == "npx"
    assert entry["args"][0] == "-y"

    mgr2 = MCPClientManager(config_path=path)
    count = await mgr2.load_config()
    assert count == 1
    assert "filesystem" in mgr2.server_names
    managed = mgr2._clients["filesystem"]
    assert managed.config.command == "npx"
    assert managed.config.args[0] == "-y"


@pytest.mark.asyncio
async def test_load_streamable_http_external_format(tmp_path) -> None:
    """A hand-written external JSON config loads with headers + timeout."""
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "project-search": {
                        "transportType": "streamableHttp",
                        "url": "http://source-webserver.example/source/mcp",
                        "headers": {"Authorization": "Bearer tok"},
                        "disabled": False,
                        "timeout": 120,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mgr = MCPClientManager(config_path=path)
    count = await mgr.load_config()
    assert count == 1
    cfg = mgr._clients["project-search"].config
    assert cfg.transport == MCPTransport.STREAMABLE_HTTP
    assert cfg.url == "http://source-webserver.example/source/mcp"
    assert cfg.headers == {"Authorization": "Bearer tok"}
    assert cfg.timeout_sec == 120
    assert cfg.enabled is True


def test_remove_persists_json(tmp_path) -> None:
    path = tmp_path / "mcp_servers.json"
    mgr = MCPClientManager(config_path=path)
    mgr.add_server(
        MCPServer(name="demo", transport=MCPTransport.STDIO, command="echo"),
        persist=True,
    )
    assert mgr.remove_server("demo", persist=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["mcpServers"] == {}


@pytest.mark.asyncio
async def test_yaml_backward_compat_load(tmp_path) -> None:
    """Legacy YAML files still load transparently."""
    path = tmp_path / "mcp_servers.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "mcpServers": {
                    "old": {
                        "transport": "stdio",
                        "command": "echo",
                        "args": ["hi"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    mgr = MCPClientManager(config_path=path)
    count = await mgr.load_config()
    assert count == 1
    cfg = mgr._clients["old"].config
    assert cfg.transport == MCPTransport.STDIO
    assert cfg.command == "echo"

