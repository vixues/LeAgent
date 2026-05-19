"""HMAC-SHA256 token minting and verification (no external deps)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


class TokenError(Exception):
    pass


def mint_token(
    payload: dict[str, Any],
    secret: str,
    *,
    algorithm: str = "HS256",
) -> str:
    """Create a compact base64url(payload).base64url(signature) token."""
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).rstrip(b"=").decode()
    sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{body}.{sig}"


def decode_token(
    token: str,
    secret: str,
    *,
    algorithms: list[str] | None = None,
    audience: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Decode and verify a token produced by :func:`mint_token`."""
    parts = token.rsplit(".", 1)
    if len(parts) != 2:
        raise TokenError("malformed token")

    body_b64, sig = parts
    expected = hmac.new(secret.encode(), body_b64.encode(), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        raise TokenError("invalid signature")

    padding = 4 - len(body_b64) % 4
    if padding != 4:
        body_b64 += "=" * padding

    try:
        payload = json.loads(base64.urlsafe_b64decode(body_b64))
    except Exception as exc:
        raise TokenError("decode failed") from exc

    if audience and payload.get("aud") != audience:
        raise TokenError("audience mismatch")

    require_exp = (options or {}).get("require_exp", False)
    exp = payload.get("exp")
    if exp is not None and exp < time.time():
        raise TokenError("token expired")
    elif require_exp and exp is None:
        raise TokenError("exp claim required")

    return payload
