"""Persistent provider configuration service.

Manages LLM provider configs in ``~/.leagent/providers.yaml`` and keeps the
in-memory :class:`ProviderRegistry` in sync.  Both the HTTP API and the CLI
share this module so that changes made in one surface are immediately visible
in the other.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from leagent.config.constants import PROVIDERS_PATH
from leagent.llm.registry import HealthCheckResult, ProviderRegistry

logger = logging.getLogger(__name__)


class ProviderConfigValidationError(ValueError):
    """Invalid provider configuration (models list, default model, etc.)."""


def _model_entry_enabled(entry: dict[str, Any]) -> bool:
    return entry.get("enabled", True) is not False


def enabled_model_names(models: list[dict[str, Any]]) -> list[str]:
    """Return non-empty model names that are enabled for routing and defaults."""
    out: list[str] = []
    for m in models:
        raw_name = m.get("name")
        name = (raw_name if isinstance(raw_name, str) else str(raw_name or "")).strip()
        if not name or not _model_entry_enabled(m):
            continue
        out.append(name)
    return out


def _first_enabled_model(models: list[dict[str, Any]]) -> str:
    for m in models:
        if not _model_entry_enabled(m):
            continue
        raw_name = m.get("name")
        name = (raw_name if isinstance(raw_name, str) else str(raw_name or "")).strip()
        if name:
            return name
    return ""


def validate_models_list(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Require at least one model, non-empty names, no duplicates."""
    if not models:
        raise ProviderConfigValidationError("At least one model is required")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for raw in models:
        if not isinstance(raw, dict):
            raise ProviderConfigValidationError("Each model must be an object with a 'name' field")
        raw_name = raw.get("name")
        name = (raw_name if isinstance(raw_name, str) else str(raw_name or "")).strip()
        if not name:
            raise ProviderConfigValidationError("Model name cannot be empty")
        if name in seen:
            raise ProviderConfigValidationError(f"Duplicate model name: {name}")
        seen.add(name)
        out.append({**raw, "name": name})
    return out


# ---------------------------------------------------------------------------
# Provider type presets
# ---------------------------------------------------------------------------

PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "default_base_url": "https://api.openai.com/v1",
        "requires_api_key": True,
        "models": [
            {
                "name": "gpt-4o", "tier": "tier1", "context_window": 128_000,
                "price_input_per_1m": 2.50, "price_output_per_1m": 10.00,
                "supports_tools": True, "supports_vision": True,
                "description": "Flagship multimodal model — strong reasoning, vision, and tool use.",
            },
            {
                "name": "gpt-4o-mini", "tier": "tier2", "context_window": 128_000,
                "price_input_per_1m": 0.15, "price_output_per_1m": 0.60,
                "supports_tools": True, "supports_vision": True,
                "description": "Affordable, intelligent small model for fast, lightweight tasks.",
            },
            {
                "name": "o3-mini", "tier": "tier1", "context_window": 200_000,
                "price_input_per_1m": 1.10, "price_output_per_1m": 4.40,
                "supports_tools": True,
                "description": "Reasoning model — thinks step-by-step. Use reasoning_effort to control depth.",
            },
        ],
    },
    "anthropic": {
        "label": "Anthropic",
        "default_base_url": "https://api.anthropic.com",
        "requires_api_key": True,
        "models": [
            {
                "name": "claude-sonnet-4-20250514", "tier": "tier1", "context_window": 200_000,
                "price_input_per_1m": 3.00, "price_output_per_1m": 15.00,
                "supports_tools": True, "supports_vision": True,
                "description": "High-performance Claude model with extended thinking.",
            },
            {
                "name": "claude-opus-4-7", "tier": "tier1", "context_window": 200_000,
                "price_input_per_1m": 15.00, "price_output_per_1m": 75.00,
                "supports_tools": True, "supports_vision": True,
                "description": "Most capable Claude model — adaptive thinking, task budgets.",
            },
            {
                "name": "claude-3-5-haiku-20241022", "tier": "tier2", "context_window": 200_000,
                "price_input_per_1m": 0.80, "price_output_per_1m": 4.00,
                "supports_tools": True, "supports_vision": True,
                "description": "Fast, affordable Claude model for lightweight tasks.",
            },
        ],
    },
    "qwen": {
        "label": "Qwen (通义千问)",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "requires_api_key": True,
        "models": [
            {
                "name": "qwen3-max", "tier": "tier1", "context_window": 128_000,
                "price_input_per_1m": 10.00, "price_output_per_1m": 30.00,
                "supports_tools": True, "supports_thinking": True,
                "description": "Qwen3-Max — strongest reasoning with thinking mode.",
            },
            {
                "name": "qwen3.5-plus", "tier": "tier1", "context_window": 128_000,
                "price_input_per_1m": 2.00, "price_output_per_1m": 8.00,
                "supports_tools": True, "supports_thinking": True,
                "description": "Qwen3.5-Plus — balanced performance and cost.",
            },
            {
                "name": "qwen-plus", "tier": "tier2", "context_window": 128_000,
                "price_input_per_1m": 0.80, "price_output_per_1m": 2.00,
                "supports_tools": True,
                "description": "Qwen-Plus — cost-effective general-purpose model.",
            },
            {
                "name": "qwen3.5-flash", "tier": "tier2", "context_window": 128_000,
                "price_input_per_1m": 0.30, "price_output_per_1m": 0.60,
                "supports_tools": True, "supports_thinking": True,
                "description": "Qwen3.5-Flash — fast and cost-effective.",
            },
            {
                "name": "qwq-plus", "tier": "tier1", "context_window": 128_000,
                "price_input_per_1m": 3.00, "price_output_per_1m": 12.00,
                "supports_tools": True, "supports_thinking": True,
                "description": "QwQ-Plus — specialized reasoning model.",
            },
            {
                "name": "qwen-long", "tier": "tier1", "context_window": 1_000_000,
                "price_input_per_1m": 0.50, "price_output_per_1m": 2.00,
                "supports_tools": True,
                "description": "Long-context Qwen — up to 1M tokens via file API.",
            },
            {
                "name": "qwen-vl-max", "tier": "tier1", "context_window": 128_000,
                "price_input_per_1m": 10.00, "price_output_per_1m": 30.00,
                "supports_tools": True,
                "description": "Qwen-VL-Max — multimodal vision-language model.",
            },
        ],
    },
    "deepseek": {
        "label": "DeepSeek",
        "default_base_url": "https://api.deepseek.com",
        "requires_api_key": True,
        "models": [
            {
                "name": "deepseek-v4-flash", "tier": "tier2", "context_window": 1_000_000,
                "price_input_per_1m": 0.14, "price_output_per_1m": 0.28,
                "supports_tools": True,
                "description": "DeepSeek-V4 Flash — fast default. V4 preview: https://api-docs.deepseek.com/news/news260424",
            },
            {
                "name": "deepseek-v4-pro", "tier": "tier1", "context_window": 1_000_000,
                "price_input_per_1m": 1.74, "price_output_per_1m": 3.48,
                "supports_tools": True,
                "description": "DeepSeek-V4 Pro (current API). See https://api-docs.deepseek.com/quick_start/pricing",
            },
        ],
    },
    "ollama": {
        "label": "Ollama (本地模型)",
        "default_base_url": "http://localhost:11434",
        "requires_api_key": False,
        "models": [],
    },
    "vllm": {
        "label": "vLLM (自托管模型)",
        "default_base_url": "http://localhost:8000/v1",
        "requires_api_key": False,
        "models": [],
    },
    "custom": {
        "label": "自定义 API (OpenAI 兼容)",
        "default_base_url": "",
        "requires_api_key": False,
        "models": [],
    },
}


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------

