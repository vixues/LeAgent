"""Tool registry API endpoints."""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from leagent.services.auth import CurrentUserId
from leagent.tools.base import ToolCategory
from leagent.tools.registry import ToolNotFoundError, ToolRegistry, get_registry

router = APIRouter()


class ToolInfo(BaseModel):
    """Tool information response."""

    name: str
    description: str
    category: str
    version: str
    timeout_sec: int
    max_retries: int
    requires_gpu: bool


class ToolDetailResponse(BaseModel):
    """Detailed tool information with parameters."""

    name: str
    description: str
    category: str
    version: str
    timeout_sec: int
    max_retries: int
    requires_gpu: bool
    parameters: dict[str, Any]


class ToolListResponse(BaseModel):
    """Response for tool listing."""

    tools: list[ToolInfo]
    total: int
    categories: dict[str, int]


def get_tool_registry() -> ToolRegistry:
    """Dependency to get the tool registry."""
    return get_registry()


@router.get("", response_model=ToolListResponse)
async def list_tools(
    user_id: CurrentUserId,
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
    category: Optional[ToolCategory] = Query(default=None),
    search: Optional[str] = Query(default=None, max_length=100),
) -> ToolListResponse:
    """List all available tools with optional filtering."""
    if category:
        tools = registry.list_by_category(category)
    else:
        tools = registry.list_all()

    if search:
        search_lower = search.lower()
        tools = [
            t for t in tools
            if search_lower in t.name.lower() or search_lower in t.description.lower()
        ]

    tool_infos = [
        ToolInfo(
            name=t.name,
            description=t.description,
            category=t.category.value,
            version=t.version,
            timeout_sec=t.timeout_sec,
            max_retries=t.max_retries,
            requires_gpu=t.requires_gpu,
        )
        for t in tools
    ]

    categories = {cat.value: count for cat, count in registry.get_categories().items()}

    return ToolListResponse(
        tools=tool_infos,
        total=len(tool_infos),
        categories=categories,
    )


@router.get("/{tool_name}", response_model=ToolDetailResponse)
async def get_tool(
    tool_name: str,
    user_id: CurrentUserId,
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> ToolDetailResponse:
    """Get detailed information about a specific tool."""
    try:
        tool = registry.get(tool_name)
    except ToolNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found",
        )

    return ToolDetailResponse(
        name=tool.name,
        description=tool.description,
        category=tool.category.value,
        version=tool.version,
        timeout_sec=tool.timeout_sec,
        max_retries=tool.max_retries,
        requires_gpu=tool.requires_gpu,
        parameters=tool.parameters,
    )


@router.get("/{tool_name}/schema", response_model=dict[str, Any])
async def get_tool_schema(
    tool_name: str,
    user_id: CurrentUserId,
    registry: Annotated[ToolRegistry, Depends(get_tool_registry)],
) -> dict[str, Any]:
    """Get OpenAI function-calling schema for a tool."""
    try:
        tool = registry.get(tool_name)
    except ToolNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found",
        )

    return tool.to_openai_schema()
