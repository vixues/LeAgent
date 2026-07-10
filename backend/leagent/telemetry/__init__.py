"""OpenTelemetry and structured-logging utilities for LeAgent.

Logging configuration has a single home in :mod:`leagent.utils.logging`.
The former ``telemetry.logging`` shim (a second ``configure_structlog``
entrypoint) has been removed; the correlation ContextVars are re-exported
here from the canonical pipeline for backwards compatibility only.
"""

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
from leagent.utils.logging import (
    bind_log_context,
    bind_turn_log_context,
    clear_log_context,
    current_llm_call_kind,
    get_logger,
    next_llm_call_index,
    request_id_var,
    session_id_var,
    setup_logging,
    tenant_id_var,
    unbind_log_context,
    user_id_var,
    user_message_id_var,
)

__all__ = [
    "TelemetryConfig",
    "bind_log_context",
    "bind_turn_log_context",
    "clear_log_context",
    "current_llm_call_kind",
    "current_traceparent",
    "get_logger",
    "get_tracer",
    "inject_traceparent",
    "instrument_all",
    "next_llm_call_index",
    "request_id_var",
    "run_with_traceparent",
    "session_id_var",
    "setup_logging",
    "setup_otel",
    "tenant_id_var",
    "unbind_log_context",
    "user_id_var",
    "user_message_id_var",
]
