"""Composable middleware pipeline for tool execution.

Replaces the hardcoded permission/rate-limit/telemetry sequence in
ToolExecutor.execute() with a pluggable chain. Each middleware receives
the call context and a ``next`` coroutine; it can inspect/mutate params,
short-circuit with an early result, or wrap the downstream call with
timing/logging/error-handling.

Callers (agents, workflows, cron) inject custom middleware at construction
time. The default pipeline provides: permission enforcement, rate limiting,
telemetry recording, and circuit-breaker protection.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

import structlog

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from leagent.tools.base import ToolContext, ToolResult
    from leagent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


@dataclass
class MiddlewareContext:
    """Immutable bag of per-call metadata available to every middleware."""

    tool_name: str
    parameters: dict[str, Any]
    call_id: str
    tool_context: "ToolContext"
    registry: "ToolRegistry"
    extra: dict[str, Any] = field(default_factory=dict)


class ToolMiddleware(Protocol):
    """Protocol for tool execution middleware."""

    async def __call__(
        self,
        ctx: MiddlewareContext,
        next_fn: "Callable[[MiddlewareContext], Awaitable[ToolResult]]",
    ) -> "ToolResult":
        ...


class PermissionMiddleware:
    """Enforces tool permission rules (deny/allow/ask)."""

    def __init__(self, permission_context: Any | None = None) -> None:
        self._permission_context = permission_context

    async def __call__(
        self,
        ctx: MiddlewareContext,
        next_fn: "Callable[[MiddlewareContext], Awaitable[ToolResult]]",
    ) -> "ToolResult":
        from leagent.tools.base import ToolResult, check_tool_permission

        if self._permission_context is None:
            return await next_fn(ctx)

        tool = ctx.registry.get(ctx.tool_name)
        perm = check_tool_permission(
            tool, ctx.parameters, self._permission_context,
            tool_context=ctx.tool_context,
        )
        if not perm.allowed:
            return ToolResult.fail(f"Permission denied: {perm.reason}")
        if perm.updated_params:
            ctx.parameters = perm.updated_params
        return await next_fn(ctx)


class RateLimitMiddleware:
    """Applies per-user rate limiting from environment configuration."""

    async def __call__(
        self,
        ctx: MiddlewareContext,
        next_fn: "Callable[[MiddlewareContext], Awaitable[ToolResult]]",
    ) -> "ToolResult":
        from leagent.tools.base import ToolResult
        from leagent.tools.rate_limit import tool_rate_limit_from_env

        rate_lim, _ = tool_rate_limit_from_env()
        if rate_lim is not None:
            uid = (getattr(ctx.tool_context, "user_id", None) or "anon")[:200]
            if not rate_lim.allow(f"{uid}\x00{ctx.tool_name}"):
                return ToolResult.fail(
                    "Tool rate limit exceeded for this user; retry shortly."
                )
        return await next_fn(ctx)


class TelemetryMiddleware:
    """Records execution timing and emits structured logs."""

    async def __call__(
        self,
        ctx: MiddlewareContext,
        next_fn: "Callable[[MiddlewareContext], Awaitable[ToolResult]]",
    ) -> "ToolResult":
        from leagent_core.telemetry.otel import get_tracer

        tracer = get_tracer("leagent.tools.executor")
        with tracer.start_as_current_span("agent.tool") as span:
            if hasattr(span, "set_attribute"):
                span.set_attribute("tool.name", ctx.tool_name)
                span.set_attribute("tool.call_id", ctx.call_id)
            result = await next_fn(ctx)
        return result


class CapabilityGuardMiddleware:
    """Blocks tools whose capabilities are not in the allowed set."""

    def __init__(self, allowed_capabilities: set[str] | None = None) -> None:
        self._allowed = allowed_capabilities

    async def __call__(
        self,
        ctx: MiddlewareContext,
        next_fn: "Callable[[MiddlewareContext], Awaitable[ToolResult]]",
    ) -> "ToolResult":
        if self._allowed is None:
            return await next_fn(ctx)

        from leagent.tools.base import ToolResult

        tool = ctx.registry.get(ctx.tool_name)
        tool_caps = getattr(tool, "capabilities", set())
        if tool_caps and not tool_caps.issubset(self._allowed):
            blocked = tool_caps - self._allowed
            return ToolResult.fail(
                f"Tool '{ctx.tool_name}' requires capabilities {blocked} "
                f"not in allowed set {self._allowed}"
            )
        return await next_fn(ctx)


class CircuitBreakerMiddleware:
    """Simple circuit breaker that opens after consecutive failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def __call__(
        self,
        ctx: MiddlewareContext,
        next_fn: "Callable[[MiddlewareContext], Awaitable[ToolResult]]",
    ) -> "ToolResult":
        from leagent.tools.base import ToolResult

        async with self._lock:
            now = time.monotonic()
            open_until = self._open_until.get(ctx.tool_name, 0.0)
            if now < open_until:
                return ToolResult.fail(
                    f"Circuit breaker open for '{ctx.tool_name}'; "
                    f"retrying in {open_until - now:.0f}s"
                )

        result = await next_fn(ctx)
        async with self._lock:
            now = time.monotonic()
            if result.success:
                self._failures.pop(ctx.tool_name, None)
                self._open_until.pop(ctx.tool_name, None)
            else:
                count = self._failures.get(ctx.tool_name, 0) + 1
                self._failures[ctx.tool_name] = count
                if count >= self._failure_threshold:
                    self._open_until[ctx.tool_name] = now + self._recovery_timeout
                    logger.warning(
                        "circuit_breaker_open",
                        tool=ctx.tool_name,
                        failures=count,
                        recovery_sec=self._recovery_timeout,
                    )
        return result


