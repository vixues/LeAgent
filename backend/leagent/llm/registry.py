"""Provider registry for LLM provider management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from leagent.exceptions.llm import LLMServiceError, ModelNotFoundError
from leagent.llm.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from leagent.llm.base import LLMProvider


def _endpoint_hostname_is_deepseek(endpoint: str) -> bool:
    """Return whether an endpoint points at DeepSeek's public API host."""
    host = (urlparse(endpoint).hostname or "").lower()
    return host == "api.deepseek.com" or host.endswith(".deepseek.com")


def _endpoint_hostname_is_dashscope(endpoint: str) -> bool:
    """Return whether an endpoint points at DashScope-compatible API hosts."""
    host = (urlparse(endpoint).hostname or "").lower()
    return host in {
        "dashscope.aliyuncs.com",
        "dashscope-intl.aliyuncs.com",
        "maas.aliyuncs.com",
    }


@dataclass
class ProviderInfo:
    """Information about a registered provider."""

    name: str
    provider: LLMProvider
    is_healthy: bool = True
    last_health_check: float = 0.0
    metadata: dict = field(default_factory=dict)
    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)


@dataclass
class HealthCheckResult:
    """Result of a provider health check."""

    provider_name: str
    is_healthy: bool
    latency_ms: float = 0.0
    error: str | None = None
    status: str = "unknown"
    ttfb_ms: float = 0.0
    error_category: str | None = None
    tested_model: str | None = None


