"""Default v2 providers.yaml builder and preset templates."""

from __future__ import annotations

from typing import Any

PROVIDERS_CONFIG_VERSION = 2


def _chat_model(
    name: str,
    *,
    context_window: int = 128_000,
    tool_call: bool = True,
    reasoning: bool = False,
    vision: bool = False,
    input_per_1m: float = 0.0,
    output_per_1m: float = 0.0,
    description: str = "",
) -> dict[str, Any]:
    caps: dict[str, Any] = {
        "input": ["text", "image"] if vision else ["text"],
        "output": ["text"],
    }
    if tool_call:
        caps["tool_call"] = True
    if reasoning:
        caps["reasoning"] = True
    entry: dict[str, Any] = {
        "name": name,
        "kind": "chat",
        "enabled": True,
        "context_window": context_window,
        "capabilities": caps,
    }
    if input_per_1m or output_per_1m:
        entry["pricing"] = {"input_per_1m": input_per_1m, "output_per_1m": output_per_1m}
    if description:
        entry["description"] = description
    return entry


def build_default_v2_config(
    *,
    deepseek_key: str = "",
    dashscope_key: str = "",
    openai_key: str = "",
    anthropic_key: str = "",
) -> dict[str, Any]:
    """Build a fresh providers.yaml v2 document from detected API keys."""
    providers: list[dict[str, Any]] = []

    if deepseek_key:
        providers.append({
            "name": "deepseek",
            "type": "deepseek",
            "enabled": True,
            "api_key": "${DEEPSEEK_API_KEY}" if deepseek_key.startswith("${") else deepseek_key,
            "base_url": "https://api.deepseek.com",
            "models": [
                _chat_model(
                    "deepseek-v4-pro",
                    context_window=1_000_000,
                    tool_call=True,
                    input_per_1m=1.74,
                    output_per_1m=3.48,
                    description="DeepSeek V4 Pro",
                ),
                _chat_model(
                    "deepseek-v4-flash",
                    context_window=1_000_000,
                    tool_call=True,
                    input_per_1m=0.14,
                    output_per_1m=0.28,
                    description="DeepSeek V4 Flash",
                ),
            ],
        })

    if dashscope_key:
        providers.append({
            "name": "dashscope",
            "type": "qwen",
            "enabled": True,
            "api_key": "${DASHSCOPE_API_KEY}" if dashscope_key.startswith("${") else dashscope_key,
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "models": [
                _chat_model("qwen3-max", tool_call=True, reasoning=True, context_window=128_000),
                _chat_model("qwen-plus", tool_call=True, context_window=128_000),
                _chat_model("qwen3.5-flash", tool_call=True, context_window=128_000),
                _chat_model("qwen-vl-max", tool_call=True, vision=True, context_window=128_000),
            ],
        })

    if openai_key:
        openai_models: list[dict[str, Any]] = [
            _chat_model("gpt-4o", vision=True, tool_call=True, context_window=128_000,
                        input_per_1m=2.5, output_per_1m=10.0),
            _chat_model("gpt-4o-mini", vision=True, tool_call=True, context_window=128_000,
                        input_per_1m=0.15, output_per_1m=0.60),
            {
                "name": "text-embedding-3-small",
                "kind": "embedding",
                "enabled": True,
                "capabilities": {"input": ["text"], "output": ["text"]},
            },
            {
                "name": "dall-e-3",
                "kind": "image_gen",
                "enabled": True,
                "capabilities": {"input": ["text"], "output": ["image"]},
                "limits": {"sizes": ["1024x1024", "1024x1792", "1792x1024"]},
            },
        ]
        providers.append({
            "name": "openai",
            "type": "openai",
            "enabled": True,
            "api_key": "${OPENAI_API_KEY}" if openai_key.startswith("${") else openai_key,
            "base_url": "https://api.openai.com/v1",
            "models": openai_models,
        })

    if anthropic_key:
        providers.append({
            "name": "anthropic",
            "type": "anthropic",
            "enabled": True,
            "api_key": "${ANTHROPIC_API_KEY}" if anthropic_key.startswith("${") else anthropic_key,
            "models": [
                _chat_model(
                    "claude-sonnet-4-20250514",
                    vision=True,
                    tool_call=True,
                    context_window=200_000,
                ),
                _chat_model(
                    "claude-3-5-haiku-20241022",
                    vision=True,
                    tool_call=True,
                    context_window=200_000,
                ),
            ],
        })

    chat_provider = "deepseek" if deepseek_key else (
        "dashscope" if dashscope_key else (
            "openai" if openai_key else ("anthropic" if anthropic_key else "")
        )
    )
    chat_model = "deepseek-v4-pro" if chat_provider == "deepseek" else (
        "qwen3-max" if chat_provider == "dashscope" else (
            "gpt-4o" if chat_provider == "openai" else "claude-sonnet-4-20250514"
        )
    )
    fast_model = "deepseek-v4-flash" if chat_provider == "deepseek" else (
        "qwen3.5-flash" if chat_provider == "dashscope" else "gpt-4o-mini"
    )

    routing_tasks: dict[str, Any] = {
        "chat": {"provider": chat_provider, "model": chat_model},
        "fast": {"provider": chat_provider, "model": fast_model},
        "compression": {"inherit": "fast"},
        "title": {"inherit": "fast"},
    }
    if dashscope_key or openai_key or anthropic_key:
        vision_provider = "dashscope" if dashscope_key else chat_provider
        vision_model = "qwen-vl-max" if vision_provider == "dashscope" else chat_model
        routing_tasks["vision"] = {"provider": vision_provider, "model": vision_model}
    if openai_key:
        routing_tasks["embedding"] = {"provider": "openai", "model": "text-embedding-3-small"}
        routing_tasks["image_gen"] = {"provider": "openai", "model": "dall-e-3"}

    return {
        "version": PROVIDERS_CONFIG_VERSION,
        "default_task": "chat",
        "providers": providers,
        "routing": {
            "tasks": routing_tasks,
            "fallbacks": {},
            "failover": {"enabled": False, "max_retries": 2},
        },
    }


