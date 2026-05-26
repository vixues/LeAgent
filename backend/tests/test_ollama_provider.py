"""Offline tests for the Ollama LLM provider.

These never hit the network: we exercise the pure-Python surface
(``_parse_stream_chunk``, ``_parse_response``, ``_build_messages``,
constructor defaults, format/think parameters, thinking extraction, tool calls).
"""

from __future__ import annotations

import json

import pytest

from leagent.llm.base import ChatMessage, MessageRole, StreamChunk, TokenUsage, ToolCall, ToolDefinition
from leagent.llm.providers.ollama import OllamaProvider
from leagent.exceptions.llm import (
    LLMServiceError,
    ModelNotFoundError,
)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

class TestOllamaProviderDefaults:
    def test_default_attributes(self) -> None:
        p = OllamaProvider()
        assert p.name == "ollama"
        assert p.supports_streaming is True
        assert p.supports_tools is True
        assert p.supports_embeddings is True
        assert p.base_url == "http://localhost:11434"
        assert p.default_model == "llama3.2"
        assert p.timeout == 300.0

    def test_accepts_overrides(self) -> None:
        p = OllamaProvider(
            base_url="http://gpu-host:11434",
            default_model="qwen2.5:72b",
            timeout=600.0,
        )
        assert p.base_url == "http://gpu-host:11434"
        assert p.default_model == "qwen2.5:72b"
        assert p.timeout == 600.0

    def test_trailing_slash_stripped(self) -> None:
        p = OllamaProvider(base_url="http://localhost:11434/")
        assert p.base_url == "http://localhost:11434"


# ---------------------------------------------------------------------------
# Message building
# ---------------------------------------------------------------------------

class TestOllamaMessageBuilding:
    def test_basic_messages(self) -> None:
        p = OllamaProvider()
        msgs = [
            ChatMessage.system("You are helpful"),
            ChatMessage.user("Hello"),
            ChatMessage.assistant("Hi!"),
        ]
        result = p._build_messages(msgs)
        assert result[0] == {"role": "system", "content": "You are helpful"}
        assert result[1] == {"role": "user", "content": "Hello"}
        assert result[2] == {"role": "assistant", "content": "Hi!"}

    def test_tool_calls_in_message(self) -> None:
        p = OllamaProvider()
        tc = ToolCall(id="call_0", name="echo", arguments='{"text":"hi"}')
        msgs = [ChatMessage.assistant(content="", tool_calls=[tc])]
        result = p._build_messages(msgs)
        assert result[0]["tool_calls"][0]["function"]["name"] == "echo"
        assert result[0]["tool_calls"][0]["function"]["arguments"] == {"text": "hi"}

    def test_tool_result_has_tool_name(self) -> None:
        p = OllamaProvider()
        msgs = [ChatMessage.tool("result data", "echo")]
        result = p._build_messages(msgs)
        assert result[0]["role"] == "tool"
        assert result[0]["content"] == "result data"
        assert result[0]["tool_name"] == "echo"


# ---------------------------------------------------------------------------
# Tool building
# ---------------------------------------------------------------------------

class TestOllamaToolBuilding:
    def test_build_tools(self) -> None:
        p = OllamaProvider()
        tools = [ToolDefinition(name="echo", description="Echo it", parameters={"type": "object"})]
        result = p._build_tools(tools)
        assert result is not None
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "echo"
        assert result[0]["function"]["description"] == "Echo it"

    def test_build_tools_none(self) -> None:
        p = OllamaProvider()
        assert p._build_tools(None) is None
        assert p._build_tools([]) is None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestOllamaResponseParsing:
    def test_parse_basic_response(self) -> None:
        p = OllamaProvider()
        data = {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": "Hello!"},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        resp = p._parse_response(data, "llama3.2")
        assert resp.content == "Hello!"
        assert resp.model == "llama3.2"
        assert resp.finish_reason == "stop"
        assert resp.usage.prompt_tokens == 10
        assert resp.usage.completion_tokens == 5
        assert resp.reasoning_content is None

    def test_parse_tool_call_response(self) -> None:
        p = OllamaProvider()
        data = {
            "model": "llama3.2",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "echo", "arguments": {"text": "hi"}}},
                    {"function": {"name": "add", "arguments": {"a": 1, "b": 2}}},
                ],
            },
            "done": True,
            "prompt_eval_count": 20,
            "eval_count": 10,
        }
        resp = p._parse_response(data, "llama3.2")
        assert len(resp.tool_calls) == 2
        assert resp.tool_calls[0].id == "call_0"
        assert resp.tool_calls[0].name == "echo"
        assert json.loads(resp.tool_calls[0].arguments) == {"text": "hi"}
        assert resp.tool_calls[1].name == "add"

    def test_parse_thinking_response(self) -> None:
        p = OllamaProvider()
        data = {
            "model": "qwq:32b",
            "message": {
                "role": "assistant",
                "content": "The answer is 42.",
                "thinking": "Let me reason step by step...",
            },
            "done": True,
            "prompt_eval_count": 15,
            "eval_count": 25,
        }
        resp = p._parse_response(data, "qwq:32b")
        assert resp.content == "The answer is 42."
        assert resp.reasoning_content == "Let me reason step by step..."

    def test_parse_response_without_done_reason(self) -> None:
        p = OllamaProvider()
        data = {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": "ok"},
            "done": True,
            "prompt_eval_count": 5,
            "eval_count": 1,
        }
        resp = p._parse_response(data, "llama3.2")
        assert resp.finish_reason == "stop"


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------