class ProviderRegistry:
    """Registry for managing LLM providers.

    Features:
    - Register/unregister providers dynamically
    - Provider discovery
    - Connection testing and health checks
    - Provider metadata management
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProviderInfo] = {}

    def register(
        self,
        name: str,
        provider: LLMProvider,
        metadata: dict | None = None,
    ) -> None:
        """Register a new LLM provider.

        Args:
            name: Unique identifier for the provider.
            provider: LLMProvider instance.
            metadata: Optional metadata about the provider.

        Raises:
            ValueError: If provider with same name already exists.
        """
        if name in self._providers:
            raise ValueError(f"Provider '{name}' is already registered")

        self._providers[name] = ProviderInfo(
            name=name,
            provider=provider,
            metadata=metadata or {},
        )

    def unregister(self, name: str) -> None:
        """Unregister a provider.

        Args:
            name: Provider identifier.

        Raises:
            ModelNotFoundError: If provider doesn't exist.
        """
        if name not in self._providers:
            raise ModelNotFoundError(f"Provider '{name}' not found")
        del self._providers[name]

    def get_provider(self, name: str) -> LLMProvider:
        """Get a provider by name.

        Args:
            name: Provider identifier.

        Returns:
            The LLMProvider instance.

        Raises:
            ModelNotFoundError: If provider doesn't exist.
        """
        info = self._providers.get(name)
        if not info:
            raise ModelNotFoundError(f"Provider '{name}' not found")
        if not info.circuit_breaker.is_available():
            snapshot = info.circuit_breaker.snapshot()
            raise LLMServiceError(
                f"Provider '{name}' circuit is open",
                details={
                    "provider": name,
                    "circuit_state": snapshot.state,
                    "last_error": snapshot.last_error,
                },
            )
        return info.provider

    def get_provider_for_probe(self, name: str) -> LLMProvider:
        """Get a provider for health probes, bypassing circuit availability."""
        info = self._providers.get(name)
        if not info:
            raise ModelNotFoundError(f"Provider '{name}' not found")
        return info.provider

    def get_provider_info(self, name: str) -> ProviderInfo:
        """Get full provider info by name.

        Args:
            name: Provider identifier.

        Returns:
            ProviderInfo with provider and metadata.

        Raises:
            ModelNotFoundError: If provider doesn't exist.
        """
        info = self._providers.get(name)
        if not info:
            raise ModelNotFoundError(f"Provider '{name}' not found")
        return info

    def has_provider(self, name: str) -> bool:
        """Check if a provider is registered."""
        return name in self._providers

    def resolve_provider_name(self, name: str) -> str:
        """Return the provider name unchanged (v2: no pseudo-provider aliases)."""
        return name

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def list_providers_info(self) -> list[ProviderInfo]:
        """List all provider info objects."""
        return list(self._providers.values())

    async def aclose(self) -> None:
        """Close provider resources that expose an async close hook."""
        for info in list(self._providers.values()):
            close = getattr(info.provider, "aclose", None)
            if close is not None:
                await close()

    def get_healthy_providers(self) -> list[str]:
        """Get names of providers that passed last health check."""
        return [
            name for name, info in self._providers.items()
            if info.is_healthy and info.circuit_breaker.is_available()
        ]

    def is_provider_available(self, name: str) -> bool:
        """Return whether provider exists and its circuit allows routing."""
        info = self._providers.get(name)
        return bool(info and info.circuit_breaker.is_available())

    def record_success(self, name: str) -> None:
        """Record a successful provider request."""
        info = self._providers.get(name)
        if not info:
            return
        info.is_healthy = True
        info.circuit_breaker.record_success()

    def record_failure(self, name: str, error: str | None = None) -> None:
        """Record a failed provider request."""
        info = self._providers.get(name)
        if not info:
            return
        info.is_healthy = False
        info.circuit_breaker.record_failure(error)

    def reset_circuit(self, name: str) -> None:
        """Close a provider circuit after a manual or scheduled recovery probe."""
        info = self._providers.get(name)
        if not info:
            return
        info.circuit_breaker.close()
        info.is_healthy = True

    async def test_connection(self, name: str) -> HealthCheckResult:
        """Test connection to a specific provider.

        Performs a simple completion request to verify connectivity.

        Args:
            name: Provider identifier.

        Returns:
            HealthCheckResult with status and latency.
        """
        import time

        info = self._providers.get(name)
        if not info:
            return HealthCheckResult(
                provider_name=name,
                is_healthy=False,
                error=f"Provider '{name}' not found",
            )

        start_time = time.perf_counter()
        try:
            is_healthy = await info.provider.health_check()
            latency_ms = (time.perf_counter() - start_time) * 1000

            info.is_healthy = is_healthy
            info.last_health_check = time.time()
            if is_healthy:
                info.circuit_breaker.record_success()
            else:
                info.circuit_breaker.record_failure("Health check returned False")

            return HealthCheckResult(
                provider_name=name,
                is_healthy=is_healthy,
                latency_ms=latency_ms,
                error=None if is_healthy else "Health check returned False",
                status="operational" if is_healthy else "failed",
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            info.is_healthy = False
            info.last_health_check = time.time()
            info.circuit_breaker.record_failure(str(e))

            return HealthCheckResult(
                provider_name=name,
                is_healthy=False,
                latency_ms=latency_ms,
                error=str(e),
                status="failed",
            )

    async def test_all_connections(
        self,
        timeout: float = 30.0,
    ) -> list[HealthCheckResult]:
        """Test connections to all registered providers.

        Args:
            timeout: Maximum time to wait for all health checks.

        Returns:
            List of HealthCheckResult for each provider.
        """
        tasks = [
            self.test_connection(name)
            for name in self._providers
        ]

        if not tasks:
            return []

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )

            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    provider_name = list(self._providers.keys())[i]
                    processed_results.append(
                        HealthCheckResult(
                            provider_name=provider_name,
                            is_healthy=False,
                            error=str(result),
                        )
                    )
                else:
                    processed_results.append(result)

            return processed_results

        except asyncio.TimeoutError:
            return [
                HealthCheckResult(
                    provider_name=name,
                    is_healthy=False,
                    error="Health check timed out",
                )
                for name in self._providers
            ]

    def discover_providers(self) -> dict[str, dict]:
        """Discover and return information about all providers.

        Returns:
            Dictionary mapping provider names to their capabilities.
        """
        discovery = {}
        for name, info in self._providers.items():
            provider = info.provider
            discovery[name] = {
                "name": name,
                "provider_type": provider.name,
                "supports_streaming": provider.supports_streaming,
                "supports_tools": provider.supports_tools,
                "supports_embeddings": provider.supports_embeddings,
                "is_healthy": info.is_healthy,
                "circuit": info.circuit_breaker.snapshot().__dict__,
                "metadata": info.metadata,
            }
        return discovery

    def update_metadata(self, name: str, metadata: dict) -> None:
        """Update metadata for a provider.

        Args:
            name: Provider identifier.
            metadata: New metadata to merge.

        Raises:
            ModelNotFoundError: If provider doesn't exist.
        """
        info = self._providers.get(name)
        if not info:
            raise ModelNotFoundError(f"Provider '{name}' not found")
        info.metadata.update(metadata)

    def replace(self, name: str, provider: LLMProvider, metadata: dict | None = None) -> None:
        """Replace (or create) a provider entry, bypassing the duplicate check."""
        self._providers[name] = ProviderInfo(
            name=name,
            provider=provider,
            metadata=metadata or {},
        )

    def clear(self) -> None:
        """Unregister all providers."""
        self._providers.clear()


def create_default_registry() -> ProviderRegistry:
    """Create a registry from providers.yaml v2 plus optional env-only overrides."""
    import logging

    _log = logging.getLogger(__name__)
    registry = ProviderRegistry()

    try:
        from leagent.llm.provider_config import ProviderConfigService

        ProviderConfigService(registry=registry)
    except Exception:
        _log.debug("providers.yaml not available; registry may be empty")

    _register_env_overrides(registry, _log)
    return registry


def _register_env_overrides(
    registry: ProviderRegistry,
    _log: "logging.Logger",
) -> None:
    """Register optional env-only providers (vLLM, Ollama)."""
    from leagent.config.settings import get_settings
    from leagent.llm.providers.ollama import OllamaProvider
    from leagent.llm.providers.vllm import VLLMProvider

    settings = get_settings()

    if settings.llm.vllm_endpoint and not registry.has_provider("vllm"):
        vllm_model_label = settings.llm.vllm_model or "auto-detect"
        vllm_provider = VLLMProvider(
            api_key=settings.llm.vllm_api_key or "not-needed",
            base_url=settings.llm.vllm_endpoint.rstrip("/"),
            default_model=settings.llm.vllm_model,
            timeout=settings.llm.vllm_timeout,
            enable_auto_tool_choice=settings.llm.vllm_enable_auto_tool_choice,
        )
        _ep = settings.llm.vllm_endpoint
        _is_local = "localhost" in _ep or "127.0.0.1" in _ep or "host.docker.internal" in _ep
        registry.register(
            "vllm",
            vllm_provider,
            metadata={"type": "local" if _is_local else "remote", "vendor": "vllm", "model": vllm_model_label},
        )

    if settings.llm.ollama_endpoint and not registry.has_provider("ollama"):
        registry.register(
            "ollama",
            OllamaProvider(
                base_url=settings.llm.ollama_endpoint,
                default_model=settings.llm.ollama_model,
            ),
            metadata={"type": "local", "vendor": "ollama", "model": settings.llm.ollama_model},
        )
