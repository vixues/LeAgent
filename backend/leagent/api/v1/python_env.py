"""REST API for managing the backend Python environment (uv project / pip)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from leagent.services.auth.deps import get_current_principal, require_permissions
from leagent.services.python_env.manager import PythonEnvManager

router = APIRouter()


def get_python_env_manager() -> PythonEnvManager:
    return PythonEnvManager()


class InstallBody(BaseModel):
    spec: str = Field(..., min_length=1, description="Package requirement (e.g. numpy, pandas==2.2)")


class UninstallBody(BaseModel):
    package: str = Field(..., min_length=1, description="Distribution name to uninstall")


class UpgradeBody(BaseModel):
    package: str = Field(..., min_length=1, description="Distribution name to upgrade")


@router.get("/info")
async def python_env_info(
    _: Annotated[Any, Depends(get_current_principal)],
    mgr: Annotated[PythonEnvManager, Depends(get_python_env_manager)],
) -> dict[str, Any]:
    return mgr.info()


@router.get("/packages")
async def list_packages(
    _: Annotated[Any, Depends(get_current_principal)],
    mgr: Annotated[PythonEnvManager, Depends(get_python_env_manager)],
) -> dict[str, Any]:
    try:
        direct = mgr.direct_dependencies()
        packages = mgr.list_packages()
        direct_set = {n.lower().replace("-", "_").replace(".", "_") for n in direct}
        if direct_set:
            for pkg in packages:
                norm = pkg["name"].lower().replace("-", "_").replace(".", "_")
                if norm in direct_set:
                    pkg["is_direct"] = True
        return {"packages": packages, "direct_dependencies": direct}
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.get("/outdated")
async def list_outdated(
    _: Annotated[Any, Depends(get_current_principal)],
    mgr: Annotated[PythonEnvManager, Depends(get_python_env_manager)],
) -> dict[str, Any]:
    try:
        return {"packages": mgr.list_outdated()}
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post(
    "/install",
    dependencies=[Depends(require_permissions("admin:panel"))],
)
async def install_package(
    body: InstallBody,
    mgr: Annotated[PythonEnvManager, Depends(get_python_env_manager)],
) -> dict[str, Any]:
    try:
        return mgr.install(body.spec)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post(
    "/uninstall",
    dependencies=[Depends(require_permissions("admin:panel"))],
)
async def uninstall_package(
    body: UninstallBody,
    mgr: Annotated[PythonEnvManager, Depends(get_python_env_manager)],
) -> dict[str, Any]:
    try:
        return mgr.uninstall(body.package)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post(
    "/upgrade",
    dependencies=[Depends(require_permissions("admin:panel"))],
)
async def upgrade_package(
    body: UpgradeBody,
    mgr: Annotated[PythonEnvManager, Depends(get_python_env_manager)],
) -> dict[str, Any]:
    try:
        return mgr.upgrade(body.package)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.post(
    "/sync",
    dependencies=[Depends(require_permissions("admin:panel"))],
)
async def sync_env(
    mgr: Annotated[PythonEnvManager, Depends(get_python_env_manager)],
) -> dict[str, Any]:
    try:
        return mgr.sync()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.get("/tree")
async def dep_tree(
    _: Annotated[Any, Depends(get_current_principal)],
    mgr: Annotated[PythonEnvManager, Depends(get_python_env_manager)],
) -> dict[str, Any]:
    try:
        return mgr.tree()
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e
