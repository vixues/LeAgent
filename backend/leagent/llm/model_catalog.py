"""Centralized model catalog and provider presets.

This module is the single source of truth for default model definitions,
provider type metadata, and model capability information.  User overrides
live in ``~/.leagent/providers.yaml``; this module defines the *code-level*
defaults that populate the YAML on first run and drive the Admin UI presets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ModelCapability:
    """Describes a single model's capabilities and pricing."""

    name: str
    tier: str = ""
    context_window: int = 0
    price_input_per_1m: float = 0.0
    price_output_per_1m: float = 0.0
    supports_tools: bool = False
    supports_vision: bool = False
    supports_thinking: bool = False
    description: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name}
        if self.tier:
            d["tier"] = self.tier
        if self.context_window:
            d["context_window"] = self.context_window
        if self.price_input_per_1m:
            d["price_input_per_1m"] = self.price_input_per_1m
        if self.price_output_per_1m:
            d["price_output_per_1m"] = self.price_output_per_1m
        if self.supports_tools:
            d["supports_tools"] = True
        if self.supports_vision:
            d["supports_vision"] = True
        if self.supports_thinking:
            d["supports_thinking"] = True
        if self.description:
            d["description"] = self.description
        if not self.enabled:
            d["enabled"] = False
        return d


@dataclass(frozen=True)
class ProviderPreset:
    """Metadata for a provider type (label, default URL, model catalog)."""

    label: str
    default_base_url: str = ""
    requires_api_key: bool = True
    models: tuple[ModelCapability, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "default_base_url": self.default_base_url,
            "requires_api_key": self.requires_api_key,
            "models": [m.to_dict() for m in self.models],
        }


# ---------------------------------------------------------------------------
# Provider presets -- the canonical model catalog
# ---------------------------------------------------------------------------

PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        label="OpenAI",
        default_base_url="https://api.openai.com/v1",
        requires_api_key=True,
        models=(
            ModelCapability(
                name="gpt-4o", tier="tier1", context_window=128_000,
                price_input_per_1m=2.50, price_output_per_1m=10.00,
                supports_tools=True, supports_vision=True,
                description="Flagship multimodal model — strong reasoning, vision, and tool use.",
            ),
            ModelCapability(
                name="gpt-4o-mini", tier="tier2", context_window=128_000,
                price_input_per_1m=0.15, price_output_per_1m=0.60,
                supports_tools=True, supports_vision=True,
                description="Affordable, intelligent small model for fast, lightweight tasks.",
            ),
            ModelCapability(
                name="o3-mini", tier="tier1", context_window=200_000,
                price_input_per_1m=1.10, price_output_per_1m=4.40,
                supports_tools=True,
                description="Reasoning model — thinks step-by-step. Use reasoning_effort to control depth.",
            ),
        ),
    ),
    "anthropic": ProviderPreset(
        label="Anthropic",
        default_base_url="https://api.anthropic.com",
        requires_api_key=True,
        models=(
            ModelCapability(
                name="claude-sonnet-4-20250514", tier="tier1", context_window=200_000,
                price_input_per_1m=3.00, price_output_per_1m=15.00,
                supports_tools=True, supports_vision=True,
                description="High-performance Claude model with extended thinking.",
            ),
            ModelCapability(
                name="claude-opus-4-7", tier="tier1", context_window=200_000,
                price_input_per_1m=15.00, price_output_per_1m=75.00,
                supports_tools=True, supports_vision=True,
                description="Most capable Claude model — adaptive thinking, task budgets.",
            ),
            ModelCapability(
                name="claude-3-5-haiku-20241022", tier="tier2", context_window=200_000,
                price_input_per_1m=0.80, price_output_per_1m=4.00,
                supports_tools=True, supports_vision=True,
                description="Fast, affordable Claude model for lightweight tasks.",
            ),
        ),
    ),
    "qwen": ProviderPreset(
        label="Qwen (通义千问)",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        requires_api_key=True,
        models=(
            ModelCapability(
                name="qwen3-max", tier="tier1", context_window=128_000,
                price_input_per_1m=10.00, price_output_per_1m=30.00,
                supports_tools=True, supports_thinking=True,
                description="Qwen3-Max — strongest reasoning with thinking mode.",
            ),
            ModelCapability(
                name="qwen3.5-plus", tier="tier1", context_window=128_000,
                price_input_per_1m=2.00, price_output_per_1m=8.00,
                supports_tools=True, supports_thinking=True,
                description="Qwen3.5-Plus — balanced performance and cost.",
            ),
            ModelCapability(
                name="qwen-plus", tier="tier2", context_window=128_000,
                price_input_per_1m=0.80, price_output_per_1m=2.00,
                supports_tools=True,
                description="Qwen-Plus — cost-effective general-purpose model.",
            ),
            ModelCapability(
                name="qwen3.5-flash", tier="tier2", context_window=128_000,
                price_input_per_1m=0.30, price_output_per_1m=0.60,
                supports_tools=True, supports_thinking=True,
                description="Qwen3.5-Flash — fast and cost-effective.",
            ),
            ModelCapability(
                name="qwq-plus", tier="tier1", context_window=128_000,
                price_input_per_1m=3.00, price_output_per_1m=12.00,
                supports_tools=True, supports_thinking=True,
                description="QwQ-Plus — specialized reasoning model.",
            ),
            ModelCapability(
                name="qwen-long", tier="tier1", context_window=1_000_000,
                price_input_per_1m=0.50, price_output_per_1m=2.00,
                supports_tools=True,
                description="Long-context Qwen — up to 1M tokens via file API.",
            ),
            ModelCapability(
                name="qwen-vl-max", tier="tier1", context_window=128_000,
                price_input_per_1m=10.00, price_output_per_1m=30.00,
                supports_tools=True,
                description="Qwen-VL-Max — multimodal vision-language model.",
            ),
        ),
    ),
    "deepseek": ProviderPreset(
        label="DeepSeek",
        default_base_url="https://api.deepseek.com",
        requires_api_key=True,
        models=(
            ModelCapability(
                name="deepseek-v4-flash", tier="tier2", context_window=1_000_000,
                price_input_per_1m=0.14, price_output_per_1m=0.28,
                supports_tools=True,
                description="DeepSeek-V4 Flash — fast default. V4 preview: https://api-docs.deepseek.com/news/news260424",
            ),
            ModelCapability(
                name="deepseek-v4-pro", tier="tier1", context_window=1_000_000,
                price_input_per_1m=1.74, price_output_per_1m=3.48,
                supports_tools=True,
                description="DeepSeek-V4 Pro (current API). See https://api-docs.deepseek.com/quick_start/pricing",
            ),
        ),
    ),
    "ollama": ProviderPreset(
        label="Ollama (本地模型)",
        default_base_url="http://localhost:11434",
        requires_api_key=False,
        models=(),
    ),
    "vllm": ProviderPreset(
        label="vLLM (本地/远程自托管模型)",
        default_base_url="http://localhost:8000/v1",
        requires_api_key=True,
        models=(),
    ),
    "custom": ProviderPreset(
        label="自定义 API (OpenAI 兼容)",
        default_base_url="",
        requires_api_key=True,
        models=(),
    ),
}


# ---------------------------------------------------------------------------
# Legacy-compatible dict form (consumed by existing code expecting plain dicts)
# ---------------------------------------------------------------------------

def get_provider_presets_dict() -> dict[str, dict[str, Any]]:
    """Return presets as plain dicts for backward compatibility."""
    return {k: v.to_dict() for k, v in PROVIDER_PRESETS.items()}


def get_default_models(provider_type: str) -> list[dict[str, Any]]:
    """Return the default model list for a provider type as plain dicts."""
    preset = PROVIDER_PRESETS.get(provider_type)
    if not preset:
        return []
    return [m.to_dict() for m in preset.models]


def get_preset_label(provider_type: str) -> str:
    """Return the human-readable label for a provider type."""
    preset = PROVIDER_PRESETS.get(provider_type)
    return preset.label if preset else provider_type


def get_default_base_url(provider_type: str) -> str:
    """Return the default base URL for a provider type."""
    preset = PROVIDER_PRESETS.get(provider_type)
    return preset.default_base_url if preset else ""


def requires_api_key(provider_type: str) -> bool:
    """Return whether a provider type requires an API key."""
    preset = PROVIDER_PRESETS.get(provider_type)
    return preset.requires_api_key if preset else True


def get_default_pricing() -> dict[str, dict[str, float]]:
    """Build default pricing from the model catalog for cost estimation."""
    pricing: dict[str, dict[str, float]] = {}
    for preset in PROVIDER_PRESETS.values():
        for m in preset.models:
            if m.price_input_per_1m or m.price_output_per_1m:
                pricing[m.name] = {
                    "input_per_1m": m.price_input_per_1m,
                    "output_per_1m": m.price_output_per_1m,
                }
    return pricing
