"""Short-lived preview tokens for the coding-project reverse proxy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import UUID

from leagent.config.settings import Settings
from leagent.services.auth.tokens import mint_token, decode_token, TokenError

PREVIEW_AUDIENCE = "leagent-coding-preview"


def _signing_secret(settings: Settings) -> str:
    s = (settings.canvas.preview_signing_secret or "").strip()
    if s:
        return s
    return "leagent-local-secret"


def mint_preview_token(
    settings: Settings,
    *,
    project_id: UUID,
    run_seq: int,
    user_id: UUID,
    ttl_seconds: int | None = None,
) -> str:
    if ttl_seconds is None:
        ttl_seconds = settings.coding_projects.preview_token_ttl_seconds
    ttl_seconds = max(60, int(ttl_seconds))

    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)
    payload: dict[str, Any] = {
        "cpid": str(project_id),
        "run": int(run_seq),
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "aud": PREVIEW_AUDIENCE,
    }
    return mint_token(payload, _signing_secret(settings))


def decode_preview_token(settings: Settings, token: str) -> dict[str, Any]:
    return decode_token(
        token,
        _signing_secret(settings),
        audience=PREVIEW_AUDIENCE,
        options={"require_exp": True},
    )


def preview_query_path(project_id: UUID, token: str, *, sub_path: str = "") -> str:
    cleaned = sub_path.lstrip("/") if sub_path else ""
    base = f"/api/v1/coding-projects/{project_id}/preview"
    if cleaned:
        return f"{base}/{cleaned}?token={quote(token, safe='')}"
    return f"{base}/?token={quote(token, safe='')}"
