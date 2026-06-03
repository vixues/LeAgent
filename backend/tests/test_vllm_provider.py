"""Offline tests for the vLLM LLM provider.

These never hit the network: we exercise the pure-Python surface
(``_build_request_body``, constructor defaults, structured_outputs injection,
registry wiring).
"""

from __future__ import annotations

import json
import logging

import pytest

from leagent.exceptions.llm import LLMServiceError
from leagent.llm.base import ChatMessage, StreamChunk, ToolCall, ToolDefinition
from leagent.llm.providers.custom import CustomOpenAIProvider
from leagent.llm.providers.openai import OpenAIProvider
from leagent.llm.providers.vllm import VLLMProvider


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestVLLMProviderDefaults:
    def test_default_attributes(self) -> None:
        p = VLLMProvider()
        assert p.name == "vllm"
        assert p.supports_streaming is True
        assert p.supports_tools is True
        assert p.supports_embeddings is True
        assert p.supports_structured_output is True
        assert p.base_url == "http://localhost:8000/v1"
        assert p.default_model == ""
        assert p.api_key == "not-needed"
        assert isinstance(p, CustomOpenAIProvider)

    def test_accepts_overrides(self) -> None:
        p = VLLMProvider(
            api_key="custom-key",
            base_url="http://gpu-server:8080/v1",
            default_model="meta-llama/Meta-Llama-3-8B-Instruct",
            timeout=60.0,
        )
        assert p.base_url == "http://gpu-server:8080/v1"
        assert p.default_model == "meta-llama/Meta-Llama-3-8B-Instruct"
        assert p.api_key == "custom-key"
        assert p.timeout == 60.0


# ---------------------------------------------------------------------------
# Stream parsing (inherited from CustomOpenAIProvider)
# ---------------------------------------------------------------------------

class TestVLLMStreamParsing:
    def test_stream_chunk_normalizes_dict_tool_arguments(self) -> None:
        p = VLLMProvider(default_model="llama3")
        chunk = p._parse_stream_chunk(
            {
                "model": "llama3",
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "echo",
                                "arguments": {"text": "ping"},
                            },
                        }],
                    },
                    "finish_reason": None,
                }],
            },
            "llama3",
        )
        args = chunk.tool_calls_delta[0]["function"]["arguments"]
        assert isinstance(args, str)
        assert json.loads(args) == {"text": "ping"}

    @pytest.mark.asyncio
    async def test_content_json_tool_call_via_custom_buffer(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = VLLMProvider(default_model="llama3")
        payload = json.dumps(
            {"name": "echo", "arguments": {"text": "hi"}},
            ensure_ascii=False,
        )

        async def fake_openai_stream(*_args, **_kwargs):
            yield StreamChunk(content=payload, finish_reason="stop", model="llama3")

        monkeypatch.setattr(OpenAIProvider, "stream", fake_openai_stream)

        chunks = [
            chunk
            async for chunk in p.stream(
                messages=[ChatMessage.user("say hi")],
                model="llama3",
            )
        ]
        assert [c for c in chunks if c.tool_calls_delta]
        assert chunks[0].tool_calls_delta[0]["function"]["name"] == "echo"

    def test_call_content_history_rewritten_for_vllm(self) -> None:
        p = VLLMProvider(default_model="llama3")
        body = p._build_request_body(
            messages=[
                ChatMessage.user("run"),
                ChatMessage.assistant(
                    tool_calls=[
                        ToolCall(
                            id="call_content_0",
                            name="echo",
                            arguments=json.dumps({"text": "x"}),
                        )
                    ],
                ),
                ChatMessage.tool('{"ok": true}', "call_content_0"),
            ],
            model="llama3",
            temperature=0.1,
            max_tokens=512,
            tools=None,
            tool_choice=None,
            stop=None,
        )
        assert "tool_calls" not in body["messages"][1]
        assert body["messages"][1].get("content") in (None, "")
        assert body["messages"][2]["role"] == "user"


class TestVLLMErrorHandling:
    def test_handle_error_logs_tool_choice_hint(self, caplog: pytest.LogCaptureFixture) -> None:
        p = VLLMProvider(default_model="llama3", enable_auto_tool_choice=False)
        with caplog.at_level(logging.ERROR):
            with pytest.raises(LLMServiceError, match="tool_choice"):
                p._handle_error(
                    400,
                    {"error": {"message": "tool_choice auto is not supported"}},
                    "llama3",
                )
        assert "vllm_tool_choice_error" in caplog.text


class TestVLLMRequestOptions:
    def test_split_vllm_request_options(self) -> None:
        merged, structured, enable_auto = VLLMProvider._split_vllm_request_options(
            {
                "structured_outputs": {"choice": ["a"]},
                "enable_auto_tool_choice": True,
                "extra": 1,
            },
            default_enable_auto_tool_choice=False,
        )
        assert merged == {"extra": 1}
        assert structured == {"choice": ["a"]}
        assert enable_auto is True


# ---------------------------------------------------------------------------
# Request body construction
# ---------------------------------------------------------------------------

class TestVLLMBuildRequestBody:
    def test_basic_body_inherits_openai(self) -> None:
        p = VLLMProvider(default_model="llama3")
        msgs = [ChatMessage.user("hello")]
        body = p._build_request_body(msgs, "llama3", 0.5, 100, None, None, None)
        assert body["model"] == "llama3"
        assert body["temperature"] == 0.5
        assert body["max_tokens"] == 100
        assert "structured_outputs" not in body

    def test_structured_outputs_choice(self) -> None:
        p = VLLMProvider(default_model="llama3")
        msgs = [ChatMessage.user("Classify: vLLM is great!")]
        body = p._build_request_body(
            msgs, "llama3", 0.5, 100, None, None, None,
            structured_outputs={"choice": ["positive", "negative"]},
        )
        assert body["structured_outputs"] == {"choice": ["positive", "negative"]}

    def test_structured_outputs_json_schema(self) -> None:
        p = VLLMProvider(default_model="llama3")
        msgs = [ChatMessage.user("Extract name and age")]
        schema = {
            "json": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "age": {"type": "integer"},
                },
                "required": ["name", "age"],
            }
        }
        body = p._build_request_body(
            msgs, "llama3", 0.5, 100, None, None, None,
            structured_outputs=schema,
        )
        assert body["structured_outputs"] == schema

    def test_structured_outputs_regex(self) -> None:
        p = VLLMProvider(default_model="llama3")
        msgs = [ChatMessage.user("Generate email")]
        body = p._build_request_body(
            msgs, "llama3", 0.5, 100, None, None, None,
            structured_outputs={"regex": r"[a-zA-Z]+@[a-zA-Z]+\.[a-zA-Z]+"},
        )
        assert "regex" in body["structured_outputs"]

    def test_tools_with_required_tool_choice(self) -> None:
        p = VLLMProvider(default_model="llama3")
        tools = [ToolDefinition(name="echo", description="Echo", parameters={"type": "object"})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "llama3", 0.5, 100, tools, "required", None)
        assert body["tool_choice"] == "required"
        assert body["tools"][0]["function"]["name"] == "echo"

    def test_tools_omit_auto_tool_choice_by_default(self) -> None:
        p = VLLMProvider(default_model="llama3")
        tools = [ToolDefinition(name="echo", description="Echo", parameters={"type": "object"})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "llama3", 0.5, 100, tools, "auto", None)
        assert "tool_choice" not in body
        assert body["tools"][0]["function"]["name"] == "echo"

    def test_tools_keep_auto_when_enabled(self) -> None:
        p = VLLMProvider(default_model="llama3", enable_auto_tool_choice=True)
        tools = [ToolDefinition(name="echo", description="Echo", parameters={"type": "object"})]
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(msgs, "llama3", 0.5, 100, tools, "auto", None)
        assert body["tool_choice"] == "auto"

    def test_structured_outputs_not_duplicated_in_kwargs(self) -> None:
        """structured_outputs is popped from kwargs, not passed through."""
        p = VLLMProvider(default_model="llama3")
        msgs = [ChatMessage.user("hi")]
        body = p._build_request_body(
            msgs, "llama3", 0.5, 100, None, None, None,
            structured_outputs={"choice": ["a", "b"]},
            extra_param="value",
        )
        assert body["structured_outputs"] == {"choice": ["a", "b"]}
        assert body["extra_param"] == "value"


