"""Structured logging setup using structlog.

This module is the single source of truth for LeAgent's logging pipeline.
Every process configures logging exactly once via :func:`setup_logging`, and
every module acquires its logger via :func:`get_logger`. Correlation fields
(``request_id``, ``user_id``, ``session_id``, ``agent_id``) are bound on
``structlog.contextvars`` at request/turn boundaries and merged into every log
line; OpenTelemetry ``trace_id`` / ``span_id`` are injected by
:func:`_inject_otel_context` when a span is active.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from contextvars import ContextVar
from typing import Any, Literal

import structlog

# ---------------------------------------------------------------------------
# Correlation context
# ---------------------------------------------------------------------------
# Canonical mechanism is ``structlog.contextvars`` (bound via the helpers
# below and merged by ``merge_contextvars``). These ContextVars are retained
# for components that read them directly (e.g. legacy middleware/interceptors)
# and are kept in sync by :func:`bind_log_context`.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)

# Keys that mirror into the bare ContextVars above for backwards compatibility.
_MIRRORED_CONTEXT_VARS = {
    "request_id": request_id_var,
    "user_id": user_id_var,
    "tenant_id": tenant_id_var,
}


def get_logger(name: str | None = None) -> Any:
    """Return the canonical structlog logger.

    This is the single accessor every module should use:
    ``logger = get_logger(__name__)``. It is a thin wrapper over
    ``structlog.get_logger`` so the whole codebase shares one pipeline and we
    avoid scattered ``logging.getLogger`` / ``structlog.get_logger`` idioms.
    """
    return structlog.get_logger(name)


def bind_log_context(**fields: Any) -> None:
    """Bind correlation fields onto the active logging context.

    Fields flow into every subsequent log line on the current context (request
    or agent turn) via ``merge_contextvars``. Drops ``None`` values so callers
    can pass optional ids unconditionally.
    """
    clean = {k: v for k, v in fields.items() if v is not None}
    if not clean:
        return
    structlog.contextvars.bind_contextvars(**clean)
    for key, value in clean.items():
        var = _MIRRORED_CONTEXT_VARS.get(key)
        if var is not None:
            var.set(str(value))


def unbind_log_context(*keys: str) -> None:
    """Remove correlation fields from the active logging context."""
    if keys:
        structlog.contextvars.unbind_contextvars(*keys)


def clear_log_context() -> None:
    """Clear all correlation fields from the active logging context."""
    structlog.contextvars.clear_contextvars()


def _inject_otel_context(
    _logger: Any, _method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Structlog processor: attach OpenTelemetry trace/span ids when present.

    Request/user/session correlation is handled by ``merge_contextvars``; this
    processor only adds the active span identifiers so logs correlate with
    traces when OTel is configured. It is a no-op when no valid span is active
    or the OTel API is not installed.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            event_dict.setdefault("trace_id", format(ctx.trace_id, "032x"))
            event_dict.setdefault("span_id", format(ctx.span_id, "016x"))
    except Exception:
        pass
    return event_dict


def setup_logging(
    level: str = "INFO",
    log_format: Literal["json", "console", "auto"] = "auto",
    json_output: bool | None = None,
    log_file: str = "",
) -> None:
    """Configure structlog and stdlib logging for the application.

    Args:
        level: Root log level (DEBUG, INFO, WARNING, ERROR).
        log_format: Output format: "json", "console", or "auto".
            "auto" uses JSON when json_output is True (or when not debug),
            and console otherwise.  Explicit "json"/"console" overrides
            the json_output flag.
        json_output: Legacy flag kept for backwards compatibility.
            Ignored when log_format is not "auto".
        log_file: If non-empty, also write JSON log lines to this file
            (rotating, 10 MB per file, 5 backups).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Resolve the effective format
    if log_format == "json":
        use_json = True
    elif log_format == "console":
        use_json = False
    else:
        # "auto": fall back to the legacy json_output flag
        use_json = json_output if json_output is not None else True

    # --- Renderer -----------------------------------------------------------
    if use_json:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # --- Processors that run for structlog-originated log calls -------------
    # These run before wrap_for_formatter hands the event dict to the stdlib
    # handler.  They must NOT include TimeStamper / ExcInfo because those run
    # in the formatter's processor chain (shared path for both structlog and
    # foreign stdlib records).
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ExtraAdder(),
            _inject_otel_context,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # --- ProcessorFormatter -------------------------------------------------
    # foreign_pre_chain: runs for stdlib logging.getLogger(__name__) records
    # that did NOT originate from structlog.  Extracts the same metadata so
    # both paths produce identical structured events.
    foreign_pre_chain: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.stdlib.ExtraAdder(),
        _inject_otel_context,
    ]

    # processors: runs for ALL records (structlog + foreign) after the
    # pre-chain.  Adds timestamp, formats exc_info, decodes bytes.
    fmt_processors: list[structlog.types.Processor] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if use_json:
        fmt_processors.append(structlog.processors.format_exc_info)
    fmt_processors += [
        structlog.processors.UnicodeDecoder(),
        renderer,
    ]
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=foreign_pre_chain,
        processors=fmt_processors,
    )

    # --- Root stdlib logger -------------------------------------------------
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    root_logger.addHandler(stdout_handler)
    root_logger.setLevel(log_level)

    # --- Optional rotating file handler (always JSON) -----------------------
    if log_file:
        file_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=foreign_pre_chain,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer(),
            ],
        )
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    # --- Third-party logger tuning ------------------------------------------
    for noisy in (
        "uvicorn.access",
        "httpcore",
        "httpx",
        "asyncio",
        "pymilvus",
        "hpack",
        "aiohttp",
        "multipart",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("uvicorn.error").setLevel(log_level)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if log_level > logging.DEBUG else logging.INFO
    )


__all__ = [
    "setup_logging",
    "get_logger",
    "bind_log_context",
    "unbind_log_context",
    "clear_log_context",
    "request_id_var",
    "user_id_var",
    "tenant_id_var",
]
