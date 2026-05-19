"""Authentication dependencies for FastAPI — passthrough for single-user execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Optional
from uuid import UUID

from fastapi import Depends, Request

from leagent.services.auth.service import LOCAL_USER_ID

LOCAL_USER_ID_VALUE = LOCAL_USER_ID


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
    request.state.user_id = str(LOCAL_USER_ID)
    request.state.user_id_cached = str(LOCAL_USER_ID)
    return LOCAL_USER_ID


async def get_current_user_id_optional(request: Request) -> Optional[UUID]:
    return LOCAL_USER_ID


async def get_current_principal(request: Request) -> UserPrincipal:
    return UserPrincipal()


class RoleChecker:
    """No-op role checker — always allows."""

    def __init__(self, allowed_roles: list | None = None) -> None:
        pass

    async def __call__(self, request: Request) -> UUID:
        return LOCAL_USER_ID


class PermissionChecker:
    """No-op permission checker — always allows."""

    def __init__(self, *keys: str, mode: str = "all") -> None:
        pass

    async def __call__(self, request: Request) -> UUID:
        return LOCAL_USER_ID


require_admin = RoleChecker()
require_dept_head = RoleChecker()
require_staff = RoleChecker()

CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
CurrentPrincipal = Annotated[UserPrincipal, Depends(get_current_principal)]
OptionalUserId = Annotated[Optional[UUID], Depends(get_current_user_id_optional)]
AdminUserId = Annotated[UUID, Depends(get_current_user_id)]


def require_permissions(*keys: str, mode: str = "all") -> PermissionChecker:
    return PermissionChecker(*keys, mode=mode)
