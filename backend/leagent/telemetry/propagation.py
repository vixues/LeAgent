"""Trace-context propagation across Redis Streams, HTTP headers, and gRPC.

All cross-process transports stash a ``traceparent`` string on each message.
This module gives service code a consistent way to read/inject/restore that
context so a single logical operation shows up as one trace in Jaeger/Tempo.
"""

from __future__ import annotations

import contextlib
from typing import Any, Iterator


def current_traceparent() -> str | None:
    """Return the active W3C traceparent string, if any."""
    try:
        from opentelemetry import trace
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        return carrier.get("traceparent")
    except Exception:
        return None


def inject_traceparent(carrier: dict[str, str]) -> dict[str, str]:
    """Inject the active trace context into a carrier dict."""
    try:
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )
        TraceContextTextMapPropagator().inject(carrier)
    except Exception:
        pass
    return carrier


@contextlib.contextmanager
def run_with_traceparent(traceparent: str | None) -> Iterator[None]:
    """Attach ``traceparent`` to the current context for the duration of a block."""
    if not traceparent:
        yield
        return
    try:
        from opentelemetry import context as otel_context
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        ctx = TraceContextTextMapPropagator().extract({"traceparent": traceparent})
        token = otel_context.attach(ctx)
        try:
            yield
        finally:
            otel_context.detach(token)
    except Exception:
        yield


__all__ = [
    "current_traceparent",
    "inject_traceparent",
    "run_with_traceparent",
]
