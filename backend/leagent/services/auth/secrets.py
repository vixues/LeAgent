"""Resolve signing secrets for JWT and signed URLs."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from leagent.config.constants import SECRET_DIR

_WEAK_DEFAULTS = frozenset(
    {
        "",
        "changeme",
        "changeme-generate-with-openssl-rand-hex-32",
        "leagent-local-secret",
        "secret",
        "password",
    }
)


def is_weak_secret(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    if raw.lower() in _WEAK_DEFAULTS:
        return True
    return len(raw) < 16


def _secret_file_path() -> Path:
    return SECRET_DIR / ".secret_key"


def ensure_persistent_secret() -> str:
    """Return a durable secret, generating ``$LEAGENT_HOME/secrets/.secret_key`` if needed."""
    path = _secret_file_path()
    if path.is_file():
        raw = path.read_text(encoding="utf-8").strip()
        if raw and not is_weak_secret(raw):
            return raw
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(32)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


def resolve_signing_secret(settings: object | None = None) -> str:
    """Resolve the HMAC signing secret used for session JWTs and signed URLs.

    Order:
    1. ``LEAGENT_SECRET_KEY`` env / ``settings.secret_key``
    2. ``settings.files.signed_url_secret``
    3. Durable ``$LEAGENT_HOME/secrets/.secret_key`` (auto-generated)
    """
    env_key = (os.environ.get("LEAGENT_SECRET_KEY") or "").strip()
    if env_key and not is_weak_secret(env_key):
        return env_key

    if settings is not None:
        sk = str(getattr(settings, "secret_key", "") or "").strip()
        if sk and not is_weak_secret(sk):
            return sk
        files = getattr(settings, "files", None)
        if files is not None:
            fsk = str(getattr(files, "signed_url_secret", "") or "").strip()
            if fsk and not is_weak_secret(fsk):
                return fsk

    return ensure_persistent_secret()


@lru_cache(maxsize=1)
def cached_signing_secret() -> str:
    try:
        from leagent.config.settings import get_settings

        return resolve_signing_secret(get_settings())
    except Exception:  # noqa: BLE001
        return ensure_persistent_secret()


def clear_secret_cache() -> None:
    cached_signing_secret.cache_clear()
