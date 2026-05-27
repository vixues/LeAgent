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

    def resolve_provider_name(self, name: str) -> str:
        """Map tier routing aliases (``tier1``/``tier2``) to the YAML provider name."""
        if name not in self._providers:
            return name
        meta = self._providers[name].metadata
        if not isinstance(meta, dict):
            return name
        vendor = meta.get("vendor")
        if isinstance(vendor, str) and vendor.strip() and vendor.strip() in self._providers:
            return vendor.strip()
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


def _first_yaml_enabled_model(models: list[dict]) -> str:
    """Return the first enabled non-empty model name from a YAML model list."""
    for model in models:
        if model.get("enabled", True) is False:
            continue
        name = str(model.get("name") or "").strip()
        if name:
            return name
    return ""


def create_default_registry() -> ProviderRegistry:
    """Create a registry with providers from YAML (primary) and env vars (fallback).

    Resolution order:
    1. Load providers from ``providers.yaml`` via :class:`ProviderConfigService`.
    2. If no YAML providers exist, register providers from env vars (backward compat).
    3. Register special env-only providers (vLLM override, embedding, Ollama).
    4. Promote the default provider to tier1/tier2 for routing.
    """
    import logging

    _log = logging.getLogger(__name__)
    registry = ProviderRegistry()

    # --- Step 1: YAML providers (primary authority) ---
    yaml_svc = _load_yaml_providers(registry, _log)

    # --- Step 2: Env-var fallback when YAML has no providers ---
    yaml_provider_names = {p for p in registry.list_providers()}
    if not yaml_provider_names:
        _register_from_env(registry, _log)

    # --- Step 3: Special env-only providers (always checked) ---
    _register_env_overrides(registry, _log)

    # --- Step 4: Assign tier1/tier2 from default provider ---
    _assign_tiers(registry, yaml_svc, _log)

    return registry


def _load_yaml_providers(
    registry: ProviderRegistry,
    _log: "logging.Logger",
) -> "ProviderConfigService | None":
    """Load all enabled providers from ``providers.yaml`` into the registry."""
    try:
        from leagent.llm.provider_config import ProviderConfigService

        svc = ProviderConfigService()
    except Exception:
        _log.debug("providers.yaml not available; skipping YAML load")
        return None

    for pc in svc.list_providers():
        if not pc.enabled:
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

    return svc


