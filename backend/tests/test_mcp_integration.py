"""Integration tests: real MCP JSON-RPC against mock stdio and HTTP servers."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from uuid import UUID

import pytest

from tests.fixtures.mcp_mock_http import mcp_rpc_http_server
from tests.fixtures.mcp_mock_protocol import handle_mcp_message

from leagent.mcp.base import MCPServer, MCPTransport
from leagent.mcp.client import MCPClient, MCPConnectionError, MCPProtocolError
from leagent.mcp.manager import MCPClientManager


def _stdio_mock_args() -> list[str]:
    """Run stdio mock as a module (``backend`` must be on ``PYTHONPATH`` / cwd)."""
    return ["-m", "tests.fixtures.mcp_mock_stdio"]


@pytest.mark.asyncio
async def test_mcp_client_stdio_initialize_list_echo() -> None:
    cfg = MCPServer(
        name="stdio_mock",
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=_stdio_mock_args(),
        timeout_sec=30,
    )
    client = MCPClient(cfg)
    async with client.connect():
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert "echo" in names and "fail" in names
        out = await client.call_tool("echo", {"message": "hi"})
        assert isinstance(out, str)
        assert "hi" in out
        data = json.loads(out)
        assert data.get("message") == "hi"


@pytest.mark.asyncio
async def test_mcp_client_stdio_fail_tool_raises() -> None:
    cfg = MCPServer(
        name="stdio_mock_fail",
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=_stdio_mock_args(),
    )
    client = MCPClient(cfg)
    async with client.connect():
        with pytest.raises(MCPProtocolError, match="Tool error"):
            await client.call_tool("fail", {})


@pytest.mark.asyncio
async def test_mcp_client_http_list_and_echo() -> None:
    async with mcp_rpc_http_server() as port:
        cfg = MCPServer(
            name="http_mock",
            transport=MCPTransport.HTTP,
            url=f"http://127.0.0.1:{port}",
            timeout_sec=30,
        )
        client = MCPClient(cfg)
        async with client.connect():
            tools = await client.list_tools()
            assert any(t.name == "echo" for t in tools)
            out = await client.call_tool("echo", {"x": 1})
            assert json.loads(str(out)) == {"x": 1}


@pytest.mark.asyncio
async def test_mcp_client_http_invalid_json_returns_error() -> None:
    async with mcp_rpc_http_server() as port:
        import httpx

        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}",
            timeout=10,
            trust_env=False,
        ) as ac:
            r = await ac.post("/rpc", content=b"not-json", headers={"Content-Type": "application/json"})
            assert r.status_code == 400


@pytest.mark.asyncio
async def test_mcp_manager_stdio_connect_call_shutdown() -> None:
    mgr = MCPClientManager()
    cfg = MCPServer(
        name="mgr_stdio",
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=_stdio_mock_args(),
        auto_connect=False,
    )
    mgr.add_server(cfg)
    assert await mgr.connect_server("mgr_stdio")
    assert mgr.get_client("mgr_stdio") is not None
    assert len(mgr.list_server_tools("mgr_stdio")) >= 2
    result = await mgr.call_tool("mgr_stdio", "echo", {"k": "v"})
    assert json.loads(str(result)) == {"k": "v"}
    await mgr._disconnect_server("mgr_stdio")
    assert mgr.get_client("mgr_stdio") is None
    await mgr.shutdown()


@pytest.mark.asyncio
async def test_mcp_manager_prompts_and_resources() -> None:
    mgr = MCPClientManager()
    cfg = MCPServer(
        name="mgr_full",
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=_stdio_mock_args(),
        auto_connect=False,
    )
    mgr.add_server(cfg)
    assert await mgr.connect_server("mgr_full")
    managed = mgr._clients.get("mgr_full")
    assert managed is not None
    assert len(managed.prompts) >= 1
    assert len(managed.resources) >= 1
    pr = await mgr.get_prompt("mgr_full", "greet", {"name": "Ada"})
    assert "messages" in pr
    raw = await mgr.read_resource("mgr_full", "mock://config")
    assert raw is not None
    await mgr.shutdown()


@pytest.mark.asyncio
async def test_protocol_handler_unknown_method() -> None:
    out = handle_mcp_message(
        {"jsonrpc": "2.0", "id": 99, "method": "does/not/exist", "params": {}},
    )
    assert out is not None and "error" in out


def test_stdio_script_exists() -> None:
    script = Path(__file__).resolve().parent / "fixtures" / "mcp_mock_stdio.py"
    assert script.is_file()


@pytest.mark.asyncio
async def test_mcp_api_stdio_connect_and_tools(
    async_client,
    test_user: dict,
    test_settings,
) -> None:
    """Smoke REST ``/api/v1/mcp`` against the process-wide manager (same as ServiceManager)."""
    # Lifespan may skip auth when DB/bootstrap fails; MCP routes still need ``get_auth_service()``.
    from leagent.services.auth.service import init_auth_service
    from leagent.services.auth import AuthService

    init_auth_service(test_settings)
    token = AuthService(test_settings).create_access_token(UUID(test_user["user_id"]))
    headers = {"Authorization": f"Bearer {token}"}
    server_name = f"api_stdio_{uuid.uuid4().hex[:10]}"
    create = await async_client.post(
        "/api/v1/mcp/servers",
        headers=headers,
        json={
            "name": server_name,
            "transport": "stdio",
            "command": sys.executable,
            "args": _stdio_mock_args(),
            "enabled": True,
            "auto_connect": False,
        },
    )
    assert create.status_code == 201, create.text

    try:
        conn = await async_client.post(
            f"/api/v1/mcp/servers/{server_name}/connect",
            headers=headers,
        )
        assert conn.status_code == 200, conn.text
        body = conn.json()
        assert body.get("connected") is True

        tools = await async_client.get(
            "/api/v1/mcp/tools",
            headers=headers,
            params={"server_name": server_name},
        )
        assert tools.status_code == 200, tools.text
        listed = tools.json()
        assert isinstance(listed, list) and len(listed) >= 2
        assert any(t.get("name") == "echo" for t in listed)

        call = await async_client.post(
            f"/api/v1/mcp/tools/call?server_name={server_name}",
            headers=headers,
            json={"tool_name": "echo", "arguments": {"message": "api"}},
        )
        assert call.status_code == 200, call.text
        assert call.json().get("success") is True
        assert "api" in str(call.json().get("result"))
    finally:
        await async_client.delete(f"/api/v1/mcp/servers/{server_name}", headers=headers)


@pytest.mark.asyncio
async def test_mcp_client_stdio_command_not_found() -> None:
    cfg = MCPServer(
        name="bad_cmd",
        transport=MCPTransport.STDIO,
        command="/nonexistent/mcp_binary_xyz",
        args=[],
    )
    client = MCPClient(cfg)
    with pytest.raises(MCPConnectionError, match="not found|Command not found"):
        async with client.connect():
            pass


@pytest.mark.asyncio
async def test_mcp_client_http_connection_refused_raises() -> None:
    cfg = MCPServer(
        name="refused",
        transport=MCPTransport.HTTP,
        url="http://127.0.0.1:61234",
        timeout_sec=3,
    )
    client = MCPClient(cfg)
    with pytest.raises(MCPProtocolError):
        async with client.connect():
            pass
