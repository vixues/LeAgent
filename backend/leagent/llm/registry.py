"""Provider registry for LLM provider management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from leagent.exceptions.llm import LLMServiceError, ModelNotFoundError
from leagent.llm.circuit_breaker import CircuitBreaker

if TYPE_CHECKING:
    from leagent.llm.base import LLMProvider


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

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def list_providers_info(self) -> list[ProviderInfo]:
        """List all provider info objects."""
        return list(self._providers.values())

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


def _endpoint_hostname_is_deepseek(base_url: str) -> bool:
    """True when *base_url* points at DeepSeek's API (OpenAI-compatible)."""
    from urllib.parse import urlparse

    h = (urlparse(base_url or "").hostname or "").lower()
    return "deepseek" in h


def _endpoint_hostname_is_dashscope(base_url: str) -> bool:
    """True when *base_url* points at DashScope's API (OpenAI-compatible)."""
    from urllib.parse import urlparse

    h = (urlparse(base_url or "").hostname or "").lower()
    return "dashscope" in h or "maas.aliyuncs.com" in h


def create_default_registry() -> ProviderRegistry:
    """Create a registry with default providers from settings.

    This is a factory function that reads from application settings
    and configures the appropriate providers.
    """
    from leagent.config.settings import get_settings
    from leagent.llm.providers.anthropic import AnthropicProvider
    from leagent.llm.providers.dashscope import DashScopeProvider
    from leagent.llm.providers.deepseek import DeepSeekProvider
    from leagent.llm.providers.ollama import OllamaProvider
    from leagent.llm.providers.openai import OpenAIProvider

    settings = get_settings()
    registry = ProviderRegistry()

    # Register tiered providers for local/on-prem endpoints.
    # These typically point to vLLM or compatible local gateways in production.
    _tier_key = (
        settings.llm.tier1_api_key
        or settings.llm.openai_api_key
        or settings.llm.dashscope_api_key
        or settings.llm.deepseek_api_key
    )

    if settings.llm.tier1_endpoint:
        if _endpoint_hostname_is_deepseek(settings.llm.tier1_endpoint):
            registry.register(
                "tier1",
                DeepSeekProvider(
                    api_key=_tier_key or "not-needed",
                    base_url=settings.llm.tier1_endpoint.rstrip("/"),
                    default_model=settings.llm.tier1_model,
                    timeout=settings.llm.tier1_timeout,
                ),
                metadata={
                    "tier": "tier1",
                    "model": settings.llm.tier1_model,
                    "description": "Primary reasoning model (DeepSeek)",
                },
            )
        elif _endpoint_hostname_is_dashscope(settings.llm.tier1_endpoint):
            registry.register(
                "tier1",
                DashScopeProvider(
                    api_key=_tier_key or "not-needed",
                    base_url=settings.llm.tier1_endpoint.rstrip("/"),
                    default_model=settings.llm.tier1_model,
                    timeout=settings.llm.tier1_timeout,
                ),
                metadata={
                    "tier": "tier1",
                    "model": settings.llm.tier1_model,
                    "description": "Primary reasoning model (DashScope)",
                },
            )
        else:
            registry.register(
                "tier1",
                OpenAIProvider(
                    api_key=_tier_key or "not-needed",
                    base_url=settings.llm.tier1_endpoint,
                    default_model=settings.llm.tier1_model,
                    timeout=settings.llm.tier1_timeout,
                ),
                metadata={
                    "tier": "tier1",
                    "model": settings.llm.tier1_model,
                    "description": "Primary reasoning model",
                },
            )

    # Register provider for tier2
    _tier2_key = (
        settings.llm.tier2_api_key
        or settings.llm.openai_api_key
        or settings.llm.dashscope_api_key
        or settings.llm.deepseek_api_key
    )

    if settings.llm.tier2_endpoint:
        if _endpoint_hostname_is_deepseek(settings.llm.tier2_endpoint):
            registry.register(
                "tier2",
                DeepSeekProvider(
                    api_key=_tier2_key or "not-needed",
                    base_url=settings.llm.tier2_endpoint.rstrip("/"),
                    default_model=settings.llm.tier2_model,
                    timeout=settings.llm.tier2_timeout,
                ),
                metadata={
                    "tier": "tier2",
                    "model": settings.llm.tier2_model,
                    "description": "Fast model for simple tasks (DeepSeek)",
                },
            )
        elif _endpoint_hostname_is_dashscope(settings.llm.tier2_endpoint):
            registry.register(
                "tier2",
                DashScopeProvider(
                    api_key=_tier2_key or "not-needed",
                    base_url=settings.llm.tier2_endpoint.rstrip("/"),
                    default_model=settings.llm.tier2_model,
                    timeout=settings.llm.tier2_timeout,
                ),
                metadata={
                    "tier": "tier2",
                    "model": settings.llm.tier2_model,
                    "description": "Fast model for simple tasks (DashScope)",
                },
            )
        else:
            registry.register(
                "tier2",
                OpenAIProvider(
                    api_key=_tier2_key or "not-needed",
                    base_url=settings.llm.tier2_endpoint,
                    default_model=settings.llm.tier2_model,
                    timeout=settings.llm.tier2_timeout,
                ),
                metadata={
                    "tier": "tier2",
                    "model": settings.llm.tier2_model,
                    "description": "Fast model for simple tasks",
                },
            )

    # Register embedding provider (typically local embedding service)
    if settings.llm.embedding_endpoint:
        registry.register(
            "embedding",
            OpenAIProvider(
                api_key=settings.llm.openai_api_key or "not-needed",
                base_url=settings.llm.embedding_endpoint,
                default_model=settings.llm.embedding_model,
            ),
            metadata={
                "type": "embedding",
                "model": settings.llm.embedding_model,
                "dimension": settings.llm.embedding_dim,
            },
        )

    # Optionally register cloud providers when not in local-only mode.
    if not settings.llm.local_only:
        if settings.llm.openai_api_key:
            registry.register(
                "openai",
                OpenAIProvider(
                    api_key=settings.llm.openai_api_key,
                    default_model="gpt-4o",
                ),
                metadata={
                    "type": "cloud",
                    "vendor": "openai",
                },
            )

        if settings.llm.anthropic_api_key:
            registry.register(
                "anthropic",
                AnthropicProvider(
                    api_key=settings.llm.anthropic_api_key,
                    default_model=settings.llm.anthropic_model,
                ),
                metadata={
                    "type": "cloud",
                    "vendor": "anthropic",
                    "model": settings.llm.anthropic_model,
                },
            )

        if settings.llm.dashscope_api_key:
            registry.register(
                "dashscope",
                DashScopeProvider(
                    api_key=settings.llm.dashscope_api_key,
                    base_url=settings.llm.dashscope_base_url,
                    default_model=settings.llm.dashscope_model,
                ),
                metadata={
                    "type": "cloud",
                    "vendor": "dashscope",
                    "model": settings.llm.dashscope_model,
                },
            )
            # Auto-alias DashScope as tier1/tier2 when no explicit tiers
            # are configured — same pattern as DeepSeek below.
            # tier1 → qwen3-max (reasoning), tier2 → configured model.
            if not registry.has_provider("tier1"):
                tier1_model = settings.llm.dashscope_model
                if tier1_model == DashScopeProvider.DEFAULT_MODEL:
                    tier1_model = "qwen3-max"
                registry.register(
                    "tier1",
                    DashScopeProvider(
                        api_key=settings.llm.dashscope_api_key,
                        base_url=settings.llm.dashscope_base_url,
                        default_model=tier1_model,
                    ),
                    metadata={
                        "tier": "tier1",
                        "vendor": "dashscope",
                        "model": tier1_model,
                        "description": "DashScope (auto-aliased as tier1)",
                    },
                )
            if not registry.has_provider("tier2"):
                registry.register(
                    "tier2",
                    DashScopeProvider(
                        api_key=settings.llm.dashscope_api_key,
                        base_url=settings.llm.dashscope_base_url,
                        default_model=settings.llm.dashscope_model,
                    ),
                    metadata={
                        "tier": "tier2",
                        "vendor": "dashscope",
                        "model": settings.llm.dashscope_model,
                        "description": "DashScope (auto-aliased as tier2)",
                    },
                )

        if settings.llm.deepseek_api_key:
            registry.register(
                "deepseek",
                DeepSeekProvider(
                    api_key=settings.llm.deepseek_api_key,
                    base_url=settings.llm.deepseek_base_url,
                    default_model=settings.llm.deepseek_model,
                ),
                metadata={
                    "type": "cloud",
                    "vendor": "deepseek",
                    "model": settings.llm.deepseek_model,
                },
            )
            # When no tier1/tier2 endpoint is configured but DeepSeek is
            # available, auto-alias it so ``chat_stream`` / QueryEngine
            # find a provider on both tiers.
            # tier1 uses deepseek-v4-pro (reasoning-heavy) unless the
            # user explicitly configured a different model.
            if not registry.has_provider("tier1"):
                tier1_model = settings.llm.deepseek_model
                if tier1_model == DeepSeekProvider.DEFAULT_MODEL:
                    tier1_model = "deepseek-v4-pro"
                registry.register(
                    "tier1",
                    DeepSeekProvider(
                        api_key=settings.llm.deepseek_api_key,
                        base_url=settings.llm.deepseek_base_url,
                        default_model=tier1_model,
                    ),
                    metadata={
                        "tier": "tier1",
                        "vendor": "deepseek",
                        "model": tier1_model,
                        "description": "DeepSeek (auto-aliased as tier1)",
                    },
                )
            # tier2 keeps the default flash model (fast/cheap).
            if not registry.has_provider("tier2"):
                registry.register(
                    "tier2",
                    DeepSeekProvider(
                        api_key=settings.llm.deepseek_api_key,
                        base_url=settings.llm.deepseek_base_url,
                        default_model=settings.llm.deepseek_model,
                    ),
                    metadata={
                        "tier": "tier2",
                        "vendor": "deepseek",
                        "model": settings.llm.deepseek_model,
                        "description": "DeepSeek (auto-aliased as tier2)",
                    },
                )

    # Ollama runs locally; register when an endpoint is configured regardless of local_only.
    if settings.llm.ollama_endpoint:
        registry.register(
            "ollama",
            OllamaProvider(
                base_url=settings.llm.ollama_endpoint,
                default_model=settings.llm.ollama_model,
            ),
            metadata={
                "type": "local",
                "vendor": "ollama",
                "model": settings.llm.ollama_model,
            },
        )

    # ---- Merge providers.yaml into the registry ----
    # The ProviderConfigService manages a separate providers.yaml file where
    # the Admin UI persists provider configs and the default_provider setting.
    # We merge those providers in and, critically, let the YAML
    # default_provider override the env-configured tier1/tier2.
    _merge_yaml_providers(registry)

    return registry


