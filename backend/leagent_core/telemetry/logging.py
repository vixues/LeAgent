"""Structured JSON logging with trace/request context enrichment."""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any

try:
    import structlog

    _HAS_STRUCTLOG = True
except ImportError:  # pragma: no cover - structlog is in deps
    _HAS_STRUCTLOG = False


# Context variables populated by middleware and the gRPC interceptor.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
tenant_id_var: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def _inject_context(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Structlog processor: attach request/user/tenant + OTel trace ids."""
    rid = request_id_var.get()
    if rid:
        event_dict.setdefault("request_id", rid)
    uid = user_id_var.get()
    if uid:
        event_dict.setdefault("user_id", uid)
    tid = tenant_id_var.get()
    if tid:
        event_dict.setdefault("tenant_id", tid)
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


def _has_processor_formatter(root: logging.Logger) -> bool:
    """Return True if any handler on ``root`` already has a structlog
    ``ProcessorFormatter`` installed — i.e. ``leagent.utils.logging
    .setup_logging`` has already fully configured the stdlib + structlog
    pipeline and we must not clobber it.
    """
    if not _HAS_STRUCTLOG:
        return False
    ProcessorFormatter = getattr(structlog.stdlib, "ProcessorFormatter", None)
    if ProcessorFormatter is None:
        return False
    for handler in root.handlers:
        if isinstance(getattr(handler, "formatter", None), ProcessorFormatter):
            return True
    return False


def _install_context_injector() -> None:
    """Ensure ``_inject_context`` is present in the already-configured
    structlog processor chain so trace/request/user IDs are attached without
    rebuilding handlers. No-op when structlog is not installed."""
    if not _HAS_STRUCTLOG:
        return
    try:
        cfg = structlog.get_config()
    except Exception:
        return
    processors = list(cfg.get("processors") or [])
    if any(p is _inject_context for p in processors):
        return
    # Insert BEFORE the final renderer / wrap_for_formatter so the injected
    # fields flow through TimeStamper, ExcInfo, etc. exactly like the chain
    # set up by setup_logging.
    insert_at = len(processors)
    for idx, proc in enumerate(processors):
        name = getattr(proc, "__qualname__", "") or getattr(proc, "__name__", "")
        if name.endswith("wrap_for_formatter"):
            insert_at = idx
            break
    processors.insert(insert_at, _inject_context)
    kwargs = {k: v for k, v in cfg.items() if k != "processors"}
    try:
        structlog.configure(processors=processors, **kwargs)
    except Exception:
        pass


def configure_structlog(
    *,
    service: str,
    level: str = "INFO",
    json_output: bool = True,
) -> None:
    """Configure stdlib logging + structlog to emit JSON lines with context.

    Safe to call a second time after
    :func:`leagent.utils.logging.setup_logging`: when the root logger
    already has a ``structlog.stdlib.ProcessorFormatter`` handler, this
    function preserves that config and only injects the request/trace
    context processor + binds the service tag. Otherwise (standalone
    microservice entrypoints, tests, CLI tools) it performs the full
    stdlib + structlog setup as before.
    """
    root = logging.getLogger()

    # ── Idempotent path ─────────────────────────────────────────────────────
    # ``setup_logging`` already wired a ProcessorFormatter — do not clobber
    # its handlers or the colourised renderer. Just attach request/trace/user
    # context + the service tag.
    if _has_processor_formatter(root):
        _install_context_injector()
        if _HAS_STRUCTLOG:
            structlog.contextvars.bind_contextvars(service=service)
        # Honour the requested level even in the idempotent path so
        # microservice callers can lower it without a full reconfigure.
        try:
            root.setLevel(level.upper())
        except (TypeError, ValueError):
            pass
        return

    # ── Full configuration path ─────────────────────────────────────────────
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(stream=sys.stdout)
    root.addHandler(handler)
    root.setLevel(level.upper())

    if not _HAS_STRUCTLOG:
        fmt = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        return

    renderer = (
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _inject_context,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    structlog.contextvars.bind_contextvars(service=service)


__all__ = [
    "configure_structlog",
    "request_id_var",
    "user_id_var",
    "tenant_id_var",
]
