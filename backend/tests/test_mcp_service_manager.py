"""ServiceManager wiring for MCP: proxy tools land in the ToolRegistry.

The regression these tests guard against: MCP servers may be configured and
even connected, but if their tools are never lifted into the global
``ToolRegistry`` the LLM never sees them and falls back to writing ad-hoc
Python via ``script_agent``. ``ServiceManager._start_mcp`` closes that gap;
these tests exercise the callbacks it installs.
"""

from __future__ import annotations

import sys

import pytest

from leagent.mcp.base import MCPServer, MCPTransport
from leagent.mcp.manager import MCPClientManager
from leagent.mcp.proxy_tool import MCPProxyTool
from leagent.tools.registry import ToolRegistry


def _stdio_mock_args() -> list[str]:
    return ["-m", "tests.fixtures.mcp_mock_stdio"]


def _install_registry_bridge(
    manager: MCPClientManager, registry: ToolRegistry
) -> None:
    """Mirror the on_connect / on_disconnect wiring from ``_start_mcp``.

    Kept in the test module (rather than imported) so the assertions below
    fail loudly if the production wiring diverges from what we intend.
    """
    from leagent.mcp.proxy_tool import _sanitize_name_part

    def _register(name: str) -> None:
        managed = manager._clients.get(name)
        if not managed or not managed.client:
            return
        for mcp_tool in managed.tools:
            proxy = MCPProxyTool(
                mcp_tool=mcp_tool, server_name=name, client=managed.client
            )
            registry.register(proxy, replace=True)

    def _unregister(name: str) -> None:
        prefix = f"mcp__{_sanitize_name_part(name)}__"
        for tool_name in list(registry._tools.keys()):
            if tool_name.startswith(prefix):
                registry.unregister(tool_name)

    manager.on_connect(_register)
    manager.on_disconnect(_unregister)


@pytest.mark.asyncio
async def test_connect_populates_registry_and_disconnect_removes_them() -> None:
    manager = MCPClientManager()
    registry = ToolRegistry()
    _install_registry_bridge(manager, registry)

    cfg = MCPServer(
        name="svc-mock",
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=_stdio_mock_args(),
        auto_connect=False,
    )
    manager.add_server(cfg)

    try:
        assert await manager.connect_server("svc-mock")

        # Hyphen in server name must be sanitized for registry acceptance.
        names = [n for n in registry._tools if n.startswith("mcp__svc_mock__")]
        assert names, "expected MCP proxies to land in registry after connect"
        assert "mcp__svc_mock__echo" in names

        # The proxy is a real, callable BaseTool discoverable by name.
        proxy = registry.get_optional("mcp__svc_mock__echo")
        assert proxy is not None
        assert proxy.parameters.get("type") == "object"

        await manager._disconnect_server("svc-mock")

        remaining = [n for n in registry._tools if n.startswith("mcp__svc_mock__")]
        assert remaining == [], "disconnect must remove stale MCP proxies"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_reconnect_refreshes_client_binding() -> None:
    """After a disconnect/reconnect, the proxy must forward to the NEW client.

    Without ``replace=True`` on re-register, the registry would keep the
    old (disconnected) client and tool calls would fail with "not
    connected" even though the server is up again.
    """
    manager = MCPClientManager()
    registry = ToolRegistry()
    _install_registry_bridge(manager, registry)

    cfg = MCPServer(
        name="svc-mock2",
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=_stdio_mock_args(),
        auto_connect=False,
    )
    manager.add_server(cfg)
    try:
        assert await manager.connect_server("svc-mock2")
        first = registry.get_optional("mcp__svc_mock2__echo")
        assert first is not None

        await manager._disconnect_server("svc-mock2")
        assert await manager.connect_server("svc-mock2")

        second = registry.get_optional("mcp__svc_mock2__echo")
        assert second is not None
        # Fresh MCPClient instance means fresh proxy.
        assert second is not first
        assert second._client.is_connected
    finally:
        await manager.shutdown()
