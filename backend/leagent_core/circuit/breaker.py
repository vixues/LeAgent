"""Async circuit breaker.

Small in-process breaker (no external dep on ``pybreaker``) with the usual
three states: CLOSED → OPEN → HALF_OPEN → CLOSED. Tuned to wrap async calls
to LLM providers, MCP servers, and external HTTP APIs, where one flapping
dependency can exhaust the worker event loop if every request is allowed to
time out.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(RuntimeError):
    """Raised when the breaker rejects a call without attempting it."""


@dataclass(slots=True)
class _Stats:
    failures: int = 0
    successes: int = 0
    opened_at: float = 0.0


class CircuitBreaker:
    """Coroutine-safe circuit breaker.

    Parameters
    ----------
    name:
        Diagnostics label used in logs and metrics.
    failure_threshold:
        Consecutive failures in CLOSED state before opening.
    recovery_timeout:
        Seconds to stay OPEN before transitioning to HALF_OPEN.
    half_open_max_calls:
        Concurrent probes allowed in HALF_OPEN; a success closes, a failure
        re-opens.
    expected_exceptions:
        Exception classes that count as failures. Anything outside this tuple
        is re-raised and does **not** change state.
    """

    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        expected_exceptions: tuple[type[BaseException], ...] = (Exception,),
    ) -> None:
        self.name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls
        self._expected = expected_exceptions
        self._state = CircuitState.CLOSED
        self._stats = _Stats()
        self._lock = asyncio.Lock()
        self._half_open_sema = asyncio.Semaphore(half_open_max_calls)

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        await self._before_call()
        try:
            result = await func(*args, **kwargs)
        except self._expected as exc:
            await self._on_failure(exc)
            raise
        else:
            await self._on_success()
            return result

    async def _before_call(self) -> None:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._stats.opened_at >= self._recovery_timeout:
                    logger.info("circuit %s → HALF_OPEN", self.name)
                    self._state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerOpen(f"circuit '{self.name}' is open")
            if self._state == CircuitState.HALF_OPEN:
                if not self._half_open_sema.locked() or self._half_open_sema._value > 0:
                    # fall through - will acquire below
                    pass
        if self._state == CircuitState.HALF_OPEN:
            # Limit concurrency of probes.
            acquired = self._half_open_sema.locked() is False and await _try_acquire(
                self._half_open_sema
            )
            if not acquired:
                raise CircuitBreakerOpen(
                    f"circuit '{self.name}' half-open; probe slot busy"
                )

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("circuit %s → CLOSED", self.name)
                self._state = CircuitState.CLOSED
                self._half_open_sema = asyncio.Semaphore(self._half_open_max_calls)
            self._stats.failures = 0
            self._stats.successes += 1

    async def _on_failure(self, exc: BaseException) -> None:
        async with self._lock:
            self._stats.failures += 1
            if (
                self._state == CircuitState.CLOSED
                and self._stats.failures >= self._failure_threshold
            ):
                self._state = CircuitState.OPEN
                self._stats.opened_at = time.monotonic()
                logger.warning(
                    "circuit %s → OPEN (after %d failures; last error: %s)",
                    self.name, self._stats.failures, exc,
                )
            elif self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._stats.opened_at = time.monotonic()
                logger.warning("circuit %s → OPEN (half-open probe failed)", self.name)


async def _try_acquire(sema: asyncio.Semaphore) -> bool:
    try:
        await asyncio.wait_for(sema.acquire(), timeout=0.0)
        return True
    except asyncio.TimeoutError:
        return False


__all__ = ["CircuitBreaker", "CircuitBreakerOpen", "CircuitState"]
