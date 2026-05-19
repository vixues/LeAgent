"""Services package for LeAgent.

This package provides core service abstractions and implementations for:
- Caching (Redis with in-memory fallback)
- Chat session and message management
- Global variables with encryption
- Job queue with priority support
- File storage (MinIO)
- Event pub/sub and webhooks
"""

from leagent.services.base import (
    Service,
    ServiceFactory,
    ServiceState,
    ServiceType,
    service_factory,
)

__all__ = [
    "Service",
    "ServiceFactory",
    "ServiceState",
    "ServiceType",
    "service_factory",
]
