"""Base exception hierarchy for LeAgent."""

from __future__ import annotations

from typing import Any


class LeAgentError(Exception):
    """Root exception for all LeAgent errors.

    Attributes:
        error_code: Machine-readable error code (e.g. ``TOOL_EXEC_FAILED``).
        message: Human-readable description.
        details: Arbitrary structured data for debugging.
        status_code: Suggested HTTP status code when surfaced via API.
    """

    error_code: str = "LEAGENT_ERROR"
    status_code: int = 500

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        *,
        error_code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(error_code={self.error_code!r}, message={self.message!r})"


class ValidationError(LeAgentError):
    """Input or output validation failure."""

    error_code = "VALIDATION_ERROR"
    status_code = 422


class ConfigurationError(LeAgentError):
    """Invalid or missing configuration."""

    error_code = "CONFIGURATION_ERROR"
    status_code = 500


class ResourceNotFoundError(LeAgentError):
    """Requested resource does not exist."""

    error_code = "RESOURCE_NOT_FOUND"
    status_code = 404


class ResourceConflictError(LeAgentError):
    """Resource already exists or state conflict."""

    error_code = "RESOURCE_CONFLICT"
    status_code = 409
