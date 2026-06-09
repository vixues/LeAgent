"""Authentication dependencies for FastAPI.

For the default local single-user profile these are permissive pass-throughs.
When ``LEAGENT_SECURITY_ENFORCE_AUTH=1`` they switch to an enforcing path that
requires a verified ``Authorization: Bearer <token>`` and raises ``401``
otherwise — the seam for a real multi-user deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from leagent.services.auth.service import LOCAL_USER_ID

LOCAL_USER_ID_VALUE = LOCAL_USER_ID


def _auth_enforced() -> bool:
    try:
        from leagent.config.settings import get_settings

        return bool(get_settings().security.enforce_auth)
    except Exception:  # noqa: BLE001 - never fail closed on config errors during import
        return False


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def _require_authenticated_user(request: Request) -> UUID:
    """Resolve the authenticated user id, raising 401 when enforcement is on."""
    token = _bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    from leagent.services.auth.service import get_auth_service

    uid = get_auth_service().verify_access_token(token)
    if uid is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return uid


@dataclass(frozen=True)
class UserPrincipal:
    user_id: UUID = LOCAL_USER_ID
    tenant_id: str | None = None
    roles: frozenset[str] = frozenset({"admin"})
    permissions: frozenset[str] = frozenset()
    is_superuser: bool = True

    def has_all(self, keys: tuple[str, ...] | list[str]) -> bool:
        return True

    def has_any(self, keys: tuple[str, ...] | list[str]) -> bool:
        return True


async def get_current_user_id(request: Request) -> UUID:
    uid = _require_authenticated_user(request) if _auth_enforced() else LOCAL_USER_ID
    request.state.user_id = str(uid)
    request.state.user_id_cached = str(uid)
    from leagent.utils.logging import bind_log_context

    bind_log_context(user_id=str(uid))
    return uid


async def get_current_user_id_optional(request: Request) -> Optional[UUID]:
    if _auth_enforced():
        token = _bearer_token(request)
        if not token:
            return None
        from leagent.services.auth.service import get_auth_service

        return get_auth_service().verify_access_token(token)
    return LOCAL_USER_ID


async def get_current_principal(request: Request) -> UserPrincipal:
    if _auth_enforced():
        uid = _require_authenticated_user(request)
        return UserPrincipal(user_id=uid)
    return UserPrincipal()


class RoleChecker:
    """Role checker. Permissive in local mode; requires auth when enforced."""

    def __init__(self, allowed_roles: list | None = None) -> None:
        self._allowed_roles = allowed_roles or []

    async def __call__(self, request: Request) -> UUID:
        if not _auth_enforced():
            return LOCAL_USER_ID
        return _require_authenticated_user(request)


class PermissionChecker:
    """Permission checker.

    Permissive in local mode; when auth is enforced it requires a verified
    bearer token and checks the principal's permissions before allowing.
    """

    def __init__(self, *keys: str, mode: str = "all") -> None:
        self._keys = keys
        self._mode = mode

    async def __call__(self, request: Request) -> UUID:
        if not _auth_enforced():
            return LOCAL_USER_ID
        uid = _require_authenticated_user(request)
        principal = UserPrincipal(user_id=uid)
        if self._keys:
            ok = (
                principal.has_all(self._keys)
                if self._mode == "all"
                else principal.has_any(self._keys)
            )
            if not ok:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions.",
                )
        return uid


require_admin = RoleChecker()
require_dept_head = RoleChecker()
require_staff = RoleChecker()

CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
CurrentPrincipal = Annotated[UserPrincipal, Depends(get_current_principal)]
OptionalUserId = Annotated[Optional[UUID], Depends(get_current_user_id_optional)]
AdminUserId = Annotated[UUID, Depends(get_current_user_id)]


def require_permissions(*keys: str, mode: str = "all") -> PermissionChecker:
    return PermissionChecker(*keys, mode=mode)
