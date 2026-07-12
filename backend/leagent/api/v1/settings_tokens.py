"""Read/write allowlisted API tokens via ``~/.leagent/.env`` (desktop secrets).

GET returns only whether each key is non-empty — never the secret value.
Writes go through :mod:`leagent.services.settings_configure`.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from leagent.services.auth.deps import get_current_principal
from leagent.services.settings_configure import (
    ALLOWED_ENV_KEYS,
    SettingsConfigureError,
    apply_env_changes,
    is_env_set,
)

router = APIRouter()

# Re-export for tests / callers that imported from this module.
__all__ = [
    "ALLOWED_ENV_KEYS",
    "TokenKeyStatus",
    "TokensStatusResponse",
    "TokensUpdateBody",
    "router",
]


class TokenKeyStatus(BaseModel):
    env_key: str
    set: bool


class TokensStatusResponse(BaseModel):
    keys: list[TokenKeyStatus]


class TokensUpdateBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


@router.get("/tokens", response_model=TokensStatusResponse)
async def get_tokens_status(_: Annotated[Any, Depends(get_current_principal)]) -> TokensStatusResponse:
    keys = [TokenKeyStatus(env_key=k, set=is_env_set(k)) for k in ALLOWED_ENV_KEYS]
    return TokensStatusResponse(keys=keys)


@router.put("/tokens")
async def put_tokens(
    body: TokensUpdateBody,
    _: Annotated[Any, Depends(get_current_principal)],
) -> dict[str, Any]:
    bad = [k for k in body.values if k not in ALLOWED_ENV_KEYS]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported keys: {', '.join(bad)}",
        )

    if not body.values:
        return {"ok": True, "updated": 0}

    filtered = {k: v for k, v in body.values.items() if k in ALLOWED_ENV_KEYS}
    try:
        result = await apply_env_changes(filtered)
    except SettingsConfigureError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    if not result.ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(result.errors) or "Invalid updates",
        )

    return {"ok": True, "updated": result.updated}
