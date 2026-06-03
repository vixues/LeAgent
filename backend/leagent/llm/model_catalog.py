"""Centralized model catalog and provider presets (providers.yaml v2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from leagent.llm.model_spec import ModelCapabilities


@dataclass(frozen=True)
class ModelPreset:
    """Preset model entry for Admin UI templates."""

    name: str
    kind: str = "chat"
    context_window: int = 0
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    description: str = ""
    pricing: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "enabled": True,
            "capabilities": self.capabilities.to_dict(),
        }
        if self.context_window:
            d["context_window"] = self.context_window
        if self.description:
            d["description"] = self.description
        if self.pricing:
            d["pricing"] = dict(self.pricing)
        return d


def _chat(
    name: str,
    *,
    context_window: int = 128_000,
    tool_call: bool = True,
    reasoning: bool = False,
    vision: bool = False,
    input_per_1m: float = 0.0,
    output_per_1m: float = 0.0,
    description: str = "",
) -> ModelPreset:
    inp = frozenset({"text", "image"} if vision else {"text"})
    caps = ModelCapabilities(input=inp, output=frozenset({"text"}), tool_call=tool_call, reasoning=reasoning)
    pricing: dict[str, float] = {}
    if input_per_1m:
        pricing["input_per_1m"] = input_per_1m
    if output_per_1m:
        pricing["output_per_1m"] = output_per_1m
    return ModelPreset(
        name=name,
        kind="chat",
        context_window=context_window,
        capabilities=caps,
        description=description,
        pricing=pricing,
    )


@dataclass(frozen=True)
class ProviderPreset:
    label: str
    default_base_url: str = ""
    requires_api_key: bool = True
    models: tuple[ModelPreset, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "default_base_url": self.default_base_url,
            "requires_api_key": self.requires_api_key,
            "models": [m.to_dict() for m in self.models],
        }


PROVIDER_PRESETS: dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        label="OpenAI",
        default_base_url="https://api.openai.com/v1",
        models=(
            _chat("gpt-4o", vision=True, tool_call=True, context_window=128_000,
                  input_per_1m=2.50, output_per_1m=10.00,
                  description="Flagship multimodal model"),
            _chat("gpt-4o-mini", vision=True, tool_call=True, context_window=128_000,
                  input_per_1m=0.15, output_per_1m=0.60),
            ModelPreset(
                name="text-embedding-3-small",
                kind="embedding",
                capabilities=ModelCapabilities(input=frozenset({"text"}), output=frozenset({"text"})),
            ),
            ModelPreset(
                name="dall-e-3",
                kind="image_gen",
                capabilities=ModelCapabilities(input=frozenset({"text"}), output=frozenset({"image"})),
            ),
        ),
    ),
    "anthropic": ProviderPreset(
        label="Anthropic",
        default_base_url="https://api.anthropic.com",
        models=(
            _chat("claude-sonnet-4-20250514", vision=True, tool_call=True, context_window=200_000,
                  input_per_1m=3.00, output_per_1m=15.00),
            _chat("claude-opus-4-7", vision=True, tool_call=True, context_window=200_000,
                  input_per_1m=15.00, output_per_1m=75.00),
            _chat("claude-3-5-haiku-20241022", vision=True, tool_call=True, context_window=200_000,
                  input_per_1m=0.80, output_per_1m=4.00),
        ),
    ),
    "qwen": ProviderPreset(
        label="Qwen (通义千问)",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=(
            _chat("qwen3-max", tool_call=True, reasoning=True, context_window=128_000),
            _chat("qwen3.5-plus", tool_call=True, reasoning=True, context_window=128_000),
            _chat("qwen-plus", tool_call=True, context_window=128_000),
            _chat("qwen3.5-flash", tool_call=True, context_window=128_000),
            _chat("qwen-vl-max", vision=True, tool_call=True, context_window=128_000,
                  description="Multimodal vision-language model"),
            ModelPreset(
                name="wanx-v1",
                kind="image_gen",
                capabilities=ModelCapabilities(input=frozenset({"text"}), output=frozenset({"image"})),
                description="DashScope Wanx text-to-image",
            ),
        ),
    ),
    "deepseek": ProviderPreset(
        label="DeepSeek",
        default_base_url="https://api.deepseek.com",
        models=(
            _chat("deepseek-v4-flash", tool_call=True, context_window=1_000_000,
                  input_per_1m=0.14, output_per_1m=0.28),
            _chat("deepseek-v4-pro", tool_call=True, context_window=1_000_000,
                  input_per_1m=1.74, output_per_1m=3.48),
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
        models=(),
    ),
    "custom": ProviderPreset(
        label="自定义 API (OpenAI 兼容)",
        default_base_url="",
        models=(),
    ),
}


def get_provider_presets_dict() -> dict[str, dict[str, Any]]:
    return {k: v.to_dict() for k, v in PROVIDER_PRESETS.items()}


def get_default_models(provider_type: str) -> list[dict[str, Any]]:
    preset = PROVIDER_PRESETS.get(provider_type)
    if not preset:
        return []
    return [m.to_dict() for m in preset.models]


def get_preset_label(provider_type: str) -> str:
    preset = PROVIDER_PRESETS.get(provider_type)
    return preset.label if preset else provider_type


def get_default_base_url(provider_type: str) -> str:
    preset = PROVIDER_PRESETS.get(provider_type)
    return preset.default_base_url if preset else ""


def requires_api_key(provider_type: str) -> bool:
    preset = PROVIDER_PRESETS.get(provider_type)
    return preset.requires_api_key if preset else True


def get_default_pricing() -> dict[str, dict[str, float]]:
    pricing: dict[str, dict[str, float]] = {}
    for preset in PROVIDER_PRESETS.values():
        for m in preset.models:
            if m.pricing:
                pricing[m.name] = dict(m.pricing)
    return pricing
