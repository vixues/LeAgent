"""Admin user management API."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from leagent.services.auth.deps import AdminUserId
from leagent.services.auth.users import (
    create_user,
    list_users,
    set_user_disabled,
    set_user_password,
)

router = APIRouter()


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=6, max_length=256)
    display_name: str | None = Field(default=None, max_length=256)
    role: str = Field(default="user", max_length=32)


class ResetPasswordRequest(BaseModel):
    password: str = Field(min_length=6, max_length=256)


class DisableUserRequest(BaseModel):
    disabled: bool = True


@router.get("")
async def admin_list_users(_admin: AdminUserId) -> list[dict[str, Any]]:
    return [u.to_api() for u in list_users()]


@router.post("", status_code=201)
async def admin_create_user(body: CreateUserRequest, _admin: AdminUserId) -> dict[str, Any]:
    try:
        user = create_user(
            username=body.username,
            password=body.password,
            display_name=body.display_name,
            role=body.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return user.to_api()


@router.post("/{user_id}/reset-password")
async def admin_reset_password(
    user_id: UUID,
    body: ResetPasswordRequest,
    _admin: AdminUserId,
) -> dict[str, str]:
    try:
        set_user_password(user_id, body.password)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.patch("/{user_id}")
async def admin_patch_user(
    user_id: UUID,
    body: DisableUserRequest,
    _admin: AdminUserId,
) -> dict[str, Any]:
    try:
        user = set_user_disabled(user_id, body.disabled)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user.to_api()
