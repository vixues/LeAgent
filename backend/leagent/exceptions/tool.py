"""Tool-related exceptions."""

from __future__ import annotations

from typing import Any

from leagent.exceptions.base import LeAgentError


class ToolExecutionError(LeAgentError):
    """A tool failed after exhausting retries."""

    error_code = "TOOL_EXEC_FAILED"
    status_code = 500

    def __init__(
        self,
        message: str = "Tool execution failed",
        *,
        tool_name: str = "",
        params: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {**(details or {}), "tool_name": tool_name, "params": params}
        super().__init__(message, details=merged)
        self.tool_name = tool_name
        self.params = params or {}


class ToolNotFoundError(LeAgentError):
    """Requested tool is not registered in the tool registry."""

    error_code = "TOOL_NOT_FOUND"
    status_code = 404

    def __init__(self, tool_name: str) -> None:
        super().__init__(
            f"Tool '{tool_name}' not found in registry",
            details={"tool_name": tool_name},
        )
        self.tool_name = tool_name


class ToolValidationError(LeAgentError):
    """Tool parameter validation failed."""

    error_code = "TOOL_VALIDATION_ERROR"
    status_code = 422

    def __init__(
        self,
        message: str = "Tool parameter validation failed",
        *,
        tool_name: str = "",
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(
            message,
            details={"tool_name": tool_name, "validation_errors": errors or []},
        )
        self.tool_name = tool_name
        self.errors = errors or []


class ToolTimeoutError(LeAgentError):
    """Tool execution exceeded the allowed timeout."""

    error_code = "TOOL_TIMEOUT"
    status_code = 504

    def __init__(self, tool_name: str, timeout_sec: int) -> None:
        super().__init__(
            f"Tool '{tool_name}' timed out after {timeout_sec}s",
            details={"tool_name": tool_name, "timeout_sec": timeout_sec},
        )
