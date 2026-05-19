"""Tools package — agent tool implementations.

This module provides the core tool framework for LeAgent including:
- Base tool abstractions and result types
- Tool registry for discovery and management
- Tool executor for parallel and sequential execution

Example:
    >>> from leagent.tools import BaseTool, ToolContext, ToolResult
    >>> from leagent.tools import get_registry, get_executor
    >>>
    >>> # Register a custom tool
    >>> registry = get_registry()
    >>> registry.register(MyCustomTool())
    >>>
    >>> # Execute tools
    >>> executor = get_executor()
    >>> result = await executor.execute("my_tool", params, context)
"""

from leagent.tools.base import (
    BaseTool,
    SyncTool,
    ToolCapability,
    ToolCategory,
    ToolContext,
    ToolProgressEvent,
    ToolResult,
)
from leagent.tools.executor import (
    AggregatedResult,
    ExecutionResult,
    ToolCall,
    ToolExecutionError,
    ToolExecutor,
    get_executor,
    reset_executor,
)
from leagent.tools.registry import (
    ToolNotFoundError,
    ToolRegistrationError,
    ToolRegistry,
    get_registry,
    reset_registry,
)

__all__ = [
    # Base classes and types
    "BaseTool",
    "SyncTool",
    "ToolCapability",
    "ToolCategory",
    "ToolContext",
    "ToolProgressEvent",
    "ToolResult",
    # Registry
    "ToolRegistry",
    "ToolNotFoundError",
    "ToolRegistrationError",
    "get_registry",
    "reset_registry",
    # Executor
    "ToolExecutor",
    "ToolCall",
    "ExecutionResult",
    "AggregatedResult",
    "ToolExecutionError",
    "get_executor",
    "reset_executor",
]