# ---------------------------------------------------------------------------
# Model detection
# ---------------------------------------------------------------------------

class TestVLLMModelDetection:
    def test_get_default_model_fallback(self) -> None:
        p = VLLMProvider(default_model="")
        assert p._get_default_model() == "default"

    def test_get_default_model_set(self) -> None:
        p = VLLMProvider(default_model="my-model")
        assert p._get_default_model() == "my-model"

    @pytest.mark.asyncio
    async def test_resolve_request_model_detects_when_blank(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = VLLMProvider(default_model="")

        async def fake_detect_model() -> str:
            return "served-local-model"

        monkeypatch.setattr(p, "detect_model", fake_detect_model)
        assert await p._resolve_model_for_request("default") == "served-local-model"

    @pytest.mark.asyncio
    async def test_resolve_request_model_keeps_explicit_model(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = VLLMProvider(default_model="")

        async def fail_detect_model() -> str:
            raise AssertionError("should not detect when caller supplied a model")

        monkeypatch.setattr(p, "detect_model", fail_detect_model)
        assert await p._resolve_model_for_request("explicit-model") == "explicit-model"

    @pytest.mark.asyncio
    async def test_detect_model_returns_cached_without_network(self) -> None:
        p = VLLMProvider(default_model="")
        p._detected_model = "cached-model"
        result = await p.detect_model()
        assert result == "cached-model"


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

class TestVLLMRegistryWiring:
    def test_providers_package_exports_vllm(self) -> None:
        from leagent.llm.providers import VLLMProvider as Exported
        assert Exported is VLLMProvider

    def test_provider_config_constructs_vllm(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        pc = ProviderConfig(
            name="vllm-test",
            type="vllm",
            enabled=True,
            api_key="",
            base_url="http://gpu:8000/v1",
            models=[{"name": "llama3-70b", "tier": "tier1"}],
            timeout=120,
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, VLLMProvider)
        assert provider.base_url == "http://gpu:8000/v1"
        assert provider.default_model == "llama3-70b"
        assert provider.api_key == "not-needed"

    def test_provider_config_constructs_remote_vllm_with_api_key(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        pc = ProviderConfig(
            name="deepseek-vllm",
            type="vllm",
            enabled=True,
            api_key="remote-key",
            base_url="http://192.168.232.22:8001/v1",
            models=[
                {
                    "name": "deepseek",
                    "tier": "tier1",
                    "context_window": 16384,
                    "supports_tools": False,
                }
            ],
            timeout=120,
            metadata={"enable_auto_tool_choice": False},
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, VLLMProvider)
        assert provider.base_url == "http://192.168.232.22:8001/v1"
        assert provider.default_model == "deepseek"
        assert provider.api_key == "remote-key"
        assert provider.enable_auto_tool_choice is False

    def test_provider_preset_exists(self) -> None:
        from leagent.llm.provider_config import PROVIDER_PRESETS
        assert "vllm" in PROVIDER_PRESETS
        assert PROVIDER_PRESETS["vllm"]["default_base_url"] == "http://localhost:8000/v1"
        assert PROVIDER_PRESETS["vllm"]["requires_api_key"] is True

    def test_vllm_env_registers_tiers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from leagent.config.settings import get_settings
        from leagent.llm.registry import create_default_registry

        monkeypatch.setenv("LLM_VLLM_ENDPOINT", "http://localhost:9000/v1")
        monkeypatch.setenv("LLM_VLLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
        monkeypatch.setenv("LLM_VLLM_ENABLE_AUTO_TOOL_CHOICE", "true")
        get_settings.cache_clear()
        try:
            registry = create_default_registry()
        finally:
            get_settings.cache_clear()

        assert isinstance(registry.get_provider("vllm"), VLLMProvider)
        assert registry.get_provider("tier1") is registry.get_provider("vllm")
        assert registry.get_provider_info("tier1").metadata["vendor"] == "vllm"
        assert registry.get_provider("vllm").enable_auto_tool_choice is True


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestVLLMResponseParsing:
    def test_parse_tool_calls(self) -> None:
        p = VLLMProvider(default_model="llama3")
        data = {
            "model": "llama3",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_abc",
                        "type": "function",
                        "function": {"name": "echo", "arguments": '{"text":"hi"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        resp = p._parse_response(data)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "echo"
        assert json.loads(resp.tool_calls[0].arguments) == {"text": "hi"}

    def test_parse_reasoning_content(self) -> None:
        p = VLLMProvider(default_model="llama3")
        data = {
            "model": "llama3",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "answer",
                    "reasoning_content": "internal trace",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        resp = p._parse_response(data)
        assert resp.reasoning_content == "internal trace"
        assert resp.content == "answer"

    def test_parse_think_tags(self) -> None:
        p = VLLMProvider(default_model="llama3", parse_think_tags=True)
        data = {
            "model": "llama3",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "<think>step by step</think>\nFinal",
                },
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        resp = p._parse_response(data)
        assert resp.reasoning_content == "step by step"
        assert resp.content == "Final"


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestVLLMHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_uses_resolved_model(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = VLLMProvider(default_model="")
        seen: dict[str, str] = {}

        async def fake_resolve_test_model(**_kwargs: object) -> str:
            return "detected-model"

        async def fake_complete(*, model, **kwargs):  # type: ignore[no-untyped-def]
            seen["model"] = model
            from leagent.llm.base import LLMResponse
            return LLMResponse(content="pong", model=model)

        monkeypatch.setattr(p, "resolve_test_model", fake_resolve_test_model)
        monkeypatch.setattr(p, "complete", fake_complete)

        assert await p.health_check() is True
        assert seen["model"] == "detected-model"

    @pytest.mark.asyncio
    async def test_health_check_returns_false_on_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = VLLMProvider(default_model="")

        async def fail_resolve(**_kwargs: object) -> str:
            raise RuntimeError("no model")

        monkeypatch.setattr(p, "resolve_test_model", fail_resolve)
        assert await p.health_check() is False


# ---------------------------------------------------------------------------
# Stream reasoning
# ---------------------------------------------------------------------------

class TestVLLMStreamReasoning:
    def test_thinking_delta_mapped_to_reasoning_content(self) -> None:
        p = VLLMProvider(default_model="llama3")
        chunk = p._parse_stream_chunk(
            {
                "model": "llama3",
                "choices": [{"delta": {"thinking": "step 1"}, "finish_reason": None}],
            },
            "llama3",
        )
        assert chunk.raw_delta == {"reasoning_content": "step 1"}

    def test_reasoning_content_delta(self) -> None:
        p = VLLMProvider(default_model="llama3")
        chunk = p._parse_stream_chunk(
            {
                "model": "llama3",
                "choices": [{"delta": {"reasoning_content": "trace"}, "finish_reason": None}],
            },
            "llama3",
        )
        assert chunk.raw_delta == {"reasoning_content": "trace"}
