"""Circuit breaker utilities for provider routing.

The breaker tracks request outcomes per provider and keeps transient outages
from repeatedly consuming user requests. It is intentionally in-memory; provider
metadata can still expose the current snapshot to APIs and the UI.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerConfig:
    """Runtime thresholds for provider circuit breakers."""

    failure_threshold: int = 4
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    error_rate_threshold: float = 0.6
    min_requests: int = 10


@dataclass
class CircuitBreakerSnapshot:
    """Serializable state for API responses and metadata."""

    state: str
    consecutive_failures: int
    consecutive_successes: int
    request_count: int
    failure_count: int
    opened_at: float | None = None
    last_error: str | None = None


@dataclass
class CircuitBreaker:
    """Simple per-provider circuit breaker."""

    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    request_count: int = 0
    failure_count: int = 0
    opened_at: float | None = None
    last_error: str | None = None

    def is_available(self) -> bool:
        """Return whether a provider should be considered for routing."""
        if self.state is CircuitState.CLOSED:
            return True
        if self.state is CircuitState.HALF_OPEN:
            return True
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at >= self.config.timeout_seconds:
            self.state = CircuitState.HALF_OPEN
            self.consecutive_successes = 0
            return True
        return False

    def record_success(self) -> None:
        """Record a successful request or health probe."""
        self.request_count += 1
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        self.last_error = None
        if self.state is CircuitState.HALF_OPEN:
            if self.consecutive_successes >= self.config.success_threshold:
                self.close()
        elif self.state is CircuitState.OPEN:
            self.state = CircuitState.HALF_OPEN

    def record_failure(self, error: str | None = None) -> None:
        """Record a failed provider request."""
        self.request_count += 1
        self.failure_count += 1
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_error = error

        if self.state is CircuitState.HALF_OPEN:
            self.open(error)
            return

        if self.consecutive_failures >= self.config.failure_threshold:
            self.open(error)
            return

        if self.request_count >= self.config.min_requests:
            error_rate = self.failure_count / max(self.request_count, 1)
            if error_rate >= self.config.error_rate_threshold:
                self.open(error)

    def open(self, error: str | None = None) -> None:
        """Open the circuit and suppress routing until timeout expires."""
        self.state = CircuitState.OPEN
        self.opened_at = time.time()
        self.last_error = error or self.last_error

    def close(self) -> None:
        """Close the circuit after successful recovery."""
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.request_count = 0
        self.failure_count = 0
        self.opened_at = None
        self.last_error = None

    def snapshot(self) -> CircuitBreakerSnapshot:
        """Return a serializable view of current state."""
        return CircuitBreakerSnapshot(
            state=self.state.value,
            consecutive_failures=self.consecutive_failures,
            consecutive_successes=self.consecutive_successes,
            request_count=self.request_count,
            failure_count=self.failure_count,
            opened_at=self.opened_at,
            last_error=self.last_error,
        )
