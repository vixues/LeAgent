"""FastAPI dependency shim — local no-auth passthrough."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Request

from leagent.config.settings import Settings
from leagent.config.settings import get_settings as _get_settings
from leagent.services.auth.deps import (  # noqa: F401 -- re-export
    CurrentPrincipal,
    CurrentUserId,
    PermissionChecker,
    get_current_principal,
    get_current_user_id,
    require_permissions,
)
from leagent.services.auth.service import LOCAL_USER_ID

if TYPE_CHECKING:
    from leagent.services.service_manager import ServiceManager


def get_settings() -> Settings:
    return _get_settings()


def get_service_manager(request: Request) -> "ServiceManager":
    from leagent.main import get_service_manager as _gsm
    return _gsm()


def get_db_service(
    sm: Annotated[Any, Depends(get_service_manager)],
) -> Any:
    return sm.db


def get_auth_service(
    sm: Annotated[Any, Depends(get_service_manager)],
) -> Any:
    return sm.auth


def require_admin(*_, **__):
    return require_permissions("admin:panel")


def require_permission(permission: str):
    return require_permissions(permission)


async def get_current_user(**_kw: object) -> dict[str, Any]:
    return {
        "user_id": str(LOCAL_USER_ID),
        "username": "local",
        "role": "admin",
        "roles": ["admin"],
        "permissions": [],
        "is_superuser": True,
        "tenant_id": None,
    }


async def get_current_active_user(**_kw: object) -> dict[str, Any]:
    return await get_current_user()


__all__ = [
    "get_settings",
    "get_service_manager",
    "get_db_service",
    "get_auth_service",
    "get_current_user",
    "get_current_active_user",
    "get_current_user_id",
    "get_current_principal",
    "require_admin",
    "require_permission",
    "require_permissions",
    "PermissionChecker",
    "CurrentUserId",
    "CurrentPrincipal",
]
