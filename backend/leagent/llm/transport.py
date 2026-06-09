"""Shared HTTP transport for all LLM providers.

Consolidates the duplicated ``httpx.AsyncClient`` setup that every
provider previously maintained individually.  A single configurable
:class:`HttpTransport` instance provides connection-pooled clients for
both completion and streaming requests, with consistent timeout/proxy
defaults and middleware hooks (OTel spans, request IDs).
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterator

import httpx

from leagent.utils.httpx_proxy import httpx_trust_env
from leagent.utils.logging import get_logger

logger = get_logger(__name__)

STREAM_HTTPX_TIMEOUT = httpx.Timeout(
    connect=30.0, read=None, write=60.0, pool=10.0,
)
STREAM_HTTPX_LIMITS = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20,
    keepalive_expiry=60.0,
)
DEFAULT_COMPLETE_TIMEOUT: float = 120.0


@dataclass
class TransportConfig:
    """Configurable knobs for :class:`HttpTransport`."""

    complete_timeout: float = DEFAULT_COMPLETE_TIMEOUT
    stream_timeout: httpx.Timeout = field(default_factory=lambda: STREAM_HTTPX_TIMEOUT)
    stream_limits: httpx.Limits = field(default_factory=lambda: STREAM_HTTPX_LIMITS)
    trust_env: bool = field(default_factory=httpx_trust_env)
    inject_request_id: bool = True
    otel_enabled: bool = True


class HttpTransport:
    """Pooled httpx transport shared across providers.

    Each :class:`HttpTransport` owns two lazy-initialised
    ``httpx.AsyncClient`` instances (complete + stream) so providers
    no longer duplicate this boilerplate.
    """

    def __init__(self, config: TransportConfig | None = None) -> None:
        self._cfg = config or TransportConfig()
        self._complete_client: httpx.AsyncClient | None = None
        self._stream_client: httpx.AsyncClient | None = None

    @property
    def complete_client(self) -> httpx.AsyncClient:
        if self._complete_client is None:
            self._complete_client = httpx.AsyncClient(
                timeout=self._cfg.complete_timeout,
                trust_env=self._cfg.trust_env,
            )
        return self._complete_client

    @property
    def stream_client(self) -> httpx.AsyncClient:
        if self._stream_client is None:
            self._stream_client = httpx.AsyncClient(
                timeout=self._cfg.stream_timeout,
                limits=self._cfg.stream_limits,
                trust_env=self._cfg.trust_env,
            )
        return self._stream_client

    def request_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build standard headers, optionally merging ``extra``.

        The ``X-Request-Id`` is correlated with the inbound request/turn
        ``request_id`` (bound on the logging context) when available, so an
        outbound LLM call can be traced back to the originating API request.
        Falls back to a fresh id for background/CLI work. When OTel is enabled
        a W3C ``traceparent`` is injected so downstream services join the trace.
        """
        headers: dict[str, str] = {}
        if self._cfg.inject_request_id:
            headers["X-Request-Id"] = self._correlation_id()
        if self._cfg.otel_enabled:
            with contextlib.suppress(Exception):
                from leagent.telemetry.propagation import inject_traceparent

                inject_traceparent(headers)
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def _correlation_id() -> str:
        with contextlib.suppress(Exception):
            from leagent.utils.logging import request_id_var

            rid = request_id_var.get()
            if rid:
                return str(rid)
        return uuid.uuid4().hex

    @contextlib.contextmanager
    def request_span(self, operation: str, **attributes: Any) -> Iterator[Any]:
        """Wrap an outbound LLM HTTP call in an OpenTelemetry span.

        No-op (yields ``None``) when OTel is disabled or unavailable, so
        providers can use this unconditionally.
        """
        if not self._cfg.otel_enabled:
            yield None
            return
        try:
            from leagent.telemetry.otel import get_tracer

            tracer = get_tracer("leagent.llm.transport")
            with tracer.start_as_current_span(f"llm.{operation}") as span:
                for key, value in attributes.items():
                    if value is not None:
                        with contextlib.suppress(Exception):
                            span.set_attribute(f"llm.{key}", value)
                yield span
        except Exception:  # noqa: BLE001
            yield None

    async def aclose(self) -> None:
        for client in (self._complete_client, self._stream_client):
            if client is not None:
                try:
                    await client.aclose()
                except Exception:  # noqa: BLE001
                    logger.debug("transport_client_close_error", exc_info=True)
        self._complete_client = None
        self._stream_client = None


_DEFAULT_TRANSPORT: HttpTransport | None = None


def get_default_transport() -> HttpTransport:
    """Return a process-wide shared transport (lazy singleton)."""
    global _DEFAULT_TRANSPORT
    if _DEFAULT_TRANSPORT is None:
        _DEFAULT_TRANSPORT = HttpTransport()
    return _DEFAULT_TRANSPORT


def reset_default_transport() -> None:
    """Reset the global transport (test helper)."""
    global _DEFAULT_TRANSPORT
    _DEFAULT_TRANSPORT = None


__all__ = [
    "DEFAULT_COMPLETE_TIMEOUT",
    "HttpTransport",
    "STREAM_HTTPX_LIMITS",
    "STREAM_HTTPX_TIMEOUT",
    "TransportConfig",
    "get_default_transport",
    "reset_default_transport",
]
