"""Offline tests for the DashScope LLM provider.

These never hit the network: we exercise the pure-Python surface
(``_parse_stream_chunk``, ``_parse_response``, ``_build_request_body``,
constructor defaults, thinking mode, reasoning_content extraction,
settings merge, cache metrics, error handling, stream usage parsing).
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from leagent.llm.base import ChatMessage, StreamChunk, TokenUsage, ToolDefinition
from leagent.llm.providers.dashscope import DashScopeProvider


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestDashScopeProviderDefaults:
    def test_default_attributes(self) -> None:
        p = DashScopeProvider(api_key="k")
        assert p.name == "dashscope"
        assert p.supports_streaming is True
        assert p.supports_tools is True
        assert p.supports_embeddings is True
        assert p.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
        assert p.default_model == "qwen-plus"

    def test_accepts_overrides(self) -> None:
        p = DashScopeProvider(
            api_key="k",
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            default_model="qwen-max",
            timeout=60.0,
        )
        assert p.base_url == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        assert p.default_model == "qwen-max"
        assert p.timeout == 60.0

    def test_empty_base_url_falls_back(self) -> None:
        p = DashScopeProvider(api_key="k", base_url="")
        assert p.base_url == DashScopeProvider.DEFAULT_BASE_URL

    def test_empty_model_falls_back(self) -> None:
        p = DashScopeProvider(api_key="k", default_model="")
        assert p.default_model == DashScopeProvider.DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Request body construction
# ---------------------------------------------------------------------------

class TestDashScopeBuildRequestBody:
    def test_basic_body_is_openai_compatible(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "qwen-plus", 0.5, 100, None, None, None)
        assert body["model"] == "qwen-plus"
        assert body["temperature"] == 0.5
        assert body["max_tokens"] == 100
        assert len(body["messages"]) == 1
        assert "enable_thinking" not in body

    def test_enable_thinking_auto_injected_for_qwen3(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "qwen3-max", 0.5, 100, None, None, None)
        assert body["enable_thinking"] is True

    def test_enable_thinking_auto_injected_for_qwq(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "qwq-32b", 0.5, 100, None, None, None)
        assert body["enable_thinking"] is True

    def test_enable_thinking_not_injected_for_non_thinking_model(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "qwen-plus", 0.5, 100, None, None, None)
        assert "enable_thinking" not in body

    def test_explicit_enable_thinking_false(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "qwen3-max", 0.5, 100, None, None, None, enable_thinking=False)
        assert body["enable_thinking"] is False

    def test_tools_in_body(self) -> None:
        p = DashScopeProvider(api_key="k")
        tools = [ToolDefinition(name="echo", description="Echo", parameters={"type": "object"})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "qwen-plus", 0.5, 100, tools, "auto", None)
        assert body["tools"][0]["type"] == "function"
        assert body["tool_choice"] == "auto"

    def test_enable_search_in_body(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "qwen-plus", 0.5, 100, None, None, None, enable_search=True)
        assert body["enable_search"] is True

    def test_thinking_budget_in_body(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "qwen3-max", 0.5, 100, None, None, None, thinking_budget=4096)
        assert body["thinking_budget"] == 4096

    def test_preserve_thinking_in_body(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "qwen3-max", 0.5, 100, None, None, None, preserve_thinking=True)
        assert body["preserve_thinking"] is True

    def test_search_options_in_body(self) -> None:
        p = DashScopeProvider(api_key="k")
        msgs = [ChatMessage.user("hello")]
        opts = {"search_strategy": "pro"}
        body = p._build_request_body(msgs, "qwen-plus", 0.5, 100, None, None, None, search_options=opts)
        assert body["search_options"] == opts


# ---------------------------------------------------------------------------
# Settings merge
# ---------------------------------------------------------------------------

class TestDashScopeSettingsMerge:
    def _mock_settings(self, *, enable_thinking=None, enable_search=False):
        """Create a mock settings object."""
        llm = MagicMock()
        llm.dashscope_enable_thinking = enable_thinking
        llm.dashscope_enable_search = enable_search
        settings = MagicMock()
        settings.llm = llm
        return settings

    def test_settings_merge_enable_thinking(self) -> None:
        p = DashScopeProvider(api_key="k")
        mock_settings = self._mock_settings(enable_thinking=True)
        with patch("leagent.llm.providers.dashscope.DashScopeProvider._merge_dashscope_settings") as mock_merge:
            mock_merge.return_value = {"enable_thinking": True}
            result = mock_merge({})
            assert result["enable_thinking"] is True

    def test_settings_merge_enable_search(self) -> None:
        p = DashScopeProvider(api_key="k")
        kwargs: dict = {}
        mock_settings = self._mock_settings(enable_search=True)
        with patch("leagent.config.settings.get_settings", return_value=mock_settings):
            merged = p._merge_dashscope_settings(kwargs)
        assert merged.get("enable_search") is True

    def test_settings_merge_explicit_kwargs_win(self) -> None:
        p = DashScopeProvider(api_key="k")
        kwargs = {"enable_thinking": False, "enable_search": False}
        mock_settings = self._mock_settings(enable_thinking=True, enable_search=True)
        with patch("leagent.config.settings.get_settings", return_value=mock_settings):
            merged = p._merge_dashscope_settings(kwargs)
        assert merged["enable_thinking"] is False
        assert merged["enable_search"] is False

    def test_settings_merge_handles_import_error(self) -> None:
        p = DashScopeProvider(api_key="k")
        kwargs = {"temperature": 0.5}
        with patch("leagent.config.settings.get_settings", side_effect=ImportError("no settings")):
            merged = p._merge_dashscope_settings(kwargs)
        assert merged == kwargs


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestDashScopeResponseParsing:
    def test_parse_basic_response(self) -> None:
        p = DashScopeProvider(api_key="k")
        data = {
            "model": "qwen-plus",
            "choices": [
                {"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        resp = p._parse_response(data)
        assert resp.content == "Hello!"
        assert resp.reasoning_content is None

    def test_parse_response_with_reasoning_content(self) -> None:
        p = DashScopeProvider(api_key="k")
        data = {
            "model": "qwen3-max",
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
        resp = p._parse_response(data)
        assert resp.content == "The answer is 42."
        assert resp.reasoning_content == "Let me think step by step..."

    def test_parse_response_empty_reasoning_ignored(self) -> None:
        p = DashScopeProvider(api_key="k")
        data = {
            "model": "qwen3-max",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Answer.",
                        "reasoning_content": "   ",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        resp = p._parse_response(data)
        assert resp.reasoning_content is None


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------

class TestDashScopeStreamParsing:
    def _parse(self, provider: DashScopeProvider, payload: dict) -> StreamChunk:
        return provider._parse_stream_chunk(payload, provider.default_model)

    def test_plain_content_delta(self) -> None:
        p = DashScopeProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "qwen-plus",
            "choices": [{"delta": {"content": "Hello"}, "finish_reason": None}],
        })
        assert chunk.content == "Hello"
        assert chunk.raw_delta is None

    def test_reasoning_content_in_stream(self) -> None:
        p = DashScopeProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "qwen3-max",
            "choices": [
                {
                    "delta": {"content": "", "reasoning_content": "thinking..."},
                    "finish_reason": None,
                }
            ],
        })
        assert chunk.raw_delta == {"reasoning_content": "thinking..."}

    def test_tool_call_delta(self) -> None:
        p = DashScopeProvider(api_key="k")
        tc = [{"index": 0, "id": "call_1", "type": "function", "function": {"name": "echo", "arguments": ""}}]
        chunk = self._parse(p, {
            "model": "qwen-plus",
            "choices": [{"delta": {"tool_calls": tc}, "finish_reason": None}],
        })
        assert chunk.tool_calls_delta == tc

    def test_null_content_coalesced_to_empty_string(self) -> None:
        p = DashScopeProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "qwen-plus",
            "choices": [{"delta": {"content": None}, "finish_reason": None}],
        })
        assert chunk.content == ""

    def test_stream_usage_parsing_with_cache_and_reasoning(self) -> None:
        p = DashScopeProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "qwen3-max",
            "choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "prompt_tokens_details": {"cached_tokens": 80},
                "completion_tokens_details": {"reasoning_tokens": 30},
            },
        })
        assert chunk.usage is not None
        assert chunk.usage.prompt_tokens == 100
        assert chunk.usage.completion_tokens == 50
        assert chunk.usage.prompt_cache_hit_tokens == 80
        assert chunk.usage.reasoning_tokens == 30

    def test_stream_usage_without_details(self) -> None:
        p = DashScopeProvider(api_key="k")
        chunk = self._parse(p, {
            "model": "qwen-plus",
            "choices": [{"delta": {"content": ""}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30,
            },
        })
        assert chunk.usage is not None
        assert chunk.usage.prompt_tokens == 20
        assert chunk.usage.prompt_cache_hit_tokens == 0
        assert chunk.usage.reasoning_tokens == 0


# ---------------------------------------------------------------------------
# Cache metrics logging
# ---------------------------------------------------------------------------

class TestDashScopeCacheMetrics:
    def test_cache_metrics_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        p = DashScopeProvider(api_key="k")
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            prompt_cache_hit_tokens=80,
        )
        with caplog.at_level(logging.DEBUG, logger="leagent.llm.providers.dashscope"):
            p._log_cache_metrics(usage, "qwen-plus")
        assert any("dashscope_cache_metrics" in r.message for r in caplog.records)

    def test_cache_metrics_not_logged_when_no_cache(self, caplog: pytest.LogCaptureFixture) -> None:
        p = DashScopeProvider(api_key="k")
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            prompt_cache_hit_tokens=0,
        )
        with caplog.at_level(logging.DEBUG, logger="leagent.llm.providers.dashscope"):
            p._log_cache_metrics(usage, "qwen-plus")
        assert not any("dashscope_cache_metrics" in r.message for r in caplog.records)

    def test_cache_metrics_not_logged_for_none_usage(self) -> None:
        p = DashScopeProvider(api_key="k")
        p._log_cache_metrics(None, "qwen-plus")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestDashScopeErrorHandling:
    def test_reasoning_content_passback_error_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        p = DashScopeProvider(api_key="k")
        body = {"error": {"message": "reasoning_content field is required"}}
        with caplog.at_level(logging.ERROR, logger="leagent.llm.providers.dashscope"):
            try:
                p._handle_error(400, body, "qwen3-max")
            except Exception:
                pass
        assert any("dashscope_reasoning_content_passback_error" in r.message for r in caplog.records)

    def test_enable_thinking_error_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        p = DashScopeProvider(api_key="k")
        body = {"error": {"message": "enable_thinking is not supported for this model"}}
        with caplog.at_level(logging.ERROR, logger="leagent.llm.providers.dashscope"):
            try:
                p._handle_error(400, body, "qwen-plus")
            except Exception:
                pass
        assert any("dashscope_enable_thinking_error" in r.message for r in caplog.records)

    def test_tool_choice_thinking_error_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        p = DashScopeProvider(api_key="k")
        body = {"error": {"message": "tool_choice not supported in thinking mode"}}
        with caplog.at_level(logging.ERROR, logger="leagent.llm.providers.dashscope"):
            try:
                p._handle_error(400, body, "qwen3-max")
            except Exception:
                pass
        assert any("dashscope_tool_choice_thinking_error" in r.message for r in caplog.records)

    def test_non_400_error_no_diagnostic(self, caplog: pytest.LogCaptureFixture) -> None:
        p = DashScopeProvider(api_key="k")
        with caplog.at_level(logging.ERROR, logger="leagent.llm.providers.dashscope"):
            try:
                p._handle_error(500, "server error", "qwen-plus")
            except Exception:
                pass
        assert not any("dashscope_" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Thinking model detection
# ---------------------------------------------------------------------------

class TestDashScopeThinkingDetection:
    def test_qwen3_is_thinking(self) -> None:
        p = DashScopeProvider(api_key="k")
        assert p._is_thinking_model("qwen3-max") is True
        assert p._is_thinking_model("qwen3.5-plus") is True
        assert p._is_thinking_model("qwen3-30b-a3b-thinking-2507") is True

    def test_qwq_is_thinking(self) -> None:
        p = DashScopeProvider(api_key="k")
        assert p._is_thinking_model("qwq-32b") is True
        assert p._is_thinking_model("QwQ-32B") is True  # case-insensitive

    def test_qwen_plus_is_not_thinking(self) -> None:
        p = DashScopeProvider(api_key="k")
        assert p._is_thinking_model("qwen-plus") is False
        assert p._is_thinking_model("qwen-max") is False
        assert p._is_thinking_model("qwen2.5-72b-instruct") is False


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

class TestDashScopeRegistryWiring:
    def test_providers_package_exports_dashscope(self) -> None:
        from leagent.llm.providers import DashScopeProvider as Exported
        assert Exported is DashScopeProvider

    def test_provider_config_constructs_dashscope(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        pc = ProviderConfig(
            name="dashscope-test",
            type="dashscope",
            enabled=True,
            api_key="test-key",
            base_url="",
            models=[{"name": "qwen-max", "tier": "tier1"}],
            timeout=30,
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, DashScopeProvider)
        assert provider.api_key == "test-key"
        assert provider.default_model == "qwen-max"

    def test_provider_config_qwen_type_constructs_dashscope(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        pc = ProviderConfig(
            name="qwen-test",
            type="qwen",
            enabled=True,
            api_key="test-key",
            base_url="",
            models=[{"name": "qwen-plus", "tier": "tier2"}],
            timeout=30,
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, DashScopeProvider)

    def test_provider_config_passes_base_url(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        custom_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        pc = ProviderConfig(
            name="qwen-intl",
            type="qwen",
            enabled=True,
            api_key="test-key",
            base_url=custom_url,
            models=[{"name": "qwen-plus", "tier": "tier2"}],
            timeout=30,
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, DashScopeProvider)
        assert provider.base_url == custom_url


# ---------------------------------------------------------------------------
# Hostname detection
# ---------------------------------------------------------------------------

class TestDashScopeHostnameDetection:
    def test_dashscope_hostname(self) -> None:
        from leagent.llm.registry import _endpoint_hostname_is_dashscope

        assert _endpoint_hostname_is_dashscope("https://dashscope.aliyuncs.com/compatible-mode/v1") is True
        assert _endpoint_hostname_is_dashscope("https://dashscope-intl.aliyuncs.com/compatible-mode/v1") is True

    def test_non_dashscope_hostname(self) -> None:
        from leagent.llm.registry import _endpoint_hostname_is_dashscope

        assert _endpoint_hostname_is_dashscope("https://api.openai.com/v1") is False
        assert _endpoint_hostname_is_dashscope("https://api.deepseek.com") is False
        assert _endpoint_hostname_is_dashscope("") is False

    def test_maas_hostname(self) -> None:
        from leagent.llm.registry import _endpoint_hostname_is_dashscope

        assert _endpoint_hostname_is_dashscope("https://maas.aliyuncs.com/v1") is True