def _register_from_env(
    registry: ProviderRegistry,
    _log: "logging.Logger",
) -> None:
    """Register providers from env vars when providers.yaml is empty."""
    from leagent.config.settings import get_settings
    from leagent.llm.providers.anthropic import AnthropicProvider
    from leagent.llm.providers.openai import OpenAIProvider
    from leagent.llm.providers.dashscope import DashScopeProvider
    from leagent.llm.providers.deepseek import DeepSeekProvider

    settings = get_settings()

    # Legacy explicit tier endpoints
    _tier_key = (
        settings.llm.tier1_api_key
        or settings.llm.openai_api_key
        or settings.llm.dashscope_api_key
        or settings.llm.deepseek_api_key
    )

    if settings.llm.tier1_endpoint and settings.llm.tier1_model:
        _register_tier_from_env(
            registry, "tier1",
            settings.llm.tier1_endpoint,
            settings.llm.tier1_model,
            _tier_key or "not-needed",
            settings.llm.tier1_timeout,
        )

    _tier2_key = (
        settings.llm.tier2_api_key
        or settings.llm.openai_api_key
        or settings.llm.dashscope_api_key
        or settings.llm.deepseek_api_key
    )

    if settings.llm.tier2_endpoint and settings.llm.tier2_model:
        _register_tier_from_env(
            registry, "tier2",
            settings.llm.tier2_endpoint,
            settings.llm.tier2_model,
            _tier2_key or "not-needed",
            settings.llm.tier2_timeout,
        )

    # Cloud providers when not local-only
    if not settings.llm.local_only:
        if settings.llm.openai_api_key:
            registry.register(
                "openai",
                OpenAIProvider(
                    api_key=settings.llm.openai_api_key,
                    default_model="gpt-4o",
                ),
                metadata={"type": "cloud", "vendor": "openai"},
            )

        if settings.llm.anthropic_api_key:
            registry.register(
                "anthropic",
                AnthropicProvider(
                    api_key=settings.llm.anthropic_api_key,
                    default_model=settings.llm.anthropic_model,
                ),
                metadata={"type": "cloud", "vendor": "anthropic", "model": settings.llm.anthropic_model},
            )

        if settings.llm.dashscope_api_key:
            registry.register(
                "dashscope",
                DashScopeProvider(
                    api_key=settings.llm.dashscope_api_key,
                    base_url=settings.llm.dashscope_base_url,
                    default_model=settings.llm.dashscope_model,
                ),
                metadata={"type": "cloud", "vendor": "dashscope", "model": settings.llm.dashscope_model},
            )
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
                    metadata={"tier": "tier1", "vendor": "dashscope", "model": tier1_model},
                )
            if not registry.has_provider("tier2"):
                registry.register(
                    "tier2",
                    DashScopeProvider(
                        api_key=settings.llm.dashscope_api_key,
                        base_url=settings.llm.dashscope_base_url,
                        default_model=settings.llm.dashscope_model,
                    ),
                    metadata={"tier": "tier2", "vendor": "dashscope", "model": settings.llm.dashscope_model},
                )

        if settings.llm.deepseek_api_key:
            registry.register(
                "deepseek",
                DeepSeekProvider(
                    api_key=settings.llm.deepseek_api_key,
                    base_url=settings.llm.deepseek_base_url,
                    default_model=settings.llm.deepseek_model,
                ),
                metadata={"type": "cloud", "vendor": "deepseek", "model": settings.llm.deepseek_model},
            )
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
                    metadata={"tier": "tier1", "vendor": "deepseek", "model": tier1_model},
                )
            if not registry.has_provider("tier2"):
                registry.register(
                    "tier2",
                    DeepSeekProvider(
                        api_key=settings.llm.deepseek_api_key,
                        base_url=settings.llm.deepseek_base_url,
                        default_model=settings.llm.deepseek_model,
                    ),
                    metadata={"tier": "tier2", "vendor": "deepseek", "model": settings.llm.deepseek_model},
                )


def _register_tier_from_env(
    registry: ProviderRegistry,
    tier_name: str,
    endpoint: str,
    model: str,
    api_key: str,
    timeout: int,
) -> None:
    """Register a tier provider from env vars, detecting the correct provider class."""
    from leagent.llm.providers.dashscope import DashScopeProvider
    from leagent.llm.providers.deepseek import DeepSeekProvider
    from leagent.llm.providers.custom import CustomOpenAIProvider

    if _endpoint_hostname_is_deepseek(endpoint):
        provider = DeepSeekProvider(
            api_key=api_key, base_url=endpoint.rstrip("/"),
            default_model=model, timeout=timeout,
        )
    elif _endpoint_hostname_is_dashscope(endpoint):
        provider = DashScopeProvider(
            api_key=api_key, base_url=endpoint.rstrip("/"),
            default_model=model, timeout=timeout,
        )
    else:
        provider = CustomOpenAIProvider(
            api_key=api_key, base_url=endpoint,
            default_model=model, timeout=timeout,
        )
    registry.register(
        tier_name, provider,
        metadata={"tier": tier_name, "model": model, "source": "env"},
    )


