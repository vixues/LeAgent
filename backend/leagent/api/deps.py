"""FastAPI dependencies — local no-auth passthrough with typed injection.

Request dependencies resolve the running services from ``request.app.state``
(populated in :mod:`leagent.main` lifespan), falling back to the module-global
accessor for non-lifespan contexts (scripts, some tests). Concrete return types
plus the ``*Dep`` ``Annotated`` aliases let route handlers declare typed
parameters instead of reaching for ``Any``.
"""

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
    from leagent.db.service import DatabaseService
    from leagent.file.service import FileService
    from leagent.services.service_manager import ServiceManager


def get_settings() -> Settings:
    return _get_settings()


def get_service_manager(request: Request) -> "ServiceManager":
    """Return the process-wide :class:`ServiceManager`.

    Prefers ``request.app.state.service_manager`` (set during lifespan startup);
    falls back to the module-global accessor so dependency resolution still works
    in contexts that never ran the lifespan.
    """
    sm = getattr(request.app.state, "service_manager", None)
    if sm is not None:
        return sm
    from leagent.main import get_service_manager as _gsm

    return _gsm()


def get_db_service(
    sm: Annotated["ServiceManager", Depends(get_service_manager)],
) -> "DatabaseService":
    return sm.db


def get_file_service(
    sm: Annotated["ServiceManager", Depends(get_service_manager)],
) -> "FileService":
    """Return the process-wide :class:`FileService` (single managed-blob ingress)."""
    fs = sm.file_service
    if fs is None:
        from fastapi import HTTPException, status as _status

        raise HTTPException(
            status_code=_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File service is unavailable.",
        )
    return fs


def get_auth_service(
    sm: Annotated["ServiceManager", Depends(get_service_manager)],
) -> Any:
    return sm.auth


# ---------------------------------------------------------------------------
# Annotated dependency aliases — declare typed handler params, e.g.
#   async def handler(db: DbDep) -> ...:
# ---------------------------------------------------------------------------

SettingsDep = Annotated[Settings, Depends(get_settings)]
ServiceManagerDep = Annotated["ServiceManager", Depends(get_service_manager)]
DbDep = Annotated["DatabaseService", Depends(get_db_service)]
FileServiceDep = Annotated["FileService", Depends(get_file_service)]


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
    "get_file_service",
    "get_auth_service",
    "SettingsDep",
    "ServiceManagerDep",
    "DbDep",
    "FileServiceDep",
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