class TestOllamaStreamParsing:
    def _parse(self, provider: OllamaProvider, payload: dict) -> StreamChunk:
        return provider._parse_stream_chunk(payload, provider.default_model)

    def test_plain_content_delta(self) -> None:
        p = OllamaProvider()
        chunk = self._parse(p, {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": "Hello"},
            "done": False,
        })
        assert chunk.content == "Hello"
        assert chunk.finish_reason is None
        assert chunk.raw_delta is None

    def test_thinking_content_in_stream(self) -> None:
        p = OllamaProvider()
        chunk = self._parse(p, {
            "model": "qwq:32b",
            "message": {"role": "assistant", "content": "", "thinking": "step 1: analyze"},
            "done": False,
        })
        assert chunk.raw_delta == {"reasoning_content": "step 1: analyze"}

    def test_done_chunk(self) -> None:
        p = OllamaProvider()
        chunk = self._parse(p, {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "done_reason": "stop",
        })
        assert chunk.finish_reason == "stop"

    def test_tool_calls_delta_forwarded(self) -> None:
        p = OllamaProvider()
        tc = [{"function": {"name": "echo", "arguments": {"text": "hi"}}}]
        chunk = self._parse(p, {
            "model": "llama3.2",
            "message": {"role": "assistant", "content": "", "tool_calls": tc},
            "done": False,
        })
        assert chunk.tool_calls_delta[0]["index"] == 0
        assert chunk.tool_calls_delta[0]["function"]["name"] == "echo"
        assert json.loads(chunk.tool_calls_delta[0]["function"]["arguments"]) == {"text": "hi"}

    def test_tool_calls_delta_indexes_multiple_calls(self) -> None:
        p = OllamaProvider()
        chunk = self._parse(p, {
            "model": "llama3.2",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "first", "arguments": {"a": 1}}},
                    {"function": {"name": "second", "arguments": {"b": 2}}},
                ],
            },
            "done": False,
        })
        assert [tc["index"] for tc in chunk.tool_calls_delta] == [0, 1]

    def test_empty_message(self) -> None:
        p = OllamaProvider()
        chunk = self._parse(p, {"model": "llama3.2", "message": {}, "done": False})
        assert chunk.content == ""
        assert chunk.tool_calls_delta == []


# ---------------------------------------------------------------------------
# Model resolution for connectivity tests
# ---------------------------------------------------------------------------

class TestOllamaModelResolution:
    def test_pick_prefers_installed_match_over_missing_preferred(self) -> None:
        installed = ["llama3.2:latest", "qwen2.5:7b", "nomic-embed-text"]
        picked = OllamaProvider.pick_test_model(
            installed,
            preferred="llama3.1:70b",
            configured=["llama3.1:70b", "llama3.2"],
            default_model="llama3.1:70b",
        )
        assert picked == "llama3.2:latest"

    def test_pick_matches_tagless_config_to_tagged_install(self) -> None:
        installed = ["qwen2.5:7b"]
        assert (
            OllamaProvider.pick_test_model(installed, preferred="qwen2.5:7b")
            == "qwen2.5:7b"
        )

    def test_pick_skips_embedding_models_when_chat_available(self) -> None:
        installed = ["nomic-embed-text", "llama3.2"]
        assert OllamaProvider.pick_test_model(installed) == "llama3.2"

    def test_pick_returns_none_when_no_models(self) -> None:
        assert OllamaProvider.pick_test_model([]) is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestOllamaErrorHandling:
    def test_404_model_error(self) -> None:
        p = OllamaProvider()
        with pytest.raises(ModelNotFoundError):
            p._handle_error(404, "model 'nonexistent' not found", "nonexistent")

    def test_404_generic(self) -> None:
        p = OllamaProvider()
        with pytest.raises(LLMServiceError, match="Not found"):
            p._handle_error(404, "endpoint not found", "llama3.2")

    def test_500_server_error(self) -> None:
        p = OllamaProvider()
        with pytest.raises(LLMServiceError, match="Ollama server error"):
            p._handle_error(500, "internal error", "llama3.2")

    def test_generic_error(self) -> None:
        p = OllamaProvider()
        with pytest.raises(LLMServiceError, match="Ollama API error.*400"):
            p._handle_error(400, "bad request", "llama3.2")


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

class TestOllamaRegistryWiring:
    def test_providers_package_exports_ollama(self) -> None:
        from leagent.llm.providers import OllamaProvider as Exported
        assert Exported is OllamaProvider

    def test_provider_config_constructs_ollama(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        pc = ProviderConfig(
            name="ollama-test",
            type="ollama",
            enabled=True,
            api_key="",
            base_url="http://gpu-host:11434",
            models=[{"name": "qwen2.5:72b", "tier": "tier1"}],
            timeout=300,
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, OllamaProvider)
        assert provider.base_url == "http://gpu-host:11434"
        assert provider.default_model == "qwen2.5:72b"