def _register_env_overrides(
    registry: ProviderRegistry,
    _log: "logging.Logger",
) -> None:
    """Register special providers that are always driven by env vars."""
    from leagent.config.settings import get_settings
    from leagent.llm.providers.ollama import OllamaProvider
    from leagent.llm.providers.openai import OpenAIProvider
    from leagent.llm.providers.vllm import VLLMProvider

    settings = get_settings()

    # vLLM override: when configured, takes over tier1/tier2
    if settings.llm.vllm_endpoint:
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
        registry.replace("vllm", vllm_provider, metadata={"type": "local" if _is_local else "remote", "vendor": "vllm", "model": vllm_model_label})
        registry.replace("tier1", vllm_provider, metadata={"tier": "tier1", "vendor": "vllm", "model": vllm_model_label, "description": "vLLM (configured via LLM_VLLM_ENDPOINT)"})
        registry.replace("tier2", vllm_provider, metadata={"tier": "tier2", "vendor": "vllm", "model": vllm_model_label, "description": "vLLM (configured via LLM_VLLM_ENDPOINT)"})

    # Embedding provider
    if settings.llm.embedding_endpoint:
        if not registry.has_provider("embedding"):
            registry.register(
                "embedding",
                OpenAIProvider(
                    api_key=settings.llm.openai_api_key or "not-needed",
                    base_url=settings.llm.embedding_endpoint,
                    default_model=settings.llm.embedding_model,
                ),
                metadata={"type": "embedding", "model": settings.llm.embedding_model, "dimension": settings.llm.embedding_dim},
            )

    # Ollama (local, always registered when endpoint is set)
    if settings.llm.ollama_endpoint and not registry.has_provider("ollama"):
        registry.register(
            "ollama",
            OllamaProvider(
                base_url=settings.llm.ollama_endpoint,
                default_model=settings.llm.ollama_model,
            ),
            metadata={"type": "local", "vendor": "ollama", "model": settings.llm.ollama_model},
        )


def _assign_tiers(
    registry: ProviderRegistry,
    yaml_svc: "ProviderConfigService | None",
    _log: "logging.Logger",
) -> None:
    """Promote the default provider to tier1/tier2 using model tier annotations."""
    if registry.has_provider("tier1") and registry.has_provider("tier2"):
        # vLLM override or env tiers already assigned — nothing to do
        tier1_meta = registry.get_provider_info("tier1").metadata
        if tier1_meta.get("vendor") == "vllm":
            return

    if yaml_svc is None:
        return

    from leagent.llm.provider_config import _model_entry_enabled, enabled_model_names

    default_cfg = yaml_svc.get_default()
    default_pc = yaml_svc.get_provider(default_cfg.provider) if default_cfg.provider else None
    allowed = enabled_model_names(default_pc.models) if default_pc else []

    default_is_valid = bool(
        default_pc and default_pc.enabled and allowed
        and (not default_cfg.model or default_cfg.model in allowed)
    )

    if not default_is_valid:
        fallback_pc = next(
            (pc for pc in yaml_svc.list_providers() if pc.enabled and enabled_model_names(pc.models)),
            None,
        )
        if fallback_pc is None:
            if default_cfg.provider:
                _log.warning("default_provider '%s' is invalid and no enabled provider available", default_cfg.provider)
            return
        fallback_model = _first_yaml_enabled_model(fallback_pc.models)
        _log.warning(
            "default_provider '%s' model '%s' invalid; using '%s' model '%s'",
            default_cfg.provider, default_cfg.model, fallback_pc.name, fallback_model,
        )
        default_cfg.provider = fallback_pc.name
        default_cfg.model = fallback_model
        default_pc = fallback_pc

    if not registry.has_provider(default_cfg.provider):
        _log.warning("default_provider '%s' not registered; cannot assign tiers", default_cfg.provider)
        return

    default_provider_instance = registry.get_provider(default_cfg.provider)
    default_model = default_cfg.model or default_provider_instance._get_default_model()

    tier1_model = ""
    tier2_model = ""
    if default_pc:
        for m in default_pc.models:
            if not _model_entry_enabled(m):
                continue
            mt = (m.get("tier") or "").strip().lower()
            mn = (m.get("name") or "").strip()
            if not mn:
                continue
            if mt == "tier1" and not tier1_model:
                tier1_model = mn
            elif mt == "tier2" and not tier2_model:
                tier2_model = mn

    if not tier1_model:
        tier1_model = default_model
    if not tier2_model:
        tier2_model = tier1_model

    _log.info("default_provider=%s tier1_model=%s tier2_model=%s", default_cfg.provider, tier1_model, tier2_model)

    registry.replace(
        "tier1", default_provider_instance,
        metadata={"tier": "tier1", "vendor": default_cfg.provider, "model": tier1_model, "description": f"{default_cfg.provider} (from providers.yaml)"},
    )
    registry.replace(
        "tier2", default_provider_instance,
        metadata={"tier": "tier2", "vendor": default_cfg.provider, "model": tier2_model, "description": f"{default_cfg.provider} (from providers.yaml)"},
    )
