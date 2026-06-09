"""Free-port allocator with a per-project lease table.

Why not just bind to ``0`` and let the OS pick? Because dev servers
are spawned as child processes and we need the chosen port *before*
the child starts so we can pass it on argv (``--port``). The
allocator therefore probes inside the configured range, returns the
first free port, and remembers the lease so a parallel scaffold run
doesn't hand the same number to two children.

Lease release happens on :meth:`PortAllocator.release` (called from
the supervisor on stop) or when ``free_if_unused`` is asked to
re-probe a held port. The allocator has no persistent state — the
process owns the lease table; restart frees everything.
"""

from __future__ import annotations

import socket
import threading
from typing import Iterable

import structlog

logger = structlog.get_logger(__name__)


class PortAllocationError(RuntimeError):
    """Raised when no free port is available in the configured range."""


class PortAllocator:
    """Thread-safe TCP port allocator over an inclusive range.

    The bind/close probe runs on ``host`` only — by default
    ``127.0.0.1`` — so the allocator never collides with services
    listening on other interfaces.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        low: int = 39000,
        high: int = 39999,
    ) -> None:
        if low > high:
            raise ValueError(f"port range invalid: {low}..{high}")
        self._host = host
        self._low = low
        self._high = high
        self._lock = threading.Lock()
        self._leases: dict[str, int] = {}
        self._held_ports: set[int] = set()

    @property
    def host(self) -> str:
        return self._host

    @property
    def held_ports(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(sorted(self._held_ports))

    def _probe(self, port: int) -> bool:
        """Return True iff a TCP listener can bind ``port`` right now."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self._host, port))
            return True
        except OSError:
            return False
        finally:
            s.close()

    def allocate(self, lease_key: str) -> int:
        """Reserve and return a free port for ``lease_key``.

        If ``lease_key`` already has a lease and the port still
        appears free, that port is returned unchanged so calling
        ``allocate`` is idempotent for restart-style flows. Otherwise
        a new port is probed.
        """
        with self._lock:
            existing = self._leases.get(lease_key)
            if existing is not None:
                if self._probe(existing):
                    self._held_ports.add(existing)
                    return existing
                self._held_ports.discard(existing)
                self._leases.pop(lease_key, None)

            for port in self._iter_range():
                if port in self._held_ports:
                    continue
                if self._probe(port):
                    self._leases[lease_key] = port
                    self._held_ports.add(port)
                    logger.debug(
                        "coding_projects_port_allocated",
                        lease=lease_key,
                        port=port,
                    )
                    return port

        raise PortAllocationError(
            f"No free port in {self._low}..{self._high} on {self._host!r}."
        )

    def _iter_range(self) -> Iterable[int]:
        return range(self._low, self._high + 1)

    def release(self, lease_key: str) -> None:
        """Drop the lease for ``lease_key``; safe to call on unknown keys."""
        with self._lock:
            port = self._leases.pop(lease_key, None)
            if port is not None:
                self._held_ports.discard(port)
                logger.debug(
                    "coding_projects_port_released",
                    lease=lease_key,
                    port=port,
                )

    def reset(self) -> None:
        """Clear every lease — used by tests and shutdown handlers."""
        with self._lock:
            self._leases.clear()
            self._held_ports.clear()
