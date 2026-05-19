"""Stub auth service for standalone local deployment"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

LOCAL_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@dataclass
class TokenPayload:
    sub: str = str(LOCAL_USER_ID)
    type: str = "access"


@dataclass
class TokenPair:
    access_token: str = "local-token"
    refresh_token: str = "local-refresh"
    token_type: str = "bearer"


class AuthService:
    """No-op auth service for local single-user deployment."""

    def __init__(self, _settings: object | None = None) -> None:
        """Accept optional settings for API compatibility with tests and callers."""

    def verify_access_token(self, _token: str) -> UUID | None:
        return LOCAL_USER_ID

    def create_access_token(self, _user_id: UUID, **_kw: object) -> str:
        return "local-token"

    def create_refresh_token(self, _user_id: UUID, **_kw: object) -> str:
        return "local-refresh"

    def create_token_pair(self, _user_id: UUID, **_kw: object) -> TokenPair:
        return TokenPair()

    def hash_password(self, _password: str) -> str:
        return ""

    def verify_password(self, _plain: str, _hashed: str) -> bool:
        return True


_auth_service: AuthService | None = None


def init_auth_service(_settings: object = None) -> AuthService:
    global _auth_service
    _auth_service = AuthService()
    return _auth_service


def get_auth_service() -> AuthService:
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
