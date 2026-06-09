"""OpenTelemetry bootstrap.

Optional dependency: if ``opentelemetry-*`` packages are not installed, setup
becomes a no-op and :func:`get_tracer` returns a dummy tracer so callers don't
have to conditionally import OTel.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from leagent.utils.logging import get_logger

logger = get_logger(__name__)

_configured = False


@dataclass(slots=True)
class TelemetryConfig:
    service_name: str
    environment: str = "development"
    otlp_endpoint: str | None = None  # e.g. http://otel-collector:4317
    sample_ratio: float = 1.0
    enable_metrics: bool = True
    enable_logs: bool = False


def setup_otel(config: TelemetryConfig) -> None:
    """Best-effort OTel SDK initialisation.

    Called once per service entrypoint. Idempotent.
    """
    global _configured
    if _configured:
        return
    _configured = True

    endpoint = config.otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.info("OTel endpoint not set; telemetry export disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ImportError:
        logger.warning(
            "opentelemetry SDK not installed; continuing without tracing"
        )
        return

    resource = Resource.create(
        {
            SERVICE_NAME: config.service_name,
            "deployment.environment": config.environment,
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(config.sample_ratio),
    )
    use_insecure = os.getenv(
        "OTEL_EXPORTER_OTLP_INSECURE", "false"
    ).strip().lower() in ("1", "true", "yes")
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint, insecure=use_insecure)
        )
    )
    trace.set_tracer_provider(provider)
    logger.info("OTel tracing enabled: service=%s endpoint=%s",
                config.service_name, endpoint)

    if config.enable_metrics:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry import metrics

            reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=endpoint, insecure=use_insecure)
            )
            metrics.set_meter_provider(
                MeterProvider(resource=resource, metric_readers=[reader])
            )
        except Exception:
            logger.debug("OTel metrics setup failed", exc_info=True)


def get_tracer(name: str) -> Any:
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NullTracer()


def instrument_all(
    *,
    fastapi_app: Any | None = None,
    sqlalchemy_engine: Any | None = None,
    redis_client: Any | None = None,
) -> None:
    """Auto-instrument common frameworks if their OTel instrumentations exist."""
    if fastapi_app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            FastAPIInstrumentor.instrument_app(fastapi_app)
        except Exception:
            logger.debug("FastAPI OTel instrumentation unavailable", exc_info=True)
    if sqlalchemy_engine is not None:
        try:
            from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
            SQLAlchemyInstrumentor().instrument(engine=sqlalchemy_engine)
        except Exception:
            logger.debug("SQLAlchemy OTel instrumentation unavailable", exc_info=True)
    if redis_client is not None:
        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            RedisInstrumentor().instrument()
        except Exception:
            logger.debug("Redis OTel instrumentation unavailable", exc_info=True)
    try:
        from opentelemetry.instrumentation.grpc import GrpcAioInstrumentorServer
        GrpcAioInstrumentorServer().instrument()
    except Exception:
        logger.debug("gRPC server OTel instrumentation unavailable", exc_info=True)


class _NullTracer:
    def start_as_current_span(self, *args: Any, **kwargs: Any) -> Any:
        class _Span:
            def __enter__(self) -> "_Span":
                return self

            def __exit__(self, *_a: Any) -> bool:
                return False

            def set_attribute(self, *_a: Any, **_kw: Any) -> None:
                return None
        return _Span()

    def start_span(self, *_args: Any, **_kwargs: Any) -> Any:
        return self.start_as_current_span()


__all__ = [
    "TelemetryConfig",
    "get_tracer",
    "instrument_all",
    "setup_otel",
]
