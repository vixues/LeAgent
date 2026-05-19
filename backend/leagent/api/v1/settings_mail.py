"""Read-only SMTP snapshot + connection test (Settings → Mail)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from leagent.config.settings import get_settings
from leagent.services.auth.deps import get_current_principal
from leagent.services.smtp_defaults import (
    check_smtp_connection,
    merge_smtp_defaults,
    send_smtp_test_message,
)

router = APIRouter()


class MailStatusResponse(BaseModel):
    host: str
    port: int
    from_email: str
    from_name: str
    use_tls: bool
    use_ssl: bool
    username_set: bool
    password_set: bool


class MailTestBody(BaseModel):
    to: str | None = Field(default=None, max_length=254)


class MailTestResponse(BaseModel):
    ok: bool
    detail: str


@router.get("/mail", response_model=MailStatusResponse)
async def get_mail_status(_: Annotated[Any, Depends(get_current_principal)]) -> MailStatusResponse:
    s = get_settings()
    return MailStatusResponse(
        host=(s.smtp_host or "").strip(),
        port=int(s.smtp_port) if s.smtp_port else 587,
        from_email=(s.smtp_from_email or "").strip(),
        from_name=(s.smtp_from_name or "").strip(),
        use_tls=bool(s.smtp_use_tls),
        use_ssl=bool(s.smtp_use_ssl),
        username_set=bool((s.smtp_username or "").strip()),
        password_set=bool((s.smtp_password or "").strip()),
    )


@router.post("/mail/test", response_model=MailTestResponse)
async def post_mail_test(
    body: MailTestBody,
    _: Annotated[Any, Depends(get_current_principal)],
) -> MailTestResponse:
    merged = merge_smtp_defaults({})
    if not (merged.get("smtp_host") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="smtp_host is not configured (Settings → Mail or LEAGENT_SMTP_HOST).",
        )
    to_addr = (body.to or "").strip()
    if to_addr and not (merged.get("from_email") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_email is not configured (required to send a test message).",
        )
    try:
        if to_addr:
            await send_smtp_test_message(merged, to_addr)
            return MailTestResponse(ok=True, detail="Test message sent.")
        await check_smtp_connection(merged)
        return MailTestResponse(ok=True, detail="SMTP connection and authentication succeeded.")
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"SMTP error: {e}",
        ) from e