def validate_v2_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a v2 providers config. Raises ProviderConfigValidationError."""
    from leagent.llm.provider_config import ProviderConfigValidationError, validate_models_list

    version = config.get("version")
    if version != PROVIDERS_CONFIG_VERSION:
        raise ProviderConfigValidationError(
            f"Unsupported providers.yaml version {version!r}. "
            f"Expected version {PROVIDERS_CONFIG_VERSION}. "
            "Run: leagent providers migrate"
        )

    providers_raw = config.get("providers")
    if not isinstance(providers_raw, list) or not providers_raw:
        raise ProviderConfigValidationError("'providers' must be a non-empty list")

    normalized_providers: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for entry in providers_raw:
        if not isinstance(entry, dict):
            raise ProviderConfigValidationError("Each provider must be an object")
        name = str(entry.get("name") or "").strip()
        if not name:
            raise ProviderConfigValidationError("Provider name cannot be empty")
        if name in seen_names:
            raise ProviderConfigValidationError(f"Duplicate provider name: {name}")
        seen_names.add(name)
        models = validate_models_list_v2(entry.get("models") or [])
        normalized_providers.append({**entry, "name": name, "models": models})

    routing = config.get("routing")
    if not isinstance(routing, dict):
        routing = {}
    tasks = routing.get("tasks")
    if not isinstance(tasks, dict) or not tasks.get("chat"):
        raise ProviderConfigValidationError("routing.tasks.chat is required")

    normalized = {
        "version": PROVIDERS_CONFIG_VERSION,
        "default_task": str(config.get("default_task") or "chat"),
        "providers": normalized_providers,
        "routing": routing,
        "pricing": config.get("pricing") if isinstance(config.get("pricing"), dict) else {},
    }
    # Preserve the image-generation section (presets + backend credentials +
    # local-diffusion settings) so the art ``GenerationService`` config managed
    # by ``ImageGenConfigStore`` survives chat-provider round-trips.
    if isinstance(config.get("image_gen"), dict):
        normalized["image_gen"] = config["image_gen"]
    return normalized


def validate_models_list_v2(models: list[Any]) -> list[dict[str, Any]]:
    """Validate v2 model entries."""
    from leagent.llm.provider_config import ProviderConfigValidationError

    if not models:
        raise ProviderConfigValidationError("At least one model is required")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for raw in models:
        if not isinstance(raw, dict):
            raise ProviderConfigValidationError("Each model must be an object")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ProviderConfigValidationError("Model name cannot be empty")
        if name in seen:
            raise ProviderConfigValidationError(f"Duplicate model name: {name}")
        seen.add(name)
        kind = str(raw.get("kind") or "chat").strip().lower()
        if kind not in ("chat", "embedding", "image_gen"):
            raise ProviderConfigValidationError(f"Invalid model kind: {kind}")
        caps = raw.get("capabilities")
        if not isinstance(caps, dict):
            caps = {"input": ["text"], "output": ["text"]}
        out.append({**raw, "name": name, "kind": kind, "capabilities": caps})
    return out
