"""Tests for task-based model resolution with image attachments and domain tasks."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from leagent.exceptions.llm import LLMServiceError, ModelNotFoundError
from leagent.llm.base import ChatMessage, MessageRole
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.model_spec import ModelCapabilities, ModelSpec, ModelTask
from leagent.llm.registry import ProviderRegistry
from leagent.llm.task_resolver import (
    TaskResolver,
    messages_contain_image,
    strip_image_blocks_from_messages,
)


def _text_spec(provider: str, model: str) -> ModelSpec:
    return ModelSpec(
        name=model,
        provider=provider,
        capabilities=ModelCapabilities(input=frozenset({"text"}), tool_call=True),
    )


def _vision_spec(provider: str, model: str) -> ModelSpec:
    return ModelSpec(
        name=model,
        provider=provider,
        capabilities=ModelCapabilities(
            input=frozenset({"text", "image"}),
            tool_call=True,
        ),
    )


def _registry_with_chat(provider: str, model: str, *, vision: bool = False) -> ModelRegistry:
    reg = ModelRegistry()
    spec = _vision_spec(provider, model) if vision else _text_spec(provider, model)
    reg._specs[(provider, model)] = spec  # noqa: SLF001
    reg._task_bindings = {  # noqa: SLF001
        "chat": {"provider": provider, "model": model},
    }
    return reg


def _resolver(catalog: ModelRegistry) -> TaskResolver:
    registry = MagicMock()
    registry.has_provider.return_value = True
    return TaskResolver(registry, catalog)


def _minimal_catalog(provider: str = "mock", model: str = "gpt-4") -> ModelRegistry:
    catalog = ModelRegistry()
    catalog.load_from_config(
        {
            "version": 2,
            "providers": [
                {
                    "name": provider,
                    "type": "openai",
                    "enabled": True,
                    "models": [
                        {
                            "name": model,
                            "kind": "chat",
                            "capabilities": {
                                "input": ["text"],
                                "output": ["text"],
                                "tool_call": True,
                            },
                            "context_window": 128000,
                        }
                    ],
                }
            ],
            "routing": {"tasks": {"chat": {"provider": provider, "model": model}}},
        }
    )
    return catalog


def _mock_resolver(catalog: ModelRegistry | None = None) -> TaskResolver:
    reg = ProviderRegistry()
    mock_prov = MagicMock()
    mock_prov.name = "mock"
    reg.register("mock", mock_prov)
    return TaskResolver(reg, catalog or _minimal_catalog())


def _kind_spec(
    provider: str,
    model: str,
    *,
    kind: str,
) -> ModelSpec:
    return ModelSpec(name=model, provider=provider, kind=kind)  # type: ignore[arg-type]


def _registry_with_task(task: str, provider: str, model: str, *, kind: str) -> ModelRegistry:
    reg = ModelRegistry()
    reg._specs[(provider, model)] = _kind_spec(provider, model, kind=kind)  # noqa: SLF001
    reg._task_bindings = {task: {"provider": provider, "model": model}}  # noqa: SLF001
    return reg


# ---------------------------------------------------------------------------
# Chat task binding (merged from test_llm.py)
# ---------------------------------------------------------------------------


def test_resolve_chat_task_binding() -> None:
    resolved = _mock_resolver().resolve(ModelTask.CHAT)
    assert resolved.provider == "mock"
    assert resolved.model == "gpt-4"
    assert resolved.task == ModelTask.CHAT


def test_explicit_user_model() -> None:
    resolved = _mock_resolver().resolve(
        ModelTask.CHAT,
        user_provider="mock",
        user_model="gpt-4",
    )
    assert resolved.reason == "user_explicit"


def test_unknown_model_raises() -> None:
    with pytest.raises(ModelNotFoundError):
        _mock_resolver().resolve(
            ModelTask.CHAT,
            user_provider="mock",
            user_model="missing",
        )


# ---------------------------------------------------------------------------
# Non-chat domain tasks (image_gen / tts / asr)
# ---------------------------------------------------------------------------


def test_image_gen_task_requires_image_gen_kind() -> None:
    catalog = _registry_with_task("image_gen", "openai", "gpt-4", kind="chat")
    resolver = _resolver(catalog)
    with pytest.raises(LLMServiceError, match="image_gen"):
        resolver.resolve(ModelTask.IMAGE_GEN)


def test_image_gen_task_succeeds_with_correct_kind() -> None:
    catalog = _registry_with_task("image_gen", "dashscope", "wanx", kind="image_gen")
    resolver = _resolver(catalog)
    resolved = resolver.resolve(ModelTask.IMAGE_GEN)
    assert resolved.task == ModelTask.IMAGE_GEN
    assert resolved.provider == "dashscope"
    assert resolved.model == "wanx"


def test_tts_task_requires_tts_kind() -> None:
    catalog = _registry_with_task("tts", "openai", "gpt-4", kind="chat")
    resolver = _resolver(catalog)
    with pytest.raises(LLMServiceError, match="tts"):
        resolver.resolve(ModelTask.TTS)


def test_tts_task_succeeds_with_correct_kind() -> None:
    catalog = _registry_with_task("tts", "openai", "tts-1", kind="tts")
    resolver = _resolver(catalog)
    resolved = resolver.resolve(ModelTask.TTS)
    assert resolved.task == ModelTask.TTS
    assert resolved.model == "tts-1"


def test_asr_task_requires_asr_kind() -> None:
    catalog = _registry_with_task("asr", "openai", "gpt-4", kind="chat")
    resolver = _resolver(catalog)
    with pytest.raises(LLMServiceError, match="asr"):
        resolver.resolve(ModelTask.ASR)


def test_asr_task_succeeds_with_correct_kind() -> None:
    catalog = _registry_with_task("asr", "openai", "whisper-1", kind="asr")
    resolver = _resolver(catalog)
    resolved = resolver.resolve(ModelTask.ASR)
    assert resolved.task == ModelTask.ASR
    assert resolved.model == "whisper-1"


# ---------------------------------------------------------------------------
# Vision / image attachment routing
# ---------------------------------------------------------------------------


def test_user_text_only_model_with_images_does_not_raise() -> None:
    catalog = _registry_with_chat("deepseek", "deepseek-v4-flash", vision=False)
    resolver = _resolver(catalog)
    messages = [
        ChatMessage(
            role=MessageRole.USER,
            content=[
                {"type": "text", "text": "describe this"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        )
    ]
    resolved = resolver.resolve(
        ModelTask.CHAT,
        messages=messages,
        user_provider="deepseek",
        user_model="deepseek-v4-flash",
    )
    assert resolved.provider == "deepseek"
    assert resolved.model == "deepseek-v4-flash"
    assert resolved.reason == "user_explicit_text_only"


def test_strip_image_blocks_from_messages() -> None:
    messages = [
        ChatMessage(
            role=MessageRole.USER,
            content=[
                {"type": "text", "text": "hello"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        )
    ]
    stripped = strip_image_blocks_from_messages(messages)
    assert stripped[0].content == "hello"
    assert not messages_contain_image(stripped)


def test_vision_task_missing_falls_back_to_chat_without_error() -> None:
    catalog = _registry_with_chat("deepseek", "deepseek-v4-flash", vision=False)
    resolver = _resolver(catalog)
    messages = [
        ChatMessage(
            role=MessageRole.USER,
            content=[
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        )
    ]
    resolved = resolver.resolve(ModelTask.CHAT, messages=messages)
    assert resolved.task == ModelTask.CHAT
    assert resolved.model == "deepseek-v4-flash"
    assert resolved.reason == "vision_unavailable_use_tools"


def test_vision_task_upgrade_when_configured() -> None:
    catalog = ModelRegistry()
    catalog._specs[("deepseek", "flash")] = _text_spec("deepseek", "flash")  # noqa: SLF001
    catalog._specs[("openai", "gpt-4o")] = _vision_spec("openai", "gpt-4o")  # noqa: SLF001
    catalog._task_bindings = {  # noqa: SLF001
        "chat": {"provider": "deepseek", "model": "flash"},
        "vision": {"provider": "openai", "model": "gpt-4o"},
    }
    resolver = _resolver(catalog)
    messages = [
        ChatMessage(
            role=MessageRole.USER,
            content=[
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            ],
        )
    ]
    resolved = resolver.resolve(ModelTask.CHAT, messages=messages)
    assert resolved.task == ModelTask.VISION
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-4o"


def test_vision_task_binding_without_image_capability_falls_back_to_chat() -> None:
    catalog = ModelRegistry()
    catalog._specs[("openai", "text-only")] = _text_spec("openai", "text-only")  # noqa: SLF001
    catalog._task_bindings = {  # noqa: SLF001
        "chat": {"provider": "openai", "model": "text-only"},
        "vision": {"provider": "openai", "model": "text-only"},
    }
    resolver = _resolver(catalog)
    resolved = resolver.resolve(
        ModelTask.CHAT,
        messages=[
            ChatMessage(
                role=MessageRole.USER,
                content=[
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,x"}},
                ],
            )
        ],
    )
    assert resolved.task == ModelTask.CHAT
    assert resolved.model == "text-only"
    assert resolved.reason == "vision_unavailable_use_tools"


def test_disabled_vision_model_falls_back_to_chat() -> None:
    catalog = ModelRegistry()
    catalog._specs[("deepseek", "flash")] = _text_spec("deepseek", "flash")  # noqa: SLF001
    vision = _vision_spec("dashscope", "qwen-vl-max")
    catalog._specs[("dashscope", "qwen-vl-max")] = ModelSpec(  # noqa: SLF001
        name=vision.name,
        provider=vision.provider,
        capabilities=vision.capabilities,
        enabled=False,
    )
    catalog._task_bindings = {  # noqa: SLF001
        "chat": {"provider": "deepseek", "model": "flash"},
        "vision": {"provider": "dashscope", "model": "qwen-vl-max"},
    }
    resolver = _resolver(catalog)
    resolved = resolver.resolve(
        ModelTask.CHAT,
        messages=[
            ChatMessage(
                role=MessageRole.USER,
                content=[
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
            )
        ],
    )
    assert resolved.task == ModelTask.CHAT
    assert resolved.provider == "deepseek"
    assert resolved.model == "flash"
    assert resolved.reason == "vision_unavailable_use_tools"


def test_explicit_vision_task_still_requires_image_capability() -> None:
    catalog = ModelRegistry()
    catalog._specs[("openai", "text-only")] = _text_spec("openai", "text-only")  # noqa: SLF001
    catalog._task_bindings = {  # noqa: SLF001
        "vision": {"provider": "openai", "model": "text-only"},
    }
    resolver = _resolver(catalog)
    with pytest.raises(LLMServiceError, match="requires a model with image input"):
        resolver.resolve(ModelTask.VISION)
