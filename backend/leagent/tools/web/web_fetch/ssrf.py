"""SSRF guards for user-supplied fetch URLs."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
    }
)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_public_http_url(url: str) -> str:
    """Validate ``url`` is http(s) and does not target private/link-local hosts.

    DNS may return a mix of public and non-routable/special addresses (for example
    Wikipedia resolving to a public IPv4 plus a private-looking ``2001::1`` IPv6
    answer). We allow the URL when **at least one** resolved address is public;
    we only refuse when every answer is non-public.

    Returns the normalized URL string. Raises ``ValueError`` on rejection.
    """
    raw = (url or "").strip()
    if not raw:
        raise ValueError("url is required")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http:// and https:// URLs are allowed for web_fetch")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("URL hostname is missing")
    if host in _BLOCKED_HOSTS or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError(f"Refusing to fetch private/local host {host!r}")

    # Literal IP in the URL — must itself be public.
    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip):
            raise ValueError(f"Refusing to fetch non-public IP {host!r}")
        return raw
    except ValueError as e:
        if "Refusing" in str(e):
            raise
        # Not an IP literal — resolve DNS.
        pass

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve host {host!r}: {e}") from e

    saw_any = False
    public_addrs: list[str] = []
    blocked_addrs: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        saw_any = True
        if _is_blocked_ip(ip):
            blocked_addrs.append(addr)
        else:
            public_addrs.append(addr)

    if not saw_any:
        raise ValueError(f"Cannot resolve host {host!r} to an IP address")
    if not public_addrs:
        sample = blocked_addrs[0] if blocked_addrs else "?"
        raise ValueError(f"Refusing to fetch host {host!r} (resolves only to non-public {sample})")
    return raw