@dataclass
class ProviderConfig:
    """Represents a single provider entry in providers.yaml."""

    name: str
    type: str
    enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    models: list[dict[str, Any]] = field(default_factory=list)
    timeout: int = 120
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "enabled": self.enabled,
            "models": self.models,
        }
        if self.api_key:
            d["api_key"] = self.api_key
        if self.base_url:
            d["base_url"] = self.base_url
        if self.timeout != 120:
            d["timeout"] = self.timeout
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProviderConfig:
        ptype = data.get("type", "custom")
        base_url = data.get("base_url", "")
        if ptype == "deepseek" and base_url:
            from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

            base_url = normalize_deepseek_base_url(base_url)
        return cls(
            name=data.get("name", ""),
            type=ptype,
            enabled=data.get("enabled", True),
            api_key=data.get("api_key", ""),
            base_url=base_url,
            models=data.get("models", []),
            timeout=data.get("timeout", 120),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DefaultModelConfig:
    provider: str = ""
    model: str = ""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ProviderConfigService:
    """Central service for provider configuration management.

    Reads/writes ``providers.yaml`` and keeps a :class:`ProviderRegistry`
    populated with the corresponding live provider instances.
    """

    def __init__(
        self,
        providers_path: Path | None = None,
        registry: ProviderRegistry | None = None,
    ) -> None:
        self._path = providers_path or PROVIDERS_PATH
        self._registry = registry or ProviderRegistry()
        self._load_and_sync()

    # -- public properties ---------------------------------------------------

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    # -- YAML I/O ------------------------------------------------------------

    def _load_yaml(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"default_provider": "", "default_model": "", "providers": []}
        with open(self._path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return {"providers": []}
        if self._migrate_legacy_deepseek_config(data):
            self._save_yaml(data)
        return data

    _DEEPSEEK_MODEL_RENAMES: dict[str, str] = {
        "deepseek-chat": "deepseek-v4-flash",
        "deepseek-reasoner": "deepseek-v4-pro",
    }

    @staticmethod
    def _migrate_legacy_deepseek_config(config: dict[str, Any]) -> bool:
        """Migrate legacy DeepSeek base URLs and model names.

        - Strips ``/v1`` suffix from base URLs.
        - Renames ``deepseek-chat`` -> ``deepseek-v4-flash`` and
          ``deepseek-reasoner`` -> ``deepseek-v4-pro``.
        - Deduplicates model entries that collide after renaming.
        """
        from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

        changed = False
        renames = ProviderConfigService._DEEPSEEK_MODEL_RENAMES

        for entry in config.get("providers", []):
            if not isinstance(entry, dict) or entry.get("type") != "deepseek":
                continue

            raw = str(entry.get("base_url") or "")
            if raw:
                normalized = normalize_deepseek_base_url(raw)
                if normalized != raw.rstrip("/"):
                    entry["base_url"] = normalized
                    changed = True

            models = entry.get("models")
            if not isinstance(models, list):
                continue

            seen: set[str] = set()
            deduped: list[dict[str, Any]] = []
            for m in models:
                name = (m.get("name") or "")
                new_name = renames.get(name)
                if new_name:
                    m["name"] = new_name
                    name = new_name
                    changed = True
                if name not in seen:
                    seen.add(name)
                    deduped.append(m)
                else:
                    changed = True

            if len(deduped) != len(models):
                entry["models"] = deduped

        if config.get("default_model") in renames:
            config["default_model"] = renames[config["default_model"]]
            changed = True

        return changed

    def _save_yaml(self, config: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            yaml.dump(config, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # -- registry sync -------------------------------------------------------

    def _load_and_sync(self) -> None:
        """Load YAML and register all enabled providers in the registry."""
        config = self._load_yaml()
        for entry in config.get("providers", []):
            pc = ProviderConfig.from_dict(entry)
            if pc.enabled and not self._registry.has_provider(pc.name):
                try:
                    provider = self._create_llm_provider(pc)
                    self._registry.register(
                        pc.name,
                        provider,
                        metadata={
                            "type": pc.type,
                            "models": [m.get("name", "") for m in pc.models],
                        },
                    )
                except Exception:
                    logger.warning("Failed to register provider %s from YAML", pc.name, exc_info=True)

    def _create_llm_provider(self, pc: ProviderConfig):
        """Instantiate the correct LLMProvider subclass for a config."""
        from leagent.llm.providers.anthropic import AnthropicProvider
        from leagent.llm.providers.dashscope import DashScopeProvider
        from leagent.llm.providers.ollama import OllamaProvider
        from leagent.llm.providers.openai import OpenAIProvider
        from leagent.llm.providers.vllm import VLLMProvider

        api_key = self._resolve_api_key(pc.api_key)
        default_model = pc.models[0]["name"] if pc.models else ""

        if pc.type in ("openai", "azure", "custom"):
            return OpenAIProvider(
                api_key=api_key or "not-needed",
                base_url=pc.base_url or "https://api.openai.com/v1",
                default_model=default_model or "gpt-4o",
                timeout=pc.timeout,
            )
        if pc.type == "anthropic":
            return AnthropicProvider(
                api_key=api_key,
                default_model=default_model or "claude-sonnet-4-20250514",
                timeout=pc.timeout,
                base_url=pc.base_url or None,
            )
        if pc.type in ("qwen", "dashscope"):
            return DashScopeProvider(
                api_key=api_key,
                base_url=pc.base_url or DashScopeProvider.DEFAULT_BASE_URL,
                default_model=default_model or "qwen-plus",
                timeout=pc.timeout,
            )
        if pc.type == "ollama":
            return OllamaProvider(
                base_url=pc.base_url or "http://localhost:11434",
                default_model=default_model or "llama3.2",
                timeout=pc.timeout,
            )
        if pc.type == "deepseek":
            from leagent.llm.providers.deepseek import DeepSeekProvider
            return DeepSeekProvider(
                api_key=api_key,
                base_url=pc.base_url or DeepSeekProvider.DEFAULT_BASE_URL,
                default_model=default_model or DeepSeekProvider.DEFAULT_MODEL,
                timeout=pc.timeout,
            )
        if pc.type == "vllm":
            return VLLMProvider(
                api_key=api_key or "not-needed",
                base_url=pc.base_url or VLLMProvider.DEFAULT_BASE_URL,
                default_model=default_model,
                timeout=pc.timeout,
            )
        # Fallback: treat as OpenAI-compatible
        return OpenAIProvider(
            api_key=api_key or "not-needed",
            base_url=pc.base_url,
            default_model=default_model,
            timeout=pc.timeout,
        )

    @staticmethod
    def _resolve_api_key(raw: str) -> str:
        """Resolve ``${ENV_VAR}`` references in API key values."""
        if raw.startswith("${") and raw.endswith("}"):
            return os.getenv(raw[2:-1], "")
        return raw

    # -- CRUD ----------------------------------------------------------------

    def list_providers(self) -> list[ProviderConfig]:
        config = self._load_yaml()
        return [ProviderConfig.from_dict(e) for e in config.get("providers", [])]

    def get_provider(self, name: str) -> ProviderConfig | None:
        for p in self.list_providers():
            if p.name == name:
                return p
        return None

    def create_provider(self, data: dict[str, Any]) -> ProviderConfig:
        config = self._load_yaml()
        providers = config.get("providers", [])

        for p in providers:
            if p.get("name") == data["name"]:
                raise ValueError(f"Provider '{data['name']}' already exists")

        ptype = data.get("type", "custom")
        preset = PROVIDER_PRESETS.get(ptype, {})

        raw_base_url = data.get("base_url", preset.get("default_base_url", ""))
        if ptype == "deepseek" and raw_base_url:
            from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

            raw_base_url = normalize_deepseek_base_url(raw_base_url)

        pc = ProviderConfig(
            name=data["name"],
            type=ptype,
            enabled=data.get("enabled", True),
            api_key=data.get("api_key", ""),
            base_url=raw_base_url,
            models=data.get("models", preset.get("models", [])),
            timeout=data.get("timeout", 120),
            metadata=data.get("metadata", {}),
        )
        pc.models = validate_models_list(pc.models)
        self._maybe_warn_host_model_mismatch(pc, pc.name)

        providers.append(pc.to_dict())
        config["providers"] = providers

        # Convenience: if no default provider/model is set yet, promote the
        # first successfully created enabled provider as the default so the
        # system immediately starts using it for tier routing.
        if pc.enabled and not str(config.get("default_provider") or "").strip():
            dm = _first_enabled_model(pc.models)
            if dm:
                config["default_provider"] = pc.name
                config["default_model"] = dm

        self._save_yaml(config)

        if pc.enabled:
            self._register_single(pc)

        return pc

    def update_provider(self, name: str, data: dict[str, Any]) -> ProviderConfig:
        config = self._load_yaml()
        providers = config.get("providers", [])

        idx = None
        for i, p in enumerate(providers):
            if p.get("name") == name:
                idx = i
                break
        if idx is None:
            raise ValueError(f"Provider '{name}' not found")

        existing = providers[idx]
        for key in ("api_key", "base_url", "models", "enabled", "timeout", "metadata", "type"):
            if key in data:
                existing[key] = data[key]

        if existing.get("type") == "deepseek" and existing.get("base_url"):
            from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

            existing["base_url"] = normalize_deepseek_base_url(str(existing["base_url"]))

        pc = ProviderConfig.from_dict(existing)
        pc.models = validate_models_list(pc.models)
        existing["models"] = pc.models
        self._maybe_warn_host_model_mismatch(pc, name)
        had_any_default = bool(str(config.get("default_provider") or "").strip())
        self._clear_default_if_invalid_for_provider(config, pc)

        # If there is no default provider/model configured yet and this update
        # results in an enabled provider with at least one enabled model,
        # promote it as the default. This matches user expectations in the
        # Admin UI: configuring a provider should make it take effect without
        # requiring a separate default-model action.
        #
        # If we just cleared a stale default (invalid model for this provider),
        # do not auto-pick a replacement — the operator should set default explicitly.
        if (
            pc.enabled
            and not str(config.get("default_provider") or "").strip()
            and not had_any_default
        ):
            dm = _first_enabled_model(pc.models)
            if dm:
                config["default_provider"] = pc.name
                config["default_model"] = dm

        config["providers"] = providers
        self._save_yaml(config)

        # Re-register to pick up changes
        if self._registry.has_provider(name):
            self._registry.unregister(name)
        if pc.enabled:
            self._register_single(pc)

        return pc

    def delete_provider(self, name: str) -> None:
        config = self._load_yaml()
        providers = config.get("providers", [])
        config["providers"] = [p for p in providers if p.get("name") != name]

        if config.get("default_provider") == name:
            config["default_provider"] = ""
            config["default_model"] = ""

        self._save_yaml(config)

        if self._registry.has_provider(name):
            self._registry.unregister(name)

    def _register_single(self, pc: ProviderConfig) -> None:
        try:
            provider = self._create_llm_provider(pc)
            if self._registry.has_provider(pc.name):
                self._registry.unregister(pc.name)
            self._registry.register(
                pc.name,
                provider,
                metadata={
                    "type": pc.type,
                    "models": [m.get("name", "") for m in pc.models],
                },
            )
        except Exception:
            logger.warning("Failed to register provider %s", pc.name, exc_info=True)

    # -- default model -------------------------------------------------------

    def get_default(self) -> DefaultModelConfig:
        config = self._load_yaml()
        return DefaultModelConfig(
            provider=config.get("default_provider", ""),
            model=config.get("default_model", ""),
        )

    def set_default(self, provider: str, model: str) -> DefaultModelConfig:
        pc = self.get_provider(provider)
        if not pc:
            raise ProviderConfigValidationError(f"Provider '{provider}' not found")
        allowed = enabled_model_names(pc.models)
        if not allowed:
            raise ProviderConfigValidationError(
                f"Provider '{provider}' has no enabled models; configure at least one model first."
            )
        if model not in allowed:
            preview = ", ".join(allowed[:12])
            if len(allowed) > 12:
                preview += ", ..."
            raise ProviderConfigValidationError(
                f"Model '{model}' is not an enabled model for provider '{provider}'. Allowed: {preview}"
            )

        config = self._load_yaml()
        config["default_provider"] = provider
        config["default_model"] = model
        self._save_yaml(config)
        return DefaultModelConfig(provider=provider, model=model)

    def _clear_default_if_invalid_for_provider(self, config: dict[str, Any], pc: ProviderConfig) -> None:
        if config.get("default_provider") != pc.name:
            return
        dm = (config.get("default_model") or "").strip()
        allowed = set(enabled_model_names(pc.models))
        if not dm or dm not in allowed:
            logger.warning(
                "Clearing default_provider/default_model: default %r/%r is not valid for provider %r.",
                config.get("default_provider"),
                dm,
                pc.name,
            )
            config["default_provider"] = ""
            config["default_model"] = ""

    def _maybe_warn_host_model_mismatch(self, pc: ProviderConfig, logical_name: str) -> None:
        if pc.type not in ("custom", "openai"):
            return
        host = (urlparse(pc.base_url or "").hostname or "").lower()
        if "deepseek" not in host:
            return
        for m in pc.models:
            mn = (m.get("name") or "").lower()
            if "qwen" in mn:
                logger.warning(
                    "Provider %r: URL host suggests DeepSeek but model id %r contains 'qwen'; "
                    "confirm IDs match your gateway documentation.",
                    logical_name,
                    m.get("name"),
                )
                break

    # -- test connectivity ---------------------------------------------------

    async def test_provider(self, name: str, model: str | None = None) -> HealthCheckResult:
        pc = self.get_provider(name)
        if not pc:
            return HealthCheckResult(
                provider_name=name, is_healthy=False, error=f"Provider '{name}' not found"
            )

        if not self._registry.has_provider(name):
            self._register_single(pc)
            if not self._registry.has_provider(name):
                return HealthCheckResult(
                    provider_name=name, is_healthy=False, error="Failed to instantiate provider"
                )

        info = self._registry.get_provider_info(name)
        test_model = model or (pc.models[0]["name"] if pc.models else info.provider.default_model)

        start = time.perf_counter()
        try:
            from leagent.llm.base import ChatMessage

            await info.provider.complete(
                messages=[ChatMessage.user("Say hello in one word.")],
                model=test_model,
                max_tokens=20,
            )
            latency = (time.perf_counter() - start) * 1000

            # Chat uses the streaming path; SOCKS/proxy/TLS issues sometimes only break SSE.
            async def _first_stream_chunk() -> object | None:
                async for chunk in info.provider.stream(
                    messages=[ChatMessage.user("Say hi.")],
                    model=test_model,
                    max_tokens=12,
                    temperature=0.1,
                ):
                    return chunk
                return None

            try:
                first = await asyncio.wait_for(_first_stream_chunk(), timeout=90.0)
            except asyncio.TimeoutError:
                return HealthCheckResult(
                    provider_name=name,
                    is_healthy=False,
                    latency_ms=latency,
                    error=(
                        "Non-stream completion succeeded, but streaming probe timed out after 90s. "
                        "Check proxy/VPN (SOCKS) and backend logs."
                    ),
                )
            except Exception as stream_exc:
                detail = str(stream_exc) or repr(stream_exc)
                return HealthCheckResult(
                    provider_name=name,
                    is_healthy=False,
                    latency_ms=latency,
                    error=(
                        f"Non-stream OK; streaming failed ({type(stream_exc).__name__}): {detail}"
                    ),
                )

            if first is None:
                return HealthCheckResult(
                    provider_name=name,
                    is_healthy=False,
                    latency_ms=latency,
                    error="Non-stream OK; streaming returned no chunks.",
                )

            return HealthCheckResult(
                provider_name=name,
                is_healthy=True,
                latency_ms=latency,
            )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            detail = str(exc) or repr(exc)
            return HealthCheckResult(
                provider_name=name,
                is_healthy=False,
                latency_ms=latency,
                error=f"{type(exc).__name__}: {detail}",
            )

    # -- presets -------------------------------------------------------------

    @staticmethod
    def get_presets() -> dict[str, dict[str, Any]]:
        return PROVIDER_PRESETS


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_service: ProviderConfigService | None = None


def get_provider_config_service() -> ProviderConfigService:
    """Return (or create) the module-level singleton."""
    global _service
    if _service is None:
        _service = ProviderConfigService()
    return _service
