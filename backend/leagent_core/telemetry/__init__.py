"""OpenTelemetry setup, structured JSON logging, and trace propagation helpers."""

from leagent_core.telemetry.logging import configure_structlog
from leagent_core.telemetry.otel import (
    TelemetryConfig,
    get_tracer,
    instrument_all,
    setup_otel,
)
from leagent_core.telemetry.propagation import (
    current_traceparent,
    inject_traceparent,
    run_with_traceparent,
)

__all__ = [
    "TelemetryConfig",
    "configure_structlog",
    "current_traceparent",
    "get_tracer",
    "inject_traceparent",
    "instrument_all",
    "run_with_traceparent",
    "setup_otel",
]