class MiddlewarePipeline:
    """Ordered chain of middleware that wraps tool execution."""

    def __init__(self, middlewares: list[ToolMiddleware] | None = None) -> None:
        self._middlewares: list[ToolMiddleware] = list(middlewares or [])

    def add(self, middleware: ToolMiddleware) -> "MiddlewarePipeline":
        self._middlewares.append(middleware)
        return self

    def prepend(self, middleware: ToolMiddleware) -> "MiddlewarePipeline":
        self._middlewares.insert(0, middleware)
        return self

    async def execute(
        self,
        ctx: MiddlewareContext,
        final: "Callable[[MiddlewareContext], Awaitable[ToolResult]]",
    ) -> "ToolResult":
        """Run the middleware chain, ending with ``final``."""
        chain = final
        for mw in reversed(self._middlewares):
            chain = _wrap(mw, chain)
        return await chain(ctx)


def _wrap(
    mw: ToolMiddleware,
    next_fn: "Callable[[MiddlewareContext], Awaitable[ToolResult]]",
) -> "Callable[[MiddlewareContext], Awaitable[ToolResult]]":
    async def _call(ctx: MiddlewareContext) -> "ToolResult":
        return await mw(ctx, next_fn)
    return _call


def build_default_pipeline(
    *,
    permission_context: Any | None = None,
    allowed_capabilities: set[str] | None = None,
    enable_circuit_breaker: bool = True,
) -> MiddlewarePipeline:
    """Assemble the standard middleware stack."""
    pipeline = MiddlewarePipeline()
    pipeline.add(PermissionMiddleware(permission_context))
    pipeline.add(RateLimitMiddleware())
    if allowed_capabilities is not None:
        pipeline.add(CapabilityGuardMiddleware(allowed_capabilities))
    pipeline.add(TelemetryMiddleware())
    if enable_circuit_breaker:
        pipeline.add(CircuitBreakerMiddleware())
    return pipeline


__all__ = [
    "MiddlewareContext",
    "ToolMiddleware",
    "MiddlewarePipeline",
    "PermissionMiddleware",
    "RateLimitMiddleware",
    "TelemetryMiddleware",
    "CapabilityGuardMiddleware",
    "CircuitBreakerMiddleware",
    "build_default_pipeline",
]
