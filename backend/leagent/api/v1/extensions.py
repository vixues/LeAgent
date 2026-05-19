"""REST API for official extension packs (plugin marketplace)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from leagent.extensions.manager import ExtensionManager
from leagent.services.auth.deps import get_current_principal, require_permissions

router = APIRouter()


def get_extension_manager() -> ExtensionManager:
    return ExtensionManager()


class InstallBody(BaseModel):
    pack_id: str = Field(..., min_length=1, description="Official pack id from the registry")


@router.get("")
async def list_extensions(
    _: Annotated[Any, Depends(get_current_principal)],
    mgr: Annotated[ExtensionManager, Depends(get_extension_manager)],
) -> dict[str, Any]:
    """Any authenticated user may browse packs; install/delete require ``admin:panel``."""
    return {"packs": mgr.list_packs()}


@router.post(
    "/install",
    dependencies=[Depends(require_permissions("admin:panel"))],
)
async def install_extension(
    body: InstallBody,
    mgr: Annotated[ExtensionManager, Depends(get_extension_manager)],
) -> dict[str, Any]:
    try:
        return mgr.install_pack(body.pack_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e


@router.delete(
    "/{pack_id}",
    dependencies=[Depends(require_permissions("admin:panel"))],
)
async def uninstall_extension(
    pack_id: str,
    mgr: Annotated[ExtensionManager, Depends(get_extension_manager)],
) -> dict[str, Any]:
    try:
        return mgr.uninstall_pack(pack_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
