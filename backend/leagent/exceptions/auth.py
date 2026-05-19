"""Authentication and authorization exceptions."""

from __future__ import annotations

from leagent.exceptions.base import LeAgentError


class AuthenticationError(LeAgentError):
    """Authentication failed (invalid or missing credentials)."""

    error_code = "AUTHENTICATION_ERROR"
    status_code = 401

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message)


class AuthorizationError(LeAgentError):
    """User is authenticated but not authorized for this action."""

    error_code = "AUTHORIZATION_ERROR"
    status_code = 403

    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(message)


class InsufficientPermissionsError(AuthorizationError):
    """User lacks the specific permission required."""

    error_code = "INSUFFICIENT_PERMISSIONS"

    def __init__(
        self,
        required_permission: str,
        user_role: str = "",
    ) -> None:
        super().__init__(
            f"Permission '{required_permission}' required (current role: {user_role or 'unknown'})"
        )
        self.details = {
            "required_permission": required_permission,
            "user_role": user_role,
        }


class TokenExpiredError(AuthenticationError):
    """JWT token has expired."""

    error_code = "TOKEN_EXPIRED"

    def __init__(self) -> None:
        super().__init__("Token has expired")


class InvalidTokenError(AuthenticationError):
    """JWT token is malformed or invalid."""

    error_code = "INVALID_TOKEN"

    def __init__(self) -> None:
        super().__init__("Invalid token")
