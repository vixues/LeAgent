"""httpx client defaults for outbound HTTP.

``httpx`` reads ``HTTP_PROXY`` / ``HTTPS_PROXY`` / ``ALL_PROXY`` when
``trust_env=True``.

SOCKS URLs (common with local VPN clients on macOS) require the optional
``socksio`` dependency. Without it, ``httpx`` raises an error at client
construction when it tries to load env proxies (e.g. ``Unknown scheme for proxy
URL``).

We keep Ubuntu/Linux behavior unchanged by default, but on macOS (or any host)
with SOCKS proxy env vars set we:
- rewrite bare ``socks://`` (and ``socks4://``) to ``socks5://`` because ``httpx``
  only accepts ``socks5`` / ``socks5h`` for SOCKS proxies — Clash and similar
  apps often export ``socks://127.0.0.1:...`` which would otherwise raise
  ``Unknown scheme for proxy URL``.
- allow inheriting env proxies if SOCKS support is installed (preferred)
- otherwise disable inheriting env proxies to avoid hard failures
"""

from __future__ import annotations

import logging
import os
from typing import Final

logger = logging.getLogger(__name__)

_SOCKS_SCHEMES = frozenset({"socks", "socks4", "socks5", "socks5h"})
_logged_socks_disable = False
_logged_socks_enable = False
_logged_trust_override = False
_logged_proxy_scheme_normalization: set[str] = set()

_PROXY_ENV_KEYS: Final[tuple[str, ...]] = (
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
)


def _normalize_proxy_scheme_for_httpx(value: str) -> str:
    """Map proxy URLs to schemes httpx accepts (``socks5`` / ``socks5h`` only for SOCKS)."""
    if "://" not in value:
        return value
    scheme, sep, rest = value.partition("://")
    sl = scheme.lower()
    if sl == "socks":
        return f"socks5://{rest}"
    if sl == "socks4":
        return f"socks5://{rest}"
    return value


def _apply_proxy_env_normalization() -> None:
    """Rewrite standard proxy env vars so httpx ``Proxy`` construction succeeds."""
    global _logged_proxy_scheme_normalization
    for key in _PROXY_ENV_KEYS:
        raw = os.environ.get(key)
        if not raw:
            continue
        stripped = raw.strip()
        new = _normalize_proxy_scheme_for_httpx(stripped)
        if new != stripped:
            os.environ[key] = new
            if key not in _logged_proxy_scheme_normalization:
                _logged_proxy_scheme_normalization.add(key)
                logger.info(
                    "httpx: normalized %s for httpx (%r → %r); "
                    "httpx only supports socks5/socks5h, not bare socks://.",
                    key,
                    stripped,
                    new,
                )


def _socks_proxy_env_key() -> str | None:
    """Return the first proxy env var key that uses a SOCKS scheme."""
    for key in _PROXY_ENV_KEYS:
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        scheme = raw.split("://", 1)[0].lower()
        if scheme in _SOCKS_SCHEMES:
            return key
    return None


def _has_socks_support() -> bool:
    """Return True if httpx has SOCKS support installed (via socksio)."""
    try:
        import socksio  # noqa: F401
    except Exception:
        return False
    return True


def httpx_trust_env() -> bool:
    """Return whether httpx should inherit proxy-related environment variables.

    Override (checked first), via ``LLM_HTTPX_TRUST_ENV`` or
    ``LEAGENT_HTTPX_TRUST_ENV``:

    - ``always`` / ``on`` / ``1`` / ``true`` / ``yes`` → ``True``
    - ``never`` / ``off`` / ``0`` / ``false`` / ``no`` → ``False``
    - ``auto`` (default) → SOCKS-aware behaviour below

    In ``auto`` mode: if a standard proxy env var uses a SOCKS scheme and
    ``socksio`` is not installed, return ``False`` (avoids client construction
    errors). If ``socksio`` is installed, return ``True`` so macOS SOCKS
    proxies are honored.
    """
    global _logged_socks_disable, _logged_socks_enable, _logged_trust_override

    _apply_proxy_env_normalization()

    mode = (
        os.environ.get("LLM_HTTPX_TRUST_ENV") or os.environ.get("LEAGENT_HTTPX_TRUST_ENV") or "auto"
    ).strip().lower()
    if mode in ("always", "on", "1", "true", "yes"):
        if not _logged_trust_override:
            _logged_trust_override = True
            logger.info("httpx: LLM_HTTPX_TRUST_ENV=%r → trust_env=True", mode)
        return True
    if mode in ("never", "off", "0", "false", "no"):
        if not _logged_trust_override:
            _logged_trust_override = True
            logger.info("httpx: LLM_HTTPX_TRUST_ENV=%r → trust_env=False", mode)
        return False
    if mode not in ("auto", ""):
        if not _logged_trust_override:
            _logged_trust_override = True
            logger.warning(
                "httpx: unknown LLM_HTTPX_TRUST_ENV=%r; using auto (SOCKS-aware) behaviour.",
                mode,
            )

    socks_key = _socks_proxy_env_key()
    if socks_key is None:
        return True

    if _has_socks_support():
        if not _logged_socks_enable:
            _logged_socks_enable = True
            logger.info(
                "httpx: %s is a SOCKS URL; socksio is installed; using trust_env=True (SOCKS enabled).",
                socks_key,
            )
        return True

    if not _logged_socks_disable:
        _logged_socks_disable = True
        logger.warning(
            "httpx: %s is a SOCKS URL but socksio is not installed; using trust_env=False. "
            "To support macOS proxy apps (SOCKS), install socksio (or httpx[socks]).",
            socks_key,
        )
    return False


# Eager normalization so ``httpx`` clients with ``trust_env=True`` see compatible URLs
# even if they are constructed before the first ``httpx_trust_env()`` call.
_apply_proxy_env_normalization()