def _merge_yaml_providers(registry: ProviderRegistry) -> None:
    """Load providers.yaml and merge into *registry*.

    YAML providers whose name isn't already registered are added.
    If ``default_provider`` / ``default_model`` are set in the YAML, the
    corresponding provider is promoted to ``tier1`` (and ``tier2`` if
    tier2 isn't already set), **replacing** any env-sourced tier.
    """
    import logging

    _log = logging.getLogger(__name__)

    try:
        from leagent.llm.provider_config import ProviderConfigService
        svc = ProviderConfigService()
    except Exception:
        _log.debug("providers.yaml not available; skipping YAML merge")
        return

    for pc in svc.list_providers():
        if not pc.enabled:
            continue
        if registry.has_provider(pc.name):
            continue
        try:
            provider = svc._create_llm_provider(pc)
            registry.register(
                pc.name,
                provider,
                metadata={
                    "type": pc.type,
                    "models": [m.get("name", "") for m in pc.models],
                    "source": "providers.yaml",
                },
            )
        except Exception:
            _log.warning("YAML provider %s failed to register", pc.name, exc_info=True)

    default_cfg = svc.get_default()
    if not default_cfg.provider:
        return

    if not registry.has_provider(default_cfg.provider):
        _log.warning(
            "YAML default_provider '%s' is not registered; cannot promote to tier1",
            default_cfg.provider,
        )
        return

    default_provider_instance = registry.get_provider(default_cfg.provider)
    default_model = default_cfg.model or default_provider_instance._get_default_model()

    _log.info(
        "YAML default_provider=%s model=%s overriding tier1/tier2",
        default_cfg.provider,
        default_model,
    )

    registry.replace(
        "tier1",
        default_provider_instance,
        metadata={
            "tier": "tier1",
            "vendor": default_cfg.provider,
            "model": default_model,
            "description": f"{default_cfg.provider} (promoted from providers.yaml)",
        },
    )
    if not registry.has_provider("tier2") or True:
        registry.replace(
            "tier2",
            default_provider_instance,
            metadata={
                "tier": "tier2",
                "vendor": default_cfg.provider,
                "model": default_model,
                "description": f"{default_cfg.provider} (promoted from providers.yaml)",
            },
        )
