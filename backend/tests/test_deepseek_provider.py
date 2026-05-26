"""Offline tests for the DeepSeek LLM provider.

These never hit the network: we exercise the pure-Python surface
(``_parse_stream_chunk``, ``_parse_response``, ``_build_request_body``,
constructor defaults, registry wiring, user_id, thinking defaults).
"""

from __future__ import annotations

import contextvars
from unittest.mock import MagicMock

import pytest

from leagent.llm.base import ChatMessage, LLMResponse, MessageRole, StreamChunk, TokenUsage
from leagent.llm.providers.deepseek import (
    DeepSeekProvider,
    _sanitize_user_id,
    set_deepseek_user_id,
    reset_deepseek_user_id,
    set_reasoning_effort_override,
    reset_reasoning_effort_override,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_settings(
    *,
    thinking_type: str | None = None,
    reasoning_effort: str | None = None,
) -> MagicMock:
    mock_llm = MagicMock()
    mock_llm.deepseek_thinking_type = thinking_type
    mock_llm.deepseek_reasoning_effort = reasoning_effort
    mock_settings = MagicMock()
    mock_settings.llm = mock_llm
    return mock_settings


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestDeepSeekProviderDefaults:
    def test_defaults_match_deepseek_v4_api(self) -> None:
        p = DeepSeekProvider(api_key="k")
        assert p.name == "deepseek"
        assert p.supports_streaming is True
        assert p.supports_tools is True
        assert p.supports_embeddings is False
        assert p.base_url.rstrip("/") == "https://api.deepseek.com"
        assert p.default_model == "deepseek-v4-flash"

    def test_accepts_overrides(self) -> None:
        p = DeepSeekProvider(
            api_key="k",
            base_url="https://proxy.example/v1",
            default_model="deepseek-v4-pro",
            timeout=7.5,
        )
        assert p.base_url.rstrip("/") == "https://proxy.example/v1"
        assert p.default_model == "deepseek-v4-pro"
        assert p.timeout == 7.5


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------

class TestDeepSeekStreamParsing:
    def _parse(self, provider: DeepSeekProvider, payload: dict) -> StreamChunk:
        return provider._parse_stream_chunk(payload, provider.default_model)

    def test_plain_content_delta(self) -> None:
        p = DeepSeekProvider(api_key="k")
        chunk = self._parse(
            p,
            {
                "model": "deepseek-v4-flash",
                "choices": [
                    {"delta": {"content": "Hello "}, "finish_reason": None},
                ],
            },
        )
        assert chunk.content == "Hello "
        assert chunk.tool_calls_delta == []
        assert chunk.finish_reason is None
        assert chunk.raw_delta is None
        assert chunk.model == "deepseek-v4-flash"

    def test_null_content_coalesced_to_empty_string(self) -> None:
        """DeepSeek sometimes streams ``content: null`` deltas before tool_calls."""
        p = DeepSeekProvider(api_key="k")
        chunk = self._parse(
            p,
            {
                "model": "deepseek-v4-flash",
                "choices": [
                    {"delta": {"content": None}, "finish_reason": None},
                ],
            },
        )
        assert chunk.content == ""

    def test_reasoning_content_surfaces_via_raw_delta(self) -> None:
        p = DeepSeekProvider(api_key="k", default_model="deepseek-v4-pro")
        chunk = self._parse(
            p,
            {
                "model": "deepseek-v4-pro",
                "choices": [
                    {
                        "delta": {
                            "content": "",
                            "reasoning_content": "step 1: think",
                        },
                        "finish_reason": None,
                    },
                ],
            },
        )
        assert chunk.content == ""
        assert chunk.raw_delta == {"reasoning_content": "step 1: think"}

    def test_tool_call_delta_forwarded(self) -> None:
        p = DeepSeekProvider(api_key="k")
        tc = [
            {
                "index": 0,
                "id": "call_1",
                "type": "function",
                "function": {"name": "echo", "arguments": "{\"x\":1}"},
            }
        ]
        chunk = self._parse(
            p,
            {
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "delta": {"content": None, "tool_calls": tc},
                        "finish_reason": None,
                    },
                ],
            },
        )
        assert chunk.tool_calls_delta == tc
        assert chunk.content == ""

    def test_finish_reason_propagates(self) -> None:
        p = DeepSeekProvider(api_key="k")
        chunk = self._parse(
            p,
            {
                "model": "deepseek-v4-flash",
                "choices": [
                    {"delta": {"content": ""}, "finish_reason": "stop"},
                ],
            },
        )
        assert chunk.finish_reason == "stop"

    def test_empty_choices_is_safe(self) -> None:
        p = DeepSeekProvider(api_key="k")
        chunk = self._parse(p, {"model": "deepseek-v4-flash", "choices": []})
        assert chunk.content == ""
        assert chunk.tool_calls_delta == []

    def test_usage_only_chunk(self) -> None:
        """SSE usage frame before ``[DONE]`` has empty choices + usage object."""
        p = DeepSeekProvider(api_key="k")
        chunk = self._parse(
            p,
            {
                "model": "deepseek-v4-flash",
                "choices": [],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                    "total_tokens": 30,
                },
            },
        )
        assert chunk.usage == TokenUsage(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

    def test_insufficient_system_resource_finish(self) -> None:
        p = DeepSeekProvider(api_key="k")
        chunk = self._parse(
            p,
            {
                "model": "deepseek-v4-flash",
                "choices": [
                    {"delta": {}, "finish_reason": "insufficient_system_resource"},
                ],
            },
        )
        assert chunk.finish_reason == "insufficient_system_resource"


# ---------------------------------------------------------------------------
# Non-streaming response parsing
# ---------------------------------------------------------------------------

class TestDeepSeekResponseParsing:
    def test_parse_response_extracts_reasoning_content(self) -> None:
        p = DeepSeekProvider(api_key="k")
        data = {
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "The answer is 42.",
                        "reasoning_content": "Let me think step by step...",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        }
        response = p._parse_response(data)
        assert response.content == "The answer is 42."
        assert response.reasoning_content == "Let me think step by step..."

    def test_parse_response_without_reasoning_content(self) -> None:
        p = DeepSeekProvider(api_key="k")
        data = {
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
        }
        response = p._parse_response(data)
        assert response.content == "Hello"
        assert response.reasoning_content is None

    def test_to_message_preserves_reasoning_content(self) -> None:
        response = LLMResponse(
            content="answer",
            reasoning_content="thinking...",
        )
        msg = response.to_message()
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "answer"
        assert msg.reasoning_content == "thinking..."

    def test_chat_message_assistant_factory_accepts_reasoning(self) -> None:
        msg = ChatMessage.assistant(
            content="answer",
            reasoning_content="my reasoning",
        )
        assert msg.reasoning_content == "my reasoning"
        fmt = msg.to_openai_format()
        assert fmt["reasoning_content"] == "my reasoning"


# ---------------------------------------------------------------------------
# Settings merge + thinking defaults
# ---------------------------------------------------------------------------

class TestDeepSeekSettingsMerge:
    def test_default_thinking_enabled_when_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When no explicit thinking_type is set, default to enabled."""
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(),
        )
        merged = p._merge_deepseek_settings({})
        assert merged["thinking"] == {"type": "enabled"}

    def test_merge_applies_thinking_from_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(thinking_type="enabled", reasoning_effort="max"),
        )
        merged = p._merge_deepseek_settings({"foo": 1})
        assert merged["foo"] == 1
        assert merged["thinking"] == {"type": "enabled"}
        assert merged["reasoning_effort"] == "max"

    def test_explicit_kwargs_win_over_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(thinking_type="enabled", reasoning_effort="max"),
        )
        merged = p._merge_deepseek_settings(
            {"thinking": {"type": "disabled"}, "reasoning_effort": "high"},
        )
        assert merged["thinking"] == {"type": "disabled"}
        assert merged["reasoning_effort"] == "high"

    def test_disabled_thinking_in_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(thinking_type="disabled"),
        )
        merged = p._merge_deepseek_settings({})
        assert merged["thinking"] == {"type": "disabled"}

    def test_reasoning_effort_override_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(reasoning_effort="high"),
        )
        token = set_reasoning_effort_override("max")
        try:
            merged = p._merge_deepseek_settings({})
            assert merged["reasoning_effort"] == "max"
        finally:
            reset_reasoning_effort_override(token)


# ---------------------------------------------------------------------------
# Request body construction
# ---------------------------------------------------------------------------

class TestDeepSeekBuildRequestBody:
    def test_deprecated_params_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(thinking_type="disabled"),
        )
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            msgs, "deepseek-v4-flash", 0.5, 100, None, None, None,
            frequency_penalty=0.5, presence_penalty=0.3,
        )
        assert "frequency_penalty" not in body
        assert "presence_penalty" not in body

    def test_thinking_mode_strips_sampling_params(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(thinking_type="enabled"),
        )
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            msgs, "deepseek-v4-flash", 0.5, 100, None, None, None,
            thinking={"type": "enabled"}, top_p=0.9,
        )
        assert "temperature" not in body
        assert "top_p" not in body
        assert "frequency_penalty" not in body
        assert "presence_penalty" not in body

    def test_user_id_injected_from_contextvar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(thinking_type="disabled"),
        )
        token = set_deepseek_user_id("ws-123:user-456")
        try:
            msgs = [ChatMessage.user("hi")]
            body = p._build_request_body(msgs, "deepseek-v4-flash", 0.5, 100, None, None, None)
            assert body["user_id"] == "ws-123_user-456"
        finally:
            reset_deepseek_user_id(token)

    def test_user_id_not_set_when_contextvar_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        p = DeepSeekProvider(api_key="k")
        monkeypatch.setattr(
            "leagent.config.settings.get_settings",
            lambda: _mock_settings(thinking_type="disabled"),
        )
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "deepseek-v4-flash", 0.5, 100, None, None, None)
        assert "user_id" not in body

    def test_user_id_reset_tolerates_different_context(self) -> None:
        token_holder: list[contextvars.Token[str | None]] = []
        context = contextvars.copy_context()
        context.run(lambda: token_holder.append(set_deepseek_user_id("user-123")))

        reset_deepseek_user_id(token_holder[0])


# ---------------------------------------------------------------------------
# user_id sanitization
# ---------------------------------------------------------------------------

class TestSanitizeUserId:
    def test_passthrough_valid_chars(self) -> None:
        assert _sanitize_user_id("abc-123_XYZ") == "abc-123_XYZ"

    def test_replaces_invalid_chars(self) -> None:
        assert _sanitize_user_id("user:abc@def") == "user_abc_def"

    def test_truncates_at_512(self) -> None:
        long_id = "a" * 600
        assert len(_sanitize_user_id(long_id)) == 512


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestDeepSeekErrorHandling:
    def test_400_reasoning_content_logs_diagnostic(self, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        import logging
        from leagent.exceptions.llm import LLMServiceError

        p = DeepSeekProvider(api_key="k")
        with caplog.at_level(logging.ERROR):
            with pytest.raises(LLMServiceError):
                p._handle_error(
                    400,
                    {"error": {"message": "Missing reasoning_content for tool call turn"}},
                    "deepseek-v4-pro",
                )
        assert any("reasoning_content" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

class TestRegistryWiring:
    def test_providers_package_exports_deepseek(self) -> None:
        from leagent.llm.providers import DeepSeekProvider as Exported

        assert Exported is DeepSeekProvider

    def test_provider_config_constructs_deepseek(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        pc = ProviderConfig(
            name="deepseek-test",
            type="deepseek",
            enabled=True,
            api_key="test-key",
            base_url="",
            models=[{"name": "deepseek-v4-flash", "tier": "tier2"}],
            timeout=30,
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)  # skip file IO in __init__
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, DeepSeekProvider)
        assert provider.api_key == "test-key"
        assert provider.default_model == "deepseek-v4-flash"


# ---------------------------------------------------------------------------
# FIM (offline shape check — no network)
# ---------------------------------------------------------------------------

class TestFIMCompleteMeta:
    def test_fim_method_exists(self) -> None:
        p = DeepSeekProvider(api_key="k")
        assert callable(getattr(p, "fim_complete", None))


# ---------------------------------------------------------------------------
# normalize_deepseek_base_url
# ---------------------------------------------------------------------------

class TestNormalizeDeepSeekBaseUrl:
    def test_strips_v1_suffix(self) -> None:
        from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

        assert normalize_deepseek_base_url("https://api.deepseek.com/v1") == "https://api.deepseek.com"

    def test_strips_v1_with_trailing_slash(self) -> None:
        from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

        assert normalize_deepseek_base_url("https://api.deepseek.com/v1/") == "https://api.deepseek.com"

    def test_noop_for_canonical_url(self) -> None:
        from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

        assert normalize_deepseek_base_url("https://api.deepseek.com") == "https://api.deepseek.com"

    def test_preserves_custom_proxy(self) -> None:
        from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

        assert normalize_deepseek_base_url("https://proxy.example/v1") == "https://proxy.example"

    def test_preserves_non_v1_path(self) -> None:
        from leagent.llm.providers.deepseek_utils import normalize_deepseek_base_url

        assert normalize_deepseek_base_url("https://api.deepseek.com/v2") == "https://api.deepseek.com/v2"


# ---------------------------------------------------------------------------
# Legacy config migration
# ---------------------------------------------------------------------------

class TestLegacyDeepSeekMigration:
    def test_renames_legacy_models(self) -> None:
        from leagent.llm.provider_config import ProviderConfigService

        config = {
            "default_provider": "deepseek",
            "default_model": "deepseek-chat",
            "providers": [
                {
                    "type": "deepseek",
                    "base_url": "https://api.deepseek.com",
                    "models": [
                        {"name": "deepseek-chat", "tier": "tier1"},
                        {"name": "deepseek-reasoner", "tier": "tier1"},
                    ],
                }
            ],
        }
        changed = ProviderConfigService._migrate_legacy_deepseek_config(config)
        assert changed is True
        names = [m["name"] for m in config["providers"][0]["models"]]
        assert names == ["deepseek-v4-flash", "deepseek-v4-pro"]
        assert config["default_model"] == "deepseek-v4-flash"

    def test_deduplicates_after_rename(self) -> None:
        from leagent.llm.provider_config import ProviderConfigService

        config = {
            "default_provider": "deepseek",
            "default_model": "deepseek-v4-flash",
            "providers": [
                {
                    "type": "deepseek",
                    "base_url": "https://api.deepseek.com",
                    "models": [
                        {"name": "deepseek-chat", "tier": "tier1"},
                        {"name": "deepseek-v4-flash", "tier": "tier2"},
                        {"name": "deepseek-v4-pro", "tier": "tier1"},
                    ],
                }
            ],
        }
        changed = ProviderConfigService._migrate_legacy_deepseek_config(config)
        assert changed is True
        names = [m["name"] for m in config["providers"][0]["models"]]
        assert names == ["deepseek-v4-flash", "deepseek-v4-pro"]

    def test_strips_v1_from_base_url(self) -> None:
        from leagent.llm.provider_config import ProviderConfigService

        config = {
            "default_provider": "deepseek",
            "default_model": "deepseek-v4-flash",
            "providers": [
                {
                    "type": "deepseek",
                    "base_url": "https://api.deepseek.com/v1",
                    "models": [{"name": "deepseek-v4-flash", "tier": "tier2"}],
                }
            ],
        }
        changed = ProviderConfigService._migrate_legacy_deepseek_config(config)
        assert changed is True
        assert config["providers"][0]["base_url"] == "https://api.deepseek.com"

    def test_no_change_for_current_config(self) -> None:
        from leagent.llm.provider_config import ProviderConfigService

        config = {
            "default_provider": "deepseek",
            "default_model": "deepseek-v4-flash",
            "providers": [
                {
                    "type": "deepseek",
                    "base_url": "https://api.deepseek.com",
                    "models": [
                        {"name": "deepseek-v4-flash", "tier": "tier2"},
                        {"name": "deepseek-v4-pro", "tier": "tier1"},
                    ],
                }
            ],
        }
        changed = ProviderConfigService._migrate_legacy_deepseek_config(config)
        assert changed is False
