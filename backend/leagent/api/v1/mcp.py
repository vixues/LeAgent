"""MCP server management API endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from leagent.mcp.base import MCPServer, MCPTransport
from leagent.mcp.manager import MCPClientManager, ServerHealth, get_mcp_manager
from leagent.services.auth import CurrentUserId

router = APIRouter()


class MCPServerInfo(BaseModel):
    """MCP server information."""

    name: str
    transport: str
    enabled: bool
    auto_connect: bool
    connected: bool
    tool_count: int
    prompt_count: int
    resource_count: int


class MCPServerDetail(BaseModel):
    """Detailed MCP server information."""

    name: str
    transport: str
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    url: Optional[str] = None
    enabled: bool
    auto_connect: bool
    description: Optional[str] = None
    health: dict[str, Any]
    tools: list[dict[str, Any]]
    prompts: list[dict[str, Any]]
    resources: list[dict[str, Any]]


class MCPServerCreateRequest(BaseModel):
    """Request schema for adding an MCP server."""

    name: str = Field(..., min_length=1, max_length=100)
    transport: MCPTransport = Field(default=MCPTransport.STDIO)
    command: Optional[str] = Field(default=None, max_length=500)
    args: list[str] = Field(default_factory=list)
    url: Optional[str] = Field(default=None, max_length=500)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = Field(default=True)
    auto_connect: bool = Field(default=True)
    description: Optional[str] = Field(default=None, max_length=500)


class MCPToolCallRequest(BaseModel):
    """Request schema for calling an MCP tool."""

    tool_name: str = Field(..., min_length=1, max_length=200)
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallResponse(BaseModel):
    """Response schema for MCP tool call."""

    server_name: str
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    latency_ms: int = 0


class MCPHealthResponse(BaseModel):
    """Health status for all MCP servers."""

    servers: dict[str, dict[str, Any]]
    connected_count: int
    total_count: int


def get_manager() -> MCPClientManager:
    """Dependency to get the MCP client manager."""
    return get_mcp_manager()


@router.get("/servers", response_model=list[MCPServerInfo])
async def list_servers(
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
) -> list[MCPServerInfo]:
    """List all configured MCP servers."""
    result = []

    for name in manager.server_names:
        client = manager.get_client(name)
        tools = manager.list_server_tools(name)

        managed = manager._clients.get(name)
        if managed:
            result.append(
                MCPServerInfo(
                    name=name,
                    transport=managed.config.transport.value,
                    enabled=managed.config.enabled,
                    auto_connect=managed.config.auto_connect,
                    connected=client is not None,
                    tool_count=len(tools),
                    prompt_count=len(managed.prompts),
                    resource_count=len(managed.resources),
                )
            )

    return result


@router.post("/servers", response_model=MCPServerInfo, status_code=status.HTTP_201_CREATED)
async def add_server(
    data: MCPServerCreateRequest,
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
) -> MCPServerInfo:
    """Add a new MCP server configuration."""
    if data.name in manager.server_names:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Server '{data.name}' already exists",
        )

    config = MCPServer(
        name=data.name,
        transport=data.transport,
        command=data.command,
        args=data.args,
        url=data.url,
        env=data.env,
        enabled=data.enabled,
        auto_connect=data.auto_connect,
        description=data.description,
    )

    manager.add_server(config)

    return MCPServerInfo(
        name=data.name,
        transport=data.transport.value,
        enabled=data.enabled,
        auto_connect=data.auto_connect,
        connected=False,
        tool_count=0,
        prompt_count=0,
        resource_count=0,
    )


@router.get("/servers/{server_name}", response_model=MCPServerDetail)
async def get_server(
    server_name: str,
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
) -> MCPServerDetail:
    """Get detailed information about an MCP server."""
    if server_name not in manager.server_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_name}' not found",
        )

    managed = manager._clients.get(server_name)
    if not managed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_name}' not found",
        )

    health = managed.health.to_dict()

    return MCPServerDetail(
        name=server_name,
        transport=managed.config.transport.value,
        command=managed.config.command,
        args=managed.config.args,
        url=managed.config.url,
        enabled=managed.config.enabled,
        auto_connect=managed.config.auto_connect,
        description=managed.config.description,
        health=health,
        tools=[t.to_dict() for t in managed.tools],
        prompts=[p.to_dict() for p in managed.prompts],
        resources=[r.to_dict() for r in managed.resources],
    )


@router.delete("/servers/{server_name}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_server(
    server_name: str,
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
) -> None:
    """Remove an MCP server configuration."""
    if not manager.remove_server(server_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_name}' not found",
        )


@router.post("/servers/{server_name}/connect")
async def connect_server(
    server_name: str,
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
) -> dict[str, Any]:
    """Connect to an MCP server."""
    if server_name not in manager.server_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_name}' not found",
        )

    success = await manager.connect_server(server_name)

    return {
        "server_name": server_name,
        "connected": success,
        "message": "Connected successfully" if success else "Connection failed",
    }


@router.post("/servers/{server_name}/disconnect")
async def disconnect_server(
    server_name: str,
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
) -> dict[str, Any]:
    """Disconnect from an MCP server."""
    if server_name not in manager.server_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_name}' not found",
        )

    await manager._disconnect_server(server_name)

    return {
        "server_name": server_name,
        "connected": False,
        "message": "Disconnected successfully",
    }


@router.get("/tools", response_model=list[dict[str, Any]])
async def list_all_tools(
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
    server_name: Optional[str] = Query(default=None),
) -> list[dict[str, Any]]:
    """List all available MCP tools."""
    if server_name:
        tools = manager.list_server_tools(server_name)
    else:
        tools = manager.list_all_tools()

    return [t.to_dict() for t in tools]


@router.post("/tools/call", response_model=MCPToolCallResponse)
async def call_tool(
    server_name: str,
    data: MCPToolCallRequest,
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
) -> MCPToolCallResponse:
    """Call an MCP tool on a specific server."""
    import time

    if server_name not in manager.server_names:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Server '{server_name}' not found",
        )

    start_time = time.time()

    try:
        result = await manager.call_tool(server_name, data.tool_name, data.arguments)
        latency_ms = int((time.time() - start_time) * 1000)

        return MCPToolCallResponse(
            server_name=server_name,
            tool_name=data.tool_name,
            success=True,
            result=result,
            latency_ms=latency_ms,
        )

    except ValueError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return MCPToolCallResponse(
            server_name=server_name,
            tool_name=data.tool_name,
            success=False,
            error=str(e),
            latency_ms=latency_ms,
        )

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        return MCPToolCallResponse(
            server_name=server_name,
            tool_name=data.tool_name,
            success=False,
            error=str(e),
            latency_ms=latency_ms,
        )


@router.get("/health", response_model=MCPHealthResponse)
async def get_health(
    user_id: CurrentUserId,
    manager: Annotated[MCPClientManager, Depends(get_manager)],
) -> MCPHealthResponse:
    """Get health status of all MCP servers."""
    all_health = manager.get_all_health()

    return MCPHealthResponse(
        servers={name: h.to_dict() for name, h in all_health.items()},
        connected_count=len(manager.connected_servers),
        total_count=len(manager.server_names),
    )
