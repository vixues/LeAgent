"""Base service abstractions and factory pattern."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from leagent.config.settings import Settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Service")


class ServiceType(str, Enum):
    """Enumeration of available service types."""

    DATABASE = "database"
    CACHE = "cache"
    AUTH = "auth"
    CHAT = "chat"
    VARIABLE = "variable"
    JOB_QUEUE = "job_queue"
    FILE_STORE = "file_store"
    EVENT = "event"
    WEBHOOK = "webhook"
    LLM = "llm"


class ServiceState(str, Enum):
    """Service lifecycle states."""

    UNINITIALIZED = "uninitialized"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class Service(ABC):
    """Abstract base class for all services.

    Provides a consistent interface for service lifecycle management,
    health checks, and configuration.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state = ServiceState.UNINITIALIZED
        self._error: Exception | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique service name."""
        ...

    @property
    def state(self) -> ServiceState:
        """Return current service state."""
        return self._state

    @property
    def is_ready(self) -> bool:
        """Check if service is ready to accept requests."""
        return self._state == ServiceState.READY

    @property
    def is_healthy(self) -> bool:
        """Check if service is in a healthy state."""
        return self._state in (ServiceState.READY, ServiceState.DEGRADED)

    @property
    def last_error(self) -> Exception | None:
        """Return the last error that occurred."""
        return self._error

    async def start(self) -> None:
        """Start the service.

        Override _do_start() to provide service-specific initialization.
        """
        if self._state == ServiceState.READY:
            logger.debug("%s already started", self.name)
            return

        self._state = ServiceState.STARTING
        logger.info("Starting %s...", self.name)

        try:
            await self._do_start()
            self._state = ServiceState.READY
            self._error = None
            logger.info("%s started successfully", self.name)
        except Exception as e:
            self._state = ServiceState.ERROR
            self._error = e
            logger.error("Failed to start %s: %s", self.name, e)
            raise

    async def stop(self) -> None:
        """Stop the service gracefully.

        Override _do_stop() to provide service-specific cleanup.
        """
        if self._state in (ServiceState.STOPPED, ServiceState.UNINITIALIZED):
            logger.debug("%s already stopped", self.name)
            return

        self._state = ServiceState.STOPPING
        logger.info("Stopping %s...", self.name)

        try:
            await self._do_stop()
            self._state = ServiceState.STOPPED
            logger.info("%s stopped successfully", self.name)
        except Exception as e:
            self._state = ServiceState.ERROR
            self._error = e
            logger.error("Error stopping %s: %s", self.name, e)

    async def health_check(self) -> dict[str, Any]:
        """Perform a health check and return status details.

        Override _do_health_check() for service-specific checks.
        """
        base_status = {
            "service": self.name,
            "state": self._state.value,
            "healthy": self.is_healthy,
        }

        if self._error:
            base_status["error"] = str(self._error)

        try:
            if self._state == ServiceState.READY:
                extra = await self._do_health_check()
                base_status.update(extra)
        except Exception as e:
            base_status["healthy"] = False
            base_status["error"] = str(e)

        return base_status

    async def _do_start(self) -> None:
        """Override to implement service-specific startup logic."""
        pass

    async def _do_stop(self) -> None:
        """Override to implement service-specific shutdown logic."""
        pass

    async def _do_health_check(self) -> dict[str, Any]:
        """Override to implement service-specific health check logic."""
        return {}


class ServiceFactory(Generic[T]):
    """Factory for creating and managing service instances.

    Implements the factory pattern for lazy service instantiation
    with caching and configuration injection.
    """

    _instances: dict[str, Service] = {}
    _factories: dict[ServiceType, type[Service]] = {}

    @classmethod
    def register(cls, service_type: ServiceType, factory: type[Service]) -> None:
        """Register a service factory for a given type."""
        cls._factories[service_type] = factory
        logger.debug("Registered factory for %s", service_type.value)

    @classmethod
    def create(
        cls,
        service_type: ServiceType,
        settings: Settings,
        *,
        singleton: bool = True,
    ) -> Service:
        """Create or retrieve a service instance.

        Args:
            service_type: The type of service to create
            settings: Application settings
            singleton: If True, returns cached instance if available

        Returns:
            The service instance

        Raises:
            ValueError: If no factory registered for the service type
        """
        if singleton and service_type.value in cls._instances:
            return cls._instances[service_type.value]

        if service_type not in cls._factories:
            raise ValueError(f"No factory registered for {service_type.value}")

        factory = cls._factories[service_type]
        instance = factory(settings)

        if singleton:
            cls._instances[service_type.value] = instance

        return instance

    @classmethod
    def get(cls, service_type: ServiceType) -> Service | None:
        """Get an existing service instance without creating."""
        return cls._instances.get(service_type.value)

    @classmethod
    def clear(cls) -> None:
        """Clear all cached service instances."""
        cls._instances.clear()

    @classmethod
    async def stop_all(cls) -> None:
        """Stop all registered service instances."""
        for name, service in cls._instances.items():
            try:
                await service.stop()
            except Exception as e:
                logger.error("Error stopping %s: %s", name, e)
        cls._instances.clear()


def service_factory(service_type: ServiceType):
    """Decorator to register a service class with the factory."""

    def decorator(cls: type[T]) -> type[T]:
        ServiceFactory.register(service_type, cls)
        return cls

    return decorator
