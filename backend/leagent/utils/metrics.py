"""Prometheus metrics for LeAgent observability.

Provides comprehensive metrics collection for monitoring:
- HTTP request performance
- LLM service usage and latency
- Tool execution statistics
- Agent task tracking
- Workflow execution
- Active session monitoring
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match

if TYPE_CHECKING:
    from starlette.types import ASGIApp

P = ParamSpec("P")
R = TypeVar("R")


# Default buckets for different metric types
DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)
LLM_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
TOOL_DURATION_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0)
TASK_DURATION_BUCKETS = (1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0)
QUEUE_DEPTH_BUCKETS = (0, 1, 2, 5, 10, 25, 50, 100, 250, 500, 1000)


class LeAgentMetrics:
    """Central metrics registry for LeAgent.
    
    All metrics are prefixed with 'leagent_' for easy identification.
    
    Usage:
        metrics = LeAgentMetrics()
        
        # Record tool execution
        with metrics.tool_execution_timer("pdf_reader"):
            result = await tool.run()
        
        # Record LLM request
        metrics.record_llm_request("chat", "qwen-plus", 0.5, 1500, 200)
        
        # Track sessions
        metrics.active_sessions.inc()
        metrics.active_sessions.dec()
    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Initialize metrics with optional custom registry.
        
        Args:
            registry: Custom CollectorRegistry. Uses default if None.
        """
        self._registry = registry or REGISTRY
        self._init_metrics()

    def _init_metrics(self) -> None:
        """Initialize all Prometheus metrics."""
        
        # HTTP request metrics
        self.http_request_duration_seconds = Histogram(
            "leagent_http_request_duration_seconds",
            "HTTP request duration in seconds",
            labelnames=["method", "endpoint", "status_code"],
            buckets=DURATION_BUCKETS,
            registry=self._registry,
        )
        
        self.http_request_total = Counter(
            "leagent_http_request_total",
            "Total HTTP requests",
            labelnames=["method", "endpoint", "status_code"],
            registry=self._registry,
        )
        
        self.http_request_size_bytes = Histogram(
            "leagent_http_request_size_bytes",
            "HTTP request body size in bytes",
            labelnames=["method", "endpoint"],
            buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
            registry=self._registry,
        )
        
        self.http_response_size_bytes = Histogram(
            "leagent_http_response_size_bytes",
            "HTTP response body size in bytes",
            labelnames=["method", "endpoint"],
            buckets=(100, 1000, 10000, 100000, 1000000, 10000000),
            registry=self._registry,
        )

        # Tool execution metrics
        self.tool_execution_duration_seconds = Histogram(
            "leagent_tool_execution_duration_seconds",
            "Tool execution duration in seconds",
            labelnames=["tool_name"],
            buckets=TOOL_DURATION_BUCKETS,
            registry=self._registry,
        )
        
        self.tool_execution_total = Counter(
            "leagent_tool_execution_total",
            "Total tool executions",
            labelnames=["tool_name", "status"],
            registry=self._registry,
        )
        
        self.tool_execution_errors_total = Counter(
            "leagent_tool_execution_errors_total",
            "Total tool execution errors",
            labelnames=["tool_name", "error_type"],
            registry=self._registry,
        )

        # LLM request metrics
        self.llm_request_duration_seconds = Histogram(
            "leagent_llm_request_duration_seconds",
            "LLM request duration in seconds",
            labelnames=["provider", "model", "tier"],
            buckets=LLM_DURATION_BUCKETS,
            registry=self._registry,
        )
        
        self.llm_request_total = Counter(
            "leagent_llm_request_total",
            "Total LLM requests",
            labelnames=["provider", "model", "tier", "status"],
            registry=self._registry,
        )
        
        self.llm_tokens_total = Counter(
            "leagent_llm_tokens_total",
            "Total LLM tokens processed",
            labelnames=["provider", "model", "tier", "token_type"],
            registry=self._registry,
        )
        
        self.llm_streaming_chunks_total = Counter(
            "leagent_llm_streaming_chunks_total",
            "Total LLM streaming chunks received",
            labelnames=["provider", "model"],
            registry=self._registry,
        )

        self.llm_stream_ttfb_seconds = Histogram(
            "leagent_llm_stream_ttfb_seconds",
            "Time to first streamed LLM chunk in seconds",
            labelnames=["provider", "model", "tier"],
            buckets=LLM_DURATION_BUCKETS,
            registry=self._registry,
        )
        
        self.llm_errors_total = Counter(
            "leagent_llm_errors_total",
            "Total LLM errors",
            labelnames=["provider", "model", "error_type"],
            registry=self._registry,
        )

        # Agent task metrics
        self.agent_task_duration_seconds = Histogram(
            "leagent_agent_task_duration_seconds",
            "Agent task duration in seconds",
            labelnames=["task_type"],
            buckets=TASK_DURATION_BUCKETS,
            registry=self._registry,
        )
        
        self.agent_task_total = Counter(
            "leagent_agent_task_total",
            "Total agent tasks",
            labelnames=["task_type", "status"],
            registry=self._registry,
        )
        
        self.agent_task_steps_total = Counter(
            "leagent_agent_task_steps_total",
            "Total steps taken in agent tasks",
            labelnames=["task_type", "step_type"],
            registry=self._registry,
        )

        self.agent_turn_phase_duration_seconds = Histogram(
            "leagent_agent_turn_phase_duration_seconds",
            "Agent chat turn phase duration in seconds",
            labelnames=["phase", "status"],
            buckets=DURATION_BUCKETS + (30.0, 60.0),
            registry=self._registry,
        )

        self.agent_stream_queue_depth = Gauge(
            "leagent_agent_stream_queue_depth",
            "Current queued stream events waiting to be consumed",
            labelnames=["queue"],
            registry=self._registry,
        )

        self.agent_stream_queue_depth_observed = Histogram(
            "leagent_agent_stream_queue_depth_observed",
            "Observed stream queue depth when events are enqueued",
            labelnames=["queue"],
            buckets=QUEUE_DEPTH_BUCKETS,
            registry=self._registry,
        )

        self.sandbox_execution_duration_seconds = Histogram(
            "leagent_sandbox_execution_duration_seconds",
            "Sandboxed Python execution duration in seconds",
            labelnames=["status", "isolation_mode"],
            buckets=TOOL_DURATION_BUCKETS,
            registry=self._registry,
        )

        self.sandbox_execution_total = Counter(
            "leagent_sandbox_execution_total",
            "Total sandboxed Python executions",
            labelnames=["status", "isolation_mode"],
            registry=self._registry,
        )

        # Workflow execution metrics
        self.workflow_execution_total = Counter(
            "leagent_workflow_execution_total",
            "Total workflow executions",
            labelnames=["workflow_name", "status"],
            registry=self._registry,
        )
        
        self.workflow_execution_duration_seconds = Histogram(
            "leagent_workflow_execution_duration_seconds",
            "Workflow execution duration in seconds",
            labelnames=["workflow_name"],
            buckets=TASK_DURATION_BUCKETS,
            registry=self._registry,
        )
        
        self.workflow_node_execution_total = Counter(
            "leagent_workflow_node_execution_total",
            "Total workflow node executions",
            labelnames=["workflow_name", "node_type", "status"],
            registry=self._registry,
        )

        # Session metrics
        self.active_sessions_gauge = Gauge(
            "leagent_active_sessions",
            "Number of active sessions",
            labelnames=["channel"],
            registry=self._registry,
        )
        
        self.active_chat_connections = Gauge(
            "leagent_active_chat_connections",
            "Number of active chat WebSocket connections",
            registry=self._registry,
        )
        
        self.session_duration_seconds = Histogram(
            "leagent_session_duration_seconds",
            "Session duration in seconds",
            labelnames=["channel"],
            buckets=TASK_DURATION_BUCKETS,
            registry=self._registry,
        )

        # Memory metrics
        self.memory_usage_bytes = Gauge(
            "leagent_memory_usage_bytes",
            "Memory usage in bytes",
            labelnames=["memory_type"],
            registry=self._registry,
        )
        
        self.memory_items_total = Gauge(
            "leagent_memory_items_total",
            "Total items in memory stores",
            labelnames=["memory_type"],
            registry=self._registry,
        )

        # Database metrics
        self.db_query_duration_seconds = Histogram(
            "leagent_db_query_duration_seconds",
            "Database query duration in seconds",
            labelnames=["operation", "table"],
            buckets=DURATION_BUCKETS,
            registry=self._registry,
        )
        
        self.db_connection_pool_size = Gauge(
            "leagent_db_connection_pool_size",
            "Database connection pool size",
            labelnames=["state"],
            registry=self._registry,
        )

        # Cache metrics
        self.cache_hits_total = Counter(
            "leagent_cache_hits_total",
            "Total cache hits",
            labelnames=["cache_name"],
            registry=self._registry,
        )
        
        self.cache_misses_total = Counter(
            "leagent_cache_misses_total",
            "Total cache misses",
            labelnames=["cache_name"],
            registry=self._registry,
        )
        
        self.cache_size_bytes = Gauge(
            "leagent_cache_size_bytes",
            "Cache size in bytes",
            labelnames=["cache_name"],
            registry=self._registry,
        )

        self.cache_entries = Gauge(
            "leagent_cache_entries",
            "Number of entries in logical caches",
            labelnames=["cache_name"],
            registry=self._registry,
        )

        # Application info
        self.app_info = Info(
            "leagent_app",
            "LeAgent application information",
            registry=self._registry,
        )

    def set_app_info(self, version: str, environment: str, **extra: str) -> None:
        """Set application info labels."""
        self.app_info.info({
            "version": version,
            "environment": environment,
            **extra,
        })

    def tool_execution_timer(self, tool_name: str) -> "MetricsTimer":
        """Context manager for timing tool execution.
        
        Usage:
            with metrics.tool_execution_timer("pdf_reader") as timer:
                result = await tool.run()
                timer.set_status("success" if result.success else "failure")
        """
        return MetricsTimer(
            histogram=self.tool_execution_duration_seconds,
            counter=self.tool_execution_total,
            labels={"tool_name": tool_name},
        )

    def llm_request_timer(
        self,
        provider: str,
        model: str,
        tier: str = "default",
    ) -> "MetricsTimer":
        """Context manager for timing LLM requests.
        
        Usage:
            with metrics.llm_request_timer("openai", "gpt-4", "chat") as timer:
                response = await llm.complete(messages)
                timer.set_status("success")
        """
        return MetricsTimer(
            histogram=self.llm_request_duration_seconds,
            counter=self.llm_request_total,
            labels={"provider": provider, "model": model, "tier": tier},
        )

    def agent_task_timer(self, task_type: str = "default") -> "MetricsTimer":
        """Context manager for timing agent tasks.
        
        Usage:
            with metrics.agent_task_timer("chat") as timer:
                await agent.process_task(task)
                timer.set_status("completed")
        """
        return MetricsTimer(
            histogram=self.agent_task_duration_seconds,
            counter=self.agent_task_total,
            labels={"task_type": task_type},
        )

    def workflow_execution_timer(self, workflow_name: str) -> "MetricsTimer":
        """Context manager for timing workflow execution."""
        return MetricsTimer(
            histogram=self.workflow_execution_duration_seconds,
            counter=self.workflow_execution_total,
            labels={"workflow_name": workflow_name},
        )

    def record_llm_tokens(
        self,
        provider: str,
        model: str,
        tier: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Record LLM token usage."""
        self.llm_tokens_total.labels(
            provider=provider,
            model=model,
            tier=tier,
            token_type="prompt",
        ).inc(prompt_tokens)
        
        self.llm_tokens_total.labels(
            provider=provider,
            model=model,
            tier=tier,
            token_type="completion",
        ).inc(completion_tokens)

    def record_llm_request(
        self,
        provider: str,
        model: str,
        tier: str,
        duration: float,
        prompt_tokens: int,
        completion_tokens: int,
        status: str = "success",
    ) -> None:
        """Record complete LLM request metrics."""
        self.llm_request_duration_seconds.labels(
            provider=provider,
            model=model,
            tier=tier,
        ).observe(duration)
        
        self.llm_request_total.labels(
            provider=provider,
            model=model,
            tier=tier,
            status=status,
        ).inc()
        
        self.record_llm_tokens(provider, model, tier, prompt_tokens, completion_tokens)

    def record_llm_stream_ttfb(
        self,
        provider: str,
        model: str,
        tier: str,
        ttfb_seconds: float,
    ) -> None:
        """Record time to first streamed model chunk."""
        self.llm_stream_ttfb_seconds.labels(
            provider=provider,
            model=model,
            tier=tier,
        ).observe(max(0.0, ttfb_seconds))

    def record_tool_execution(
        self,
        tool_name: str,
        duration: float,
        success: bool,
        error_type: str | None = None,
    ) -> None:
        """Record tool execution metrics."""
        status = "success" if success else "failure"
        
        self.tool_execution_duration_seconds.labels(
            tool_name=tool_name,
        ).observe(duration)
        
        self.tool_execution_total.labels(
            tool_name=tool_name,
            status=status,
        ).inc()
        
        if not success and error_type:
            self.tool_execution_errors_total.labels(
                tool_name=tool_name,
                error_type=error_type,
            ).inc()

    def record_agent_task(
        self,
        task_type: str,
        duration: float,
        status: str,
    ) -> None:
        """Record agent task/turn duration and status."""
        self.agent_task_duration_seconds.labels(task_type=task_type).observe(duration)
        self.agent_task_total.labels(task_type=task_type, status=status).inc()

    def record_agent_turn_phase(
        self,
        phase: str,
        duration: float,
        *,
        status: str = "success",
    ) -> None:
        """Record latency for a phase in the chat/agent hot path."""
        self.agent_turn_phase_duration_seconds.labels(
            phase=phase,
            status=status,
        ).observe(max(0.0, duration))

    def record_stream_queue_depth(self, queue: str, depth: int) -> None:
        """Record the current depth of a stream event queue."""
        depth = max(0, int(depth))
        self.agent_stream_queue_depth.labels(queue=queue).set(depth)
        self.agent_stream_queue_depth_observed.labels(queue=queue).observe(depth)

    def record_db_query(
        self,
        operation: str,
        table: str,
        duration: float,
    ) -> None:
        """Record DB operation latency."""
        self.db_query_duration_seconds.labels(
            operation=operation,
            table=table,
        ).observe(max(0.0, duration))

    def record_cache_event(
        self,
        cache_name: str,
        *,
        hit: bool,
        entries: int | None = None,
    ) -> None:
        """Record cache hit/miss and optional entry count."""
        if hit:
            self.cache_hits_total.labels(cache_name=cache_name).inc()
        else:
            self.cache_misses_total.labels(cache_name=cache_name).inc()
        if entries is not None:
            self.cache_entries.labels(cache_name=cache_name).set(max(0, int(entries)))

    def record_sandbox_execution(
        self,
        *,
        status: str,
        isolation_mode: str,
        duration: float,
    ) -> None:
        """Record sandbox execution status and latency."""
        labels = {"status": status, "isolation_mode": isolation_mode}
        self.sandbox_execution_duration_seconds.labels(**labels).observe(duration)
        self.sandbox_execution_total.labels(**labels).inc()

    def generate_metrics(self) -> bytes:
        """Generate Prometheus metrics output."""
        return generate_latest(self._registry)


