"""OpenTelemetry and structured-logging utilities for LeAgent."""

from leagent.telemetry.logging import (
    configure_structlog,
    request_id_var,
    tenant_id_var,
    user_id_var,
)
from leagent.telemetry.otel import (
    TelemetryConfig,
    get_tracer,
    instrument_all,
    setup_otel,
)
from leagent.telemetry.propagation import (
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
    "request_id_var",
    "run_with_traceparent",
    "setup_otel",
    "tenant_id_var",
    "user_id_var",
]
