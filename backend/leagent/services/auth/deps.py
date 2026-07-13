"""Authentication dependencies for FastAPI.

When auth is not enforced (loopback / desktop / explicit off) these are
permissive pass-throughs. When enforced they require a verified Bearer token
and apply real RBAC on :class:`UserPrincipal`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from leagent.services.auth.service import LOCAL_USER_ID

LOCAL_USER_ID_VALUE = LOCAL_USER_ID

_ADMIN_PERMISSIONS = frozenset(
    {
        "*",
        "admin:panel",
        "admin:users",
        "admin:tasks",
        "admin:providers",
        "workflow:admin",
    }
)


def _auth_enforced() -> bool:
    try:
        from leagent.services.auth.policy import effective_enforce_auth
        from leagent.config.settings import get_settings

        return effective_enforce_auth(get_settings())
    except Exception:  # noqa: BLE001
        return False


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def _principal_from_token(token: str) -> "UserPrincipal":
    from leagent.services.auth.service import get_auth_service

    svc = get_auth_service()
    payload = svc.decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    uid = UUID(payload.sub)
    role = payload.role or "user"
    is_admin = role == "admin" or uid == LOCAL_USER_ID
    roles = frozenset({"admin"} if is_admin else {role})
    perms = _ADMIN_PERMISSIONS if is_admin else frozenset()
    return UserPrincipal(
        user_id=uid,
        roles=roles,
        permissions=perms,
        is_superuser=is_admin,
        username=payload.username or ("admin" if is_admin else "user"),
    )


def _require_authenticated_user(request: Request) -> UUID:
    token = _bearer_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _principal_from_token(token).user_id


@dataclass(frozen=True)
class UserPrincipal:
    user_id: UUID = LOCAL_USER_ID
    tenant_id: str | None = None
    roles: frozenset[str] = frozenset({"admin"})
    permissions: frozenset[str] = frozenset()
    is_superuser: bool = True
    username: str = "local"

    def has_all(self, keys: tuple[str, ...] | list[str]) -> bool:
        if self.is_superuser or "*" in self.permissions:
            return True
        if not keys:
            return True
        return all(k in self.permissions or k in self.roles for k in keys)

    def has_any(self, keys: tuple[str, ...] | list[str]) -> bool:
        if self.is_superuser or "*" in self.permissions:
            return True
        if not keys:
            return True
        return any(k in self.permissions or k in self.roles for k in keys)


async def get_current_user_id(request: Request) -> UUID:
    if _auth_enforced():
        uid = _require_authenticated_user(request)
    else:
        token = _bearer_token(request)
        if token:
            from leagent.services.auth.service import get_auth_service

            uid = get_auth_service().verify_access_token(token) or LOCAL_USER_ID
        else:
            uid = LOCAL_USER_ID
    request.state.user_id = str(uid)
    request.state.user_id_cached = str(uid)
    from leagent.utils.logging import bind_log_context

    bind_log_context(user_id=str(uid))
    return uid


async def get_current_user_id_optional(request: Request) -> Optional[UUID]:
    token = _bearer_token(request)
    if _auth_enforced():
        if not token:
            return None
        from leagent.services.auth.service import get_auth_service

        return get_auth_service().verify_access_token(token)
    if token:
        from leagent.services.auth.service import get_auth_service

        return get_auth_service().verify_access_token(token) or LOCAL_USER_ID
    return LOCAL_USER_ID


async def get_current_principal(request: Request) -> UserPrincipal:
    if _auth_enforced():
        token = _bearer_token(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _principal_from_token(token)
    token = _bearer_token(request)
    if token:
        try:
            return _principal_from_token(token)
        except HTTPException:
            return UserPrincipal()
    return UserPrincipal()


class RoleChecker:
    """Require auth (when enforced) and optional role membership."""

    def __init__(self, allowed_roles: list | None = None) -> None:
        self._allowed_roles = [r.lower() for r in (allowed_roles or [])]

    async def __call__(self, request: Request) -> UUID:
        if not _auth_enforced():
            return LOCAL_USER_ID
        token = _bearer_token(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        principal = _principal_from_token(token)
        if self._allowed_roles and not principal.is_superuser:
            if not any(r in principal.roles for r in self._allowed_roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient role.",
                )
        return principal.user_id


class PermissionChecker:
    """Permission checker with real RBAC when auth is enforced."""

    def __init__(self, *keys: str, mode: str = "all") -> None:
        self._keys = keys
        self._mode = mode

    async def __call__(self, request: Request) -> UUID:
        if not _auth_enforced():
            return LOCAL_USER_ID
        token = _bearer_token(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        principal = _principal_from_token(token)
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
        return principal.user_id


require_admin = RoleChecker(["admin"])
require_dept_head = RoleChecker(["admin"])
require_staff = RoleChecker(["admin", "user"])

CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
CurrentPrincipal = Annotated[UserPrincipal, Depends(get_current_principal)]
OptionalUserId = Annotated[Optional[UUID], Depends(get_current_user_id_optional)]
AdminUserId = Annotated[UUID, Depends(require_admin)]


def require_permissions(*keys: str, mode: str = "all") -> PermissionChecker:
    return PermissionChecker(*keys, mode=mode)