class MetricsTimer:
    """Context manager for timing operations with metrics.
    
    Automatically records duration to histogram and increments counter.
    Status can be set during execution for accurate labeling.
    """

    def __init__(
        self,
        histogram: Histogram,
        counter: Counter | None = None,
        labels: dict[str, str] | None = None,
    ) -> None:
        self._histogram = histogram
        self._counter = counter
        self._labels = labels or {}
        self._status = "success"
        self._start_time: float = 0

    def set_status(self, status: str) -> None:
        """Set the status label for this timer."""
        self._status = status

    def __enter__(self) -> "MetricsTimer":
        self._start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        duration = time.perf_counter() - self._start_time
        
        if exc_type is not None:
            self._status = "error"
        
        histogram_labels = {k: v for k, v in self._labels.items() if k != "status"}
        self._histogram.labels(**histogram_labels).observe(duration)
        
        if self._counter is not None:
            counter_labels = {**self._labels, "status": self._status}
            self._counter.labels(**counter_labels).inc()

    async def __aenter__(self) -> "MetricsTimer":
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.__exit__(exc_type, exc_val, exc_tb)


class MetricsMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for automatic HTTP metrics collection.
    
    Collects:
    - Request duration
    - Request/response sizes
    - Status codes by endpoint
    
    Usage:
        from leagent.utils.metrics import MetricsMiddleware, get_metrics
        
        app.add_middleware(MetricsMiddleware, metrics=get_metrics())
    """

    def __init__(
        self,
        app: "ASGIApp",
        metrics: LeAgentMetrics | None = None,
        exclude_paths: set[str] | None = None,
    ) -> None:
        """Initialize the middleware.
        
        Args:
            app: ASGI application.
            metrics: LeAgentMetrics instance.
            exclude_paths: Paths to exclude from metrics (e.g., /metrics, /health).
        """
        super().__init__(app)
        self._metrics = metrics or get_metrics()
        self._exclude_paths = exclude_paths or {"/metrics", "/health", "/healthz"}

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Any],
    ) -> Response:
        """Process request and record metrics."""
        path = request.url.path
        
        if path in self._exclude_paths:
            return await call_next(request)
        
        method = request.method
        
        endpoint = self._get_endpoint_pattern(request) or path
        
        request_size = 0
        if content_length := request.headers.get("content-length"):
            try:
                request_size = int(content_length)
            except ValueError:
                pass
        
        start_time = time.perf_counter()
        
        response: Response = await call_next(request)
        
        duration = time.perf_counter() - start_time
        status_code = str(response.status_code)
        
        self._metrics.http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).observe(duration)
        
        self._metrics.http_request_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).inc()
        
        if request_size > 0:
            self._metrics.http_request_size_bytes.labels(
                method=method,
                endpoint=endpoint,
            ).observe(request_size)
        
        response_size = 0
        if content_length := response.headers.get("content-length"):
            try:
                response_size = int(content_length)
            except ValueError:
                pass
        
        if response_size > 0:
            self._metrics.http_response_size_bytes.labels(
                method=method,
                endpoint=endpoint,
            ).observe(response_size)
        
        return response

    def _get_endpoint_pattern(self, request: Request) -> str | None:
        """Extract the route pattern from request for consistent labeling.
        
        Converts /api/v1/users/123 to /api/v1/users/{user_id}
        """
        app = request.app
        
        if not hasattr(app, "routes"):
            return None
        
        for route in app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                if hasattr(route, "path"):
                    return route.path
        
        return None


def track_metrics(
    metric_type: str = "custom",
    labels: dict[str, str] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to track function execution metrics.
    
    Usage:
        @track_metrics("tool_execution", {"tool_name": "pdf_reader"})
        async def read_pdf(path: str) -> dict:
            ...
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            metrics = get_metrics()
            timer_labels = labels or {}
            
            if metric_type == "tool_execution":
                timer = metrics.tool_execution_timer(timer_labels.get("tool_name", func.__name__))
            elif metric_type == "llm_request":
                timer = metrics.llm_request_timer(
                    timer_labels.get("provider", "unknown"),
                    timer_labels.get("model", "unknown"),
                    timer_labels.get("tier", "default"),
                )
            else:
                timer = metrics.agent_task_timer(timer_labels.get("task_type", "default"))
            
            async with timer:
                return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            metrics = get_metrics()
            timer_labels = labels or {}
            
            if metric_type == "tool_execution":
                timer = metrics.tool_execution_timer(timer_labels.get("tool_name", func.__name__))
            else:
                timer = metrics.agent_task_timer(timer_labels.get("task_type", "default"))
            
            with timer:
                return func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]
    
    return decorator


_metrics_instance: LeAgentMetrics | None = None


def get_metrics() -> LeAgentMetrics:
    """Get the global LeAgentMetrics singleton.
    
    Returns:
        The shared LeAgentMetrics instance.
    """
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = LeAgentMetrics()
    return _metrics_instance


def reset_metrics() -> None:
    """Reset the global metrics instance (for testing)."""
    global _metrics_instance
    _metrics_instance = None
