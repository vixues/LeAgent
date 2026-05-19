"""Event bus protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Protocol, runtime_checkable
from uuid import uuid4


@dataclass(slots=True)
class EventEnvelope:
    """Wraps every event published on the bus.

    Carries optional trace context (``traceparent``) so consumers can link
    spans across the transport, and a tenant id so multi-tenant deployments
    can scope fan-out.
    """

    topic: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    traceparent: str | None = None
    tenant_id: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "topic": self.topic,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "traceparent": self.traceparent,
            "tenant_id": self.tenant_id,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventEnvelope":
        return cls(
            topic=data["topic"],
            payload=data.get("payload", {}),
            event_id=data.get("event_id") or str(uuid4()),
            timestamp=data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            traceparent=data.get("traceparent"),
            tenant_id=data.get("tenant_id"),
            source=data.get("source"),
        )


@runtime_checkable
class Subscriber(Protocol):
    """Async iterable of envelopes received on subscribed topics."""

    def __aiter__(self) -> AsyncIterator[EventEnvelope]: ...
    async def aclose(self) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    """Duck-typed event bus interface."""

    async def publish(self, envelope: EventEnvelope) -> None: ...
    async def subscribe(self, *topics: str) -> Subscriber: ...
    async def aclose(self) -> None: ...


__all__ = ["EventBus", "EventEnvelope", "Subscriber"]
