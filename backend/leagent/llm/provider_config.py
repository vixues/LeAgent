"""Persistent provider configuration service.

Manages LLM provider configs in ``~/.leagent/providers.yaml`` and keeps the
in-memory :class:`ProviderRegistry` in sync.  Both the HTTP API and the CLI
share this module so that changes made in one surface are immediately visible
in the other.
"""

from __future__ import annotations

import asyncio
import shutil
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from leagent.config.constants import PROVIDERS_PATH
from leagent.llm.error_policy import classify_llm_error
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
    """Require at least one v2 model entry with valid kind/capabilities."""
    from leagent.llm.providers_schema import validate_models_list_v2

    return validate_models_list_v2(models)


# ---------------------------------------------------------------------------
# Provider type presets — imported from the centralized model catalog
# ---------------------------------------------------------------------------

from leagent.llm.model_catalog import (
    PROVIDER_PRESETS as _CATALOG_PRESETS,
    get_provider_presets_dict as _get_presets_dict,
)

# Backward-compatible plain-dict form used throughout the codebase.
PROVIDER_PRESETS: dict[str, dict[str, Any]] = _get_presets_dict()


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
        self._health_monitor_task: asyncio.Task[None] | None = None
        self._load_and_sync()

    # -- public properties ---------------------------------------------------

    @property
    def registry(self) -> ProviderRegistry:
        return self._registry

    # -- YAML I/O ------------------------------------------------------------

    def _load_yaml(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._auto_init_from_env()
        with open(self._path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return self._auto_init_from_env()
        from leagent.llm.providers_schema import validate_v2_config

        if data.get("version") != 2:
            raise ProviderConfigValidationError(
                f"Unsupported providers.yaml version {data.get('version')!r}. "
                "Expected version 2. Run: leagent providers migrate"
            )
        if self._migrate_legacy_deepseek_config(data):
            self._save_yaml(data)
        normalized = validate_v2_config(data)
        self._sync_legacy_default_fields(normalized)
        return normalized

    def _sync_legacy_default_fields(self, config: dict[str, Any]) -> None:
        """Keep default_provider/default_model aligned with routing.tasks.chat for Admin UI."""
        routing = config.get("routing") if isinstance(config.get("routing"), dict) else {}
        tasks = routing.get("tasks") if isinstance(routing.get("tasks"), dict) else {}
        chat = tasks.get("chat") if isinstance(tasks.get("chat"), dict) else {}
        provider = str(chat.get("provider") or config.get("default_provider") or "").strip()
        model = str(chat.get("model") or config.get("default_model") or "").strip()
        if provider:
            config["default_provider"] = provider
        if model:
            config["default_model"] = model

    def _auto_init_from_env(self) -> dict[str, Any]:
        """Auto-create providers.yaml v2 from detected API keys on first run."""
        from leagent.config.settings import get_settings
        from leagent.llm.providers_schema import build_default_v2_config

        settings = get_settings()
        config = build_default_v2_config(
            deepseek_key=settings.llm.deepseek_api_key or "${DEEPSEEK_API_KEY}",
            dashscope_key=settings.llm.dashscope_api_key or "${DASHSCOPE_API_KEY}",
            openai_key=settings.llm.openai_api_key or "${OPENAI_API_KEY}",
            anthropic_key=settings.llm.anthropic_api_key or "${ANTHROPIC_API_KEY}",
        )
        # Only persist when at least one real key is present
        has_key = any(
            getattr(settings.llm, f"{name}_api_key", "")
            for name in ("deepseek", "dashscope", "openai", "anthropic")
        )
        if config.get("providers") and has_key:
            logger.info(
                "Auto-initialized providers.yaml v2 with %d provider(s)",
                len(config["providers"]),
            )
            self._save_yaml(config)
        elif not config.get("providers"):
            config = build_default_v2_config(deepseek_key="${DEEPSEEK_API_KEY}")
            self._save_yaml(config)
        return config

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
        from leagent.llm.providers.custom import CustomOpenAIProvider
        from leagent.llm.providers.dashscope import DashScopeProvider
        from leagent.llm.providers.ollama import OllamaProvider
        from leagent.llm.providers.openai import OpenAIProvider
        from leagent.llm.providers.vllm import VLLMProvider

        api_key = self._resolve_api_key(pc.api_key)
        default_model = pc.models[0]["name"] if pc.models else ""

        # Allow metadata.parse_think_tags to override per-type defaults.
        meta = pc.metadata if isinstance(pc.metadata, dict) else {}
        meta_parse_think = meta.get("parse_think_tags")

        if pc.type == "custom":
            return CustomOpenAIProvider(
                api_key=api_key or "not-needed",
                base_url=pc.base_url,
                default_model=default_model,
                timeout=pc.timeout,
                parse_think_tags=bool(meta_parse_think) if meta_parse_think is not None else True,
            )
        if pc.type in ("openai", "azure"):
            return OpenAIProvider(
                api_key=api_key or "not-needed",
                base_url=pc.base_url or "https://api.openai.com/v1",
                default_model=default_model or "gpt-4o",
                timeout=pc.timeout,
                parse_think_tags=bool(meta_parse_think) if meta_parse_think is not None else False,
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
            enable_auto_tool_choice = bool(meta.get("enable_auto_tool_choice", False))
            return VLLMProvider(
                api_key=api_key or "not-needed",
                base_url=pc.base_url or VLLMProvider.DEFAULT_BASE_URL,
                default_model=default_model,
                timeout=pc.timeout,
                enable_auto_tool_choice=enable_auto_tool_choice,
            )
        # Fallback: treat unknown types as tolerant OpenAI-compatible custom gateways.
        return CustomOpenAIProvider(
            api_key=api_key or "not-needed",
            base_url=pc.base_url,
            default_model=default_model,
            timeout=pc.timeout,
            parse_think_tags=bool(meta_parse_think) if meta_parse_think is not None else True,
        )

    def _create_image_gen_provider(self, pc: ProviderConfig, model_name: str):
        """Instantiate an image generation provider for *pc*."""
        from leagent.llm.image_gen.dashscope import DashScopeWanxProvider
        from leagent.llm.image_gen.openai import OpenAIImageGenProvider

        api_key = self._resolve_api_key(pc.api_key)
        if pc.type in ("openai", "azure", "custom"):
            return OpenAIImageGenProvider(
                api_key=api_key or "not-needed",
                base_url=pc.base_url or "https://api.openai.com/v1",
                timeout=float(pc.timeout),
            )
        if pc.type in ("qwen", "dashscope"):
            return DashScopeWanxProvider(
                api_key=api_key,
                base_url=pc.base_url or "https://dashscope.aliyuncs.com/api/v1",
                timeout=float(pc.timeout),
            )
        return OpenAIImageGenProvider(
            api_key=api_key or "not-needed",
            base_url=pc.base_url or "https://api.openai.com/v1",
            timeout=float(pc.timeout),
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

    def get_routing_config(self) -> dict[str, Any]:
        """Return model routing metadata from providers.yaml."""
        config = self._load_yaml()
        routing = config.get("routing")
        return routing if isinstance(routing, dict) else {}

    def get_pricing_config(self) -> dict[str, Any]:
        """Return editable model pricing metadata from providers.yaml."""
        config = self._load_yaml()
        pricing = config.get("pricing")
        return pricing if isinstance(pricing, dict) else {}

    def get_model_registry(self) -> "ModelRegistry":
        """Build a :class:`ModelRegistry` from the current YAML config."""
        from leagent.llm.model_registry import ModelRegistry

        catalog = ModelRegistry()
        catalog.load_from_config(self._load_yaml())
        return catalog

    def get_task_routing(self) -> dict[str, Any]:
        """Return routing.tasks from providers.yaml."""
        routing = self.get_routing_config()
        tasks = routing.get("tasks")
        return tasks if isinstance(tasks, dict) else {}

    def set_task_routing(self, tasks: dict[str, Any]) -> dict[str, Any]:
        """Persist routing.tasks and sync default_provider/default_model from chat."""
        if not isinstance(tasks, dict):
            raise ProviderConfigValidationError("'tasks' must be an object")
        config = self._load_yaml()
        routing = config.get("routing") if isinstance(config.get("routing"), dict) else {}
        routing["tasks"] = tasks
        config["routing"] = routing
        self._sync_legacy_default_fields(config)
        self._save_yaml(config)
        self._registry.clear()
        self._load_and_sync()
        return tasks

    def get_model_aliases(self) -> dict[str, str]:
        """Deprecated: v2 uses routing.tasks instead of aliases."""
        return {}

    def set_pricing_config(self, pricing: dict[str, Any]) -> dict[str, Any]:
        """Persist editable model pricing metadata."""
        config = self._load_yaml()
        config["pricing"] = pricing
        self._save_yaml(config)
        return pricing

    def export_config(self, *, include_secrets: bool = False) -> dict[str, Any]:
        """Return providers.yaml content, masking API keys by default."""
        config = self._load_yaml()
        if include_secrets:
            return config
        masked = dict(config)
        masked["providers"] = []
        for entry in config.get("providers", []):
            if not isinstance(entry, dict):
                continue
            item = dict(entry)
            if item.get("api_key"):
                item["api_key"] = "***"
            masked["providers"].append(item)
        return masked

    def import_config(self, data: dict[str, Any], *, merge: bool = True) -> dict[str, Any]:
        """Validate and import provider config data."""
        if not isinstance(data, dict):
            raise ProviderConfigValidationError("Config payload must be an object")
        incoming = data.get("providers", [])
        if not isinstance(incoming, list):
            raise ProviderConfigValidationError("'providers' must be a list")
        for entry in incoming:
            pc = ProviderConfig.from_dict(entry)
            validate_models_list(pc.models)

        current = self._load_yaml() if merge else {"providers": []}
        if merge:
            by_name = {
                str(entry.get("name")): entry
                for entry in current.get("providers", [])
                if isinstance(entry, dict) and entry.get("name")
            }
            for entry in incoming:
                if isinstance(entry, dict) and entry.get("name"):
                    if entry.get("api_key") == "***" and entry.get("name") in by_name:
                        entry = {**entry, "api_key": by_name[entry["name"]].get("api_key", "")}
                    by_name[str(entry["name"])] = entry
            current["providers"] = list(by_name.values())
            for key in ("default_provider", "default_model", "routing", "pricing"):
                if key in data:
                    current[key] = data[key]
        else:
            current = data
        self._save_yaml(current)
        self._registry.clear()
        self._load_and_sync()
        return current

    def create_backup(self) -> str:
        """Create a timestamped backup of providers.yaml."""
        ts = time.strftime("%Y%m%d-%H%M%S")
        backup_dir = self._path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup = backup_dir / f"providers-{ts}.yaml"
        if self._path.exists():
            shutil.copy2(self._path, backup)
        else:
            self._save_yaml(self._load_yaml())
            shutil.copy2(self._path, backup)
        return backup.name

    def list_backups(self) -> list[str]:
        backup_dir = self._path.parent / "backups"
        if not backup_dir.exists():
            return []
        return sorted(p.name for p in backup_dir.glob("providers-*.yaml"))

    def restore_backup(self, backup_id: str) -> dict[str, Any]:
        backup = self._path.parent / "backups" / backup_id
        if not backup.exists() or backup.parent != self._path.parent / "backups":
            raise FileNotFoundError(backup_id)
        shutil.copy2(backup, self._path)
        self._registry.clear()
        self._load_and_sync()
        return self._load_yaml()

    def start_health_monitor(self) -> None:
        """Start optional periodic provider health monitoring if configured."""
        routing = self.get_routing_config()
        health = routing.get("health_monitor")
        if not isinstance(health, dict) or not health.get("enabled"):
            return
        if self._health_monitor_task and not self._health_monitor_task.done():
            return
        interval = max(float(health.get("interval_seconds") or 300), 30.0)
        self._health_monitor_task = asyncio.create_task(self._health_monitor_loop(interval))

    def stop_health_monitor(self) -> None:
        """Stop the optional provider health monitor."""
        if self._health_monitor_task and not self._health_monitor_task.done():
            self._health_monitor_task.cancel()
        self._health_monitor_task = None

    async def _health_monitor_loop(self, interval: float) -> None:
        while True:
            try:
                await asyncio.gather(
                    *(self.test_provider(p.name) for p in self.list_providers() if p.enabled),
                    return_exceptions=True,
                )
            except Exception:
                logger.debug("provider_health_monitor_tick_failed", exc_info=True)
            await asyncio.sleep(interval)

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
        provider = str(config.get("default_provider") or "")
        model = str(config.get("default_model") or "")
        current = self.get_provider(provider) if provider else None
        if current and current.enabled:
            allowed = enabled_model_names(current.models)
            if allowed and (not model or model in allowed):
                return DefaultModelConfig(
                    provider=provider,
                    model=model or allowed[0],
                )
        for pc in self.list_providers():
            if not pc.enabled:
                continue
            fallback_model = _first_enabled_model(pc.models)
            if fallback_model:
                return DefaultModelConfig(provider=pc.name, model=fallback_model)
        return DefaultModelConfig(
            provider=provider,
            model=model,
        )

    def set_default(self, provider: str, model: str) -> DefaultModelConfig:
        pc = self.get_provider(provider)
        if not pc:
            raise ProviderConfigValidationError(f"Provider '{provider}' not found")
        if not pc.enabled:
            raise ProviderConfigValidationError(
                f"Provider '{provider}' is disabled; enable it before setting it as default."
            )
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
        routing = config.get("routing") if isinstance(config.get("routing"), dict) else {}
        tasks = routing.get("tasks") if isinstance(routing.get("tasks"), dict) else {}
        tasks["chat"] = {"provider": provider, "model": model}
        routing["tasks"] = tasks
        config["routing"] = routing
        self._save_yaml(config)
        self._registry.clear()
        self._load_and_sync()
        return DefaultModelConfig(provider=provider, model=model)

    def _clear_default_if_invalid_for_provider(self, config: dict[str, Any], pc: ProviderConfig) -> None:
        if config.get("default_provider") != pc.name:
            return
        dm = (config.get("default_model") or "").strip()
        allowed = set(enabled_model_names(pc.models))
        if not pc.enabled or not dm or dm not in allowed:
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
        test_config = pc.metadata.get("test_config") if isinstance(pc.metadata, dict) else {}
        if not isinstance(test_config, dict):
            test_config = {}
        test_model = (
            model
            or str(test_config.get("test_model") or "").strip()
            or (pc.models[0]["name"] if pc.models else getattr(info.provider, "default_model", ""))
            or info.provider._get_default_model()
        )
        start = time.perf_counter()
        if pc.type == "ollama":
            from leagent.llm.providers.ollama import OllamaProvider

            if isinstance(info.provider, OllamaProvider):
                try:
                    test_model = await info.provider.resolve_test_model(
                        preferred=test_model or None,
                        configured=[str(m.get("name") or "") for m in pc.models],
                    )
                except Exception as exc:
                    latency = (time.perf_counter() - start) * 1000
                    detail = str(exc) or repr(exc)
                    classification = classify_llm_error(exc)
                    info.is_healthy = False
                    info.last_health_check = time.time()
                    if classification.counts_against_provider:
                        info.circuit_breaker.record_failure(detail)
                    installed = []
                    try:
                        installed = await info.provider.get_installed_model_names()
                    except Exception:
                        pass
                    if installed:
                        detail = (
                            f"{detail}. Locally installed: {', '.join(sorted(installed)[:8])}"
                            + (" …" if len(installed) > 8 else "")
                        )
                    return HealthCheckResult(
                        provider_name=name,
                        is_healthy=False,
                        latency_ms=latency,
                        error=f"{type(exc).__name__}: {detail}",
                        status="failed",
                        error_category=classification.category.value,
                    )
        elif pc.type == "vllm":
            from leagent.llm.providers.vllm import VLLMProvider

            if isinstance(info.provider, VLLMProvider):
                test_model = await info.provider.resolve_test_model(
                    preferred=test_model if test_model != "default" else None,
                    configured=[str(m.get("name") or "") for m in pc.models],
                )
        prompt = str(test_config.get("test_prompt") or "Who are you?")
        timeout_secs = float(test_config.get("timeout_secs") or min(max(pc.timeout, 1), 90))
        degraded_threshold_ms = float(test_config.get("degraded_threshold_ms") or 6000)
        max_retries = int(test_config.get("max_retries") or 0)

        attempt = 0
        try:
            from leagent.llm.base import ChatMessage

            async def _stream_probe() -> tuple[object | None, float]:
                probe_start = time.perf_counter()
                async for chunk in info.provider.stream(
                    messages=[ChatMessage.user(prompt)],
                    model=test_model,
                    max_tokens=50,
                    temperature=0.1,
                ):
                    return chunk, (time.perf_counter() - probe_start) * 1000
                return None, (time.perf_counter() - probe_start) * 1000

            while True:
                try:
                    first, ttfb = await asyncio.wait_for(_stream_probe(), timeout=timeout_secs)
                    latency = (time.perf_counter() - start) * 1000
                    if first is None:
                        raise RuntimeError("Streaming probe returned no chunks")
                    status = "degraded" if ttfb > degraded_threshold_ms else "operational"
                    info.is_healthy = True
                    info.last_health_check = time.time()
                    info.circuit_breaker.record_success()
                    return HealthCheckResult(
                        provider_name=name,
                        is_healthy=True,
                        latency_ms=latency,
                        ttfb_ms=ttfb,
                        status=status,
                        tested_model=test_model,
                    )
                except asyncio.TimeoutError as exc:
                    attempt += 1
                    if attempt <= max_retries:
                        continue
                    raise TimeoutError(f"Streaming probe timed out after {timeout_secs:.0f}s") from exc
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000
            detail = str(exc) or repr(exc)
            classification = classify_llm_error(exc)
            info.is_healthy = False
            info.last_health_check = time.time()
            if classification.counts_against_provider:
                info.circuit_breaker.record_failure(detail)
            return HealthCheckResult(
                provider_name=name,
                is_healthy=False,
                latency_ms=latency,
                error=f"{type(exc).__name__}: {detail}",
                status="failed",
                error_category=classification.category.value,
            )

    async def discover_models(self, name: str) -> list[dict[str, Any]]:
        """Fetch available model IDs from provider APIs."""
        pc = self.get_provider(name)
        if not pc:
            raise ValueError(f"Provider '{name}' not found")

        configured = {str(m.get("name") or "") for m in pc.models}
        timeout = float(min(max(pc.timeout, 1), 60))

        import httpx

        if pc.type == "anthropic":
            models = PROVIDER_PRESETS.get("anthropic", {}).get("models", [])
            return [
                {**m, "id": m.get("name", ""), "already_configured": m.get("name", "") in configured}
                for m in models
            ]

        headers: dict[str, str] = {}
        api_key = self._resolve_api_key(pc.api_key)
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        base_url = (pc.base_url or "").rstrip("/")
        if not base_url:
            preset = PROVIDER_PRESETS.get(pc.type, {})
            base_url = str(preset.get("default_base_url") or "").rstrip("/")
        if not base_url:
            return []

        async with httpx.AsyncClient(timeout=timeout) as client:
            if pc.type == "ollama":
                response = await client.get(f"{base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                raw_models = data.get("models", []) if isinstance(data, dict) else []
                return [
                    {
                        "id": str(item.get("name") or ""),
                        "name": str(item.get("name") or ""),
                        "owned_by": "ollama",
                        "already_configured": str(item.get("name") or "") in configured,
                        "raw": item,
                    }
                    for item in raw_models
                    if isinstance(item, dict) and item.get("name")
                ]

            model_url = f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"
            response = await client.get(model_url, headers=headers)
            response.raise_for_status()
            data = response.json()
            raw_models = data.get("data", []) if isinstance(data, dict) else []
            return [
                {
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("id") or ""),
                    "owned_by": str(item.get("owned_by") or ""),
                    "created": item.get("created"),
                    "already_configured": str(item.get("id") or "") in configured,
                    "raw": item,
                }
                for item in raw_models
                if isinstance(item, dict) and item.get("id")
            ]

    async def speed_test_endpoints(self, name: str, candidates: list[str]) -> list[dict[str, Any]]:
        """Measure latency for candidate provider base URLs."""
        pc = self.get_provider(name)
        if not pc:
            raise ValueError(f"Provider '{name}' not found")
        import httpx

        api_key = self._resolve_api_key(pc.api_key)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        async def _probe(url: str) -> dict[str, Any]:
            normalized = url.rstrip("/")
            start = time.perf_counter()
            try:
                async with httpx.AsyncClient(timeout=min(max(pc.timeout, 1), 20)) as client:
                    if pc.type == "ollama":
                        resp = await client.get(f"{normalized}/api/tags")
                    else:
                        model_url = f"{normalized}/models" if normalized.endswith("/v1") else f"{normalized}/v1/models"
                        resp = await client.get(model_url, headers=headers)
                    resp.raise_for_status()
                return {
                    "url": normalized,
                    "ok": True,
                    "latency_ms": (time.perf_counter() - start) * 1000,
                    "error": "",
                }
            except Exception as exc:
                return {
                    "url": normalized,
                    "ok": False,
                    "latency_ms": (time.perf_counter() - start) * 1000,
                    "error": str(exc),
                }

        unique = [u for i, u in enumerate(candidates) if u and u not in candidates[:i]]
        results = await asyncio.gather(*(_probe(u) for u in unique))
        results.sort(key=lambda r: (not r["ok"], r["latency_ms"]))
        return results

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


def reset_provider_config_service() -> None:
    """Invalidate the module-level singleton so next access re-reads YAML."""
    global _service  # noqa: PLW0603
    _service = None
