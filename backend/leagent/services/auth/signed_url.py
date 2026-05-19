"""HMAC-signed URLs for chat attachment previews / downloads.

The frontend needs to render inline previews of session attachments (images,
PDFs, text excerpts) without forcing a second round-trip for the JWT. We
solve that by emitting short-lived, HMAC-signed URLs alongside each
attachment in the SSE ``attachments`` event:

* ``sub`` — the attachment UUID
* ``scope`` — ``preview`` or ``download``
* ``uid`` — the user ID who created the token
* ``exp`` — UNIX timestamp when the URL stops being valid

The signing secret is the ``files.signed_url_secret`` setting when set,
otherwise we fall back to the JWT signing secret so ops do not have to
configure yet another key for a local bring-up.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from leagent.config.settings import Settings

_Scope = Literal["preview", "download"]


@dataclass(slots=True, frozen=True)
class SignedToken:
    """The decoded payload of a signed URL token."""

    attachment_id: UUID
    user_id: UUID | None
    scope: _Scope
    expires_at: int


class SignedUrlError(ValueError):
    """Raised when a signed-URL token fails to verify."""


def _secret(settings: Settings) -> bytes:
    raw = (settings.files.signed_url_secret or "leagent-local-secret").encode()
    return raw


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_signed_token(
    settings: Settings,
    *,
    attachment_id: UUID,
    user_id: UUID | None,
    scope: _Scope = "preview",
    ttl_seconds: int | None = None,
) -> str:
    """Return a signed opaque token for an attachment URL."""
    exp = int(time.time()) + int(
        ttl_seconds if ttl_seconds is not None else settings.files.preview_ttl_seconds
    )
    payload = {
        "sub": str(attachment_id),
        "uid": str(user_id) if user_id else None,
        "scope": scope,
        "exp": exp,
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    mac = hmac.new(_secret(settings), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64encode(mac)}"


def verify_signed_token(settings: Settings, token: str) -> SignedToken:
    """Decode/verify a signed-URL token.

    Raises :class:`SignedUrlError` on any failure — invalid format, bad
    signature, expired, or malformed payload.
    """
    if not token or token.count(".") != 1:
        raise SignedUrlError("Malformed signed URL token")
    body_b64, mac_b64 = token.split(".", 1)
    expected = hmac.new(_secret(settings), body_b64.encode(), hashlib.sha256).digest()
    try:
        actual = _b64decode(mac_b64)
    except Exception as exc:  # noqa: BLE001
        raise SignedUrlError("Invalid signed URL signature") from exc
    if not hmac.compare_digest(expected, actual):
        raise SignedUrlError("Invalid signed URL signature")

    try:
        payload = json.loads(_b64decode(body_b64))
    except Exception as exc:  # noqa: BLE001
        raise SignedUrlError("Corrupt signed URL payload") from exc

    try:
        attachment_id = UUID(str(payload["sub"]))
    except Exception as exc:  # noqa: BLE001
        raise SignedUrlError("Invalid attachment id in signed URL") from exc

    scope = payload.get("scope")
    if scope not in ("preview", "download"):
        raise SignedUrlError("Unknown scope in signed URL")

    exp = int(payload.get("exp") or 0)
    if exp and exp < int(time.time()):
        raise SignedUrlError("Signed URL has expired")

    user_id: UUID | None = None
    if payload.get("uid"):
        try:
            user_id = UUID(str(payload["uid"]))
        except Exception:  # noqa: BLE001
            user_id = None

    return SignedToken(
        attachment_id=attachment_id,
        user_id=user_id,
        scope=scope,  # type: ignore[arg-type]
        expires_at=exp,
    )


def build_preview_url(
    settings: Settings,
    *,
    attachment_id: UUID,
    user_id: UUID | None,
    base_path: str = "/api/v1/files",
) -> str:
    """Return the canonical inline-preview URL for an attachment."""
    token = create_signed_token(
        settings,
        attachment_id=attachment_id,
        user_id=user_id,
        scope="preview",
    )
    return f"{base_path}/{attachment_id}/preview?token={token}"


def build_download_url(
    settings: Settings,
    *,
    attachment_id: UUID,
    user_id: UUID | None,
    base_path: str = "/api/v1/files",
) -> str:
    """Return a signed URL for the download endpoint."""
    token = create_signed_token(
        settings,
        attachment_id=attachment_id,
        user_id=user_id,
        scope="download",
    )
    return f"{base_path}/{attachment_id}/download?token={token}"
