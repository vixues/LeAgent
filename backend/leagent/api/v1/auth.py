"""Auth HTTP API: status, setup, login, logout, me, change-password."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from leagent.config.settings import get_settings
from leagent.services.auth.deps import CurrentPrincipal, CurrentUserId, UserPrincipal
from leagent.services.auth.policy import effective_enforce_auth, is_desktop_runtime, security_status_payload
from leagent.services.auth.service import LOCAL_USER_ID, get_auth_service
from leagent.services.auth.store import get_security_store
from leagent.services.auth.users import seed_admin_from_access_password

router = APIRouter()


class SetupRequest(BaseModel):
    password: str = Field(min_length=6, max_length=256)
    confirm_password: str | None = Field(default=None, max_length=256)
    require_unlock_on_desktop: bool = False


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    username: str | None = Field(default=None, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=6, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 0


class MeResponse(BaseModel):
    id: str
    username: str
    display_name: str
    email: str = ""
    role: str
    is_superuser: bool
    permissions: list[str]
    roles: list[str]
    default_workspace_id: str | None = None


def _client_is_loopback(request: Request) -> bool:
    client = request.client.host if request.client else ""
    return client in {"127.0.0.1", "::1", "localhost", "testclient"}


@router.get("/status")
async def auth_status() -> dict[str, Any]:
    """Public: whether auth is enforced and whether first-run setup is done."""
    return security_status_payload(get_settings())


@router.post("/setup", response_model=TokenResponse)
async def auth_setup(body: SetupRequest) -> TokenResponse:
    store = get_security_store()
    if store.is_setup_complete():
        raise HTTPException(status_code=409, detail="Access password already configured")
    if body.confirm_password is not None and body.confirm_password != body.password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    try:
        store.set_access_password(
            body.password,
            require_unlock_on_desktop=body.require_unlock_on_desktop,
        )
        try:
            seed_admin_from_access_password(body.password)
        except Exception:  # noqa: BLE001 - password gate still works without DB seed
            pass
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    svc = get_auth_service()
    pair = svc.create_token_pair(LOCAL_USER_ID, role="admin", username="admin")
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )


@router.post("/login", response_model=TokenResponse)
async def auth_login(body: LoginRequest) -> TokenResponse:
    store = get_security_store()
    if not store.is_setup_complete() and effective_enforce_auth(get_settings()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Setup required. Call POST /auth/setup first.",
        )
    svc = get_auth_service()
    try:
        if body.username:
            pair = svc.login_user(body.username, body.password)
        else:
            pair = svc.login_with_access_password(body.password)
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )


@router.post("/logout")
async def auth_logout(request: Request) -> dict[str, str]:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            get_auth_service().revoke_token(token)
    return {"status": "ok"}


@router.get("/me", response_model=MeResponse)
async def auth_me(
    principal: CurrentPrincipal,
) -> MeResponse:
    return MeResponse(
        id=str(principal.user_id),
        username=principal.username,
        display_name=principal.username,
        email=f"{principal.username}@localhost",
        role="admin" if principal.is_superuser else (next(iter(principal.roles), "user")),
        is_superuser=principal.is_superuser,
        permissions=sorted(principal.permissions),
        roles=sorted(principal.roles),
    )


@router.post("/change-password")
async def auth_change_password(
    body: ChangePasswordRequest,
    user_id: CurrentUserId,
    principal: CurrentPrincipal,
) -> dict[str, str]:
    store = get_security_store()
    # Instance access password change (admin / shared gate).
    if principal.is_superuser and store.is_setup_complete():
        try:
            store.change_access_password(body.current_password, body.new_password)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            seed_admin_from_access_password(body.new_password)
        except Exception:  # noqa: BLE001
            pass
        return {"status": "ok"}

    from leagent.services.auth.users import authenticate_user, set_user_password

    info = authenticate_user(principal.username, body.current_password)
    if info is None or info.user_id != user_id:
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    try:
        set_user_password(user_id, body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok"}


@router.post("/desktop-bootstrap", response_model=TokenResponse)
async def auth_desktop_bootstrap(request: Request) -> TokenResponse:
    """Mint a local session for the desktop Electron shell (loopback only)."""
    settings = get_settings()
    if not is_desktop_runtime(settings) and not _client_is_loopback(request):
        raise HTTPException(status_code=403, detail="Desktop bootstrap not allowed")
    if not _client_is_loopback(request):
        raise HTTPException(status_code=403, detail="Desktop bootstrap requires loopback")

    store = get_security_store()
    if store.load().require_unlock_on_desktop and store.is_setup_complete():
        raise HTTPException(
            status_code=401,
            detail="Desktop unlock required. Use /auth/login.",
        )

    svc = get_auth_service()
    # Ensure a signing secret exists even in passthrough mode.
    pair = svc.create_token_pair(LOCAL_USER_ID, role="admin", username="admin")
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
    )
