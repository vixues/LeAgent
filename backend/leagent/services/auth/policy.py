"""Effective security policy helpers (enforce-auth, bind checks)."""

from __future__ import annotations

import os
from typing import Any


def _host_is_loopback(host: str) -> bool:
    h = (host or "").strip().lower()
    return h in {"127.0.0.1", "localhost", "::1"}


def is_desktop_runtime(settings: object | None = None) -> bool:
    if os.environ.get("LEAGENT_DESKTOP") == "1":
        return True
    if settings is not None and bool(getattr(settings, "desktop_mode", False)):
        return True
    return False


def effective_enforce_auth(settings: object | None = None) -> bool:
    """Whether protected routes require a verified bearer token.

    Resolution order:
    1. Explicit ``security.enforce_auth`` when set to a bool
    2. Desktop / loopback → off
    3. Non-loopback bind (incl. ``0.0.0.0``) → on
    """
    sec = getattr(settings, "security", None) if settings is not None else None
    if sec is not None:
        raw = getattr(sec, "enforce_auth", None)
        # Tri-state: None means auto; bool is explicit.
        if raw is True:
            return True
        if raw is False:
            return False

    if settings is None:
        try:
            from leagent.config.settings import get_settings

            settings = get_settings()
            return effective_enforce_auth(settings)
        except Exception:  # noqa: BLE001
            return False

    if is_desktop_runtime(settings):
        return False

    host = str(getattr(settings, "host", "0.0.0.0") or "0.0.0.0")
    if _host_is_loopback(host):
        return False
    return True


def effective_rate_limit_enabled(settings: object | None = None) -> bool:
    sec = getattr(settings, "security", None) if settings is not None else None
    if sec is None:
        return False
    raw = getattr(sec, "rate_limit_enabled", None)
    if raw is True:
        return True
    if raw is False:
        # Still auto-enable when auth is enforced (defense in depth).
        if getattr(sec, "rate_limit_auto_with_auth", True) and effective_enforce_auth(settings):
            return True
        return False
    return effective_enforce_auth(settings)


def bind_exposure_warnings(settings: object) -> list[str]:
    """Return human-readable startup warnings for insecure bind/secret combos."""
    warnings: list[str] = []
    host = str(getattr(settings, "host", "") or "")
    if not _host_is_loopback(host) and not is_desktop_runtime(settings):
        warnings.append(
            f"Listening on {host!r} (non-loopback). Authentication will be enforced; "
            "ensure LEAGENT_SECRET_KEY is set and complete /auth/setup."
        )
        from leagent.services.auth.secrets import is_weak_secret, resolve_signing_secret

        try:
            secret = resolve_signing_secret(settings)
        except Exception:  # noqa: BLE001
            secret = ""
        if is_weak_secret(secret):
            warnings.append(
                "Signing secret is weak or missing while the API is network-exposed."
            )
    workers = int(getattr(settings, "workers", 1) or 1)
    db = getattr(settings, "database", None)
    driver = str(getattr(db, "driver", "") or "") if db is not None else ""
    if workers > 1 and "sqlite" in driver.lower():
        warnings.append(
            f"LEAGENT_WORKERS={workers} with SQLite is unsafe (single-writer). "
            "Set workers=1 or switch to PostgreSQL."
        )
    return warnings


def security_status_payload(settings: object) -> dict[str, Any]:
    from leagent.services.auth.store import get_security_store

    store = get_security_store()
    enforced = effective_enforce_auth(settings)
    return {
        "enforce_auth": enforced,
        "setup_complete": store.is_setup_complete(),
        "desktop_mode": is_desktop_runtime(settings),
        "require_unlock_on_desktop": store.load().require_unlock_on_desktop,
        "host": str(getattr(settings, "host", "") or ""),
        "multi_user": True,
    }
