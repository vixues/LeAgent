from __future__ import annotations

import pytest

from leagent.tools.base import ToolContext, ToolResult
from leagent.tools.pipeline import (
    CircuitBreakerMiddleware,
    MiddlewareContext,
    build_default_pipeline,
)


class _Registry:
    def get(self, name: str) -> object:
        return object()


def _ctx() -> MiddlewareContext:
    return MiddlewareContext(
        tool_name="unstable",
        parameters={},
        call_id="call-1",
        tool_context=ToolContext(user_id="u", session_id="s"),
        registry=_Registry(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreakerMiddleware(failure_threshold=2, recovery_timeout=60.0)
    calls = 0

    async def failing(_: MiddlewareContext) -> ToolResult:
        nonlocal calls
        calls += 1
        return ToolResult.fail("boom")

    first = await breaker(_ctx(), failing)
    second = await breaker(_ctx(), failing)
    third = await breaker(_ctx(), failing)

    assert first.success is False
    assert second.success is False
    assert third.success is False
    assert "Circuit breaker open" in (third.error or "")
    assert calls == 2


def test_default_pipeline_enables_circuit_breaker() -> None:
    pipeline = build_default_pipeline()

    assert any(
        isinstance(mw, CircuitBreakerMiddleware)
        for mw in pipeline._middlewares  # noqa: SLF001 - verifies public factory wiring
    )
