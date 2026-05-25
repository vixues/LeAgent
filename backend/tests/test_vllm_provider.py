"""Offline tests for the vLLM LLM provider.

These never hit the network: we exercise the pure-Python surface
(``_build_request_body``, constructor defaults, structured_outputs injection,
registry wiring).
"""

from __future__ import annotations

import pytest

from leagent.llm.base import ChatMessage, ToolDefinition
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

    def test_provider_preset_exists(self) -> None:
        from leagent.llm.provider_config import PROVIDER_PRESETS
        assert "vllm" in PROVIDER_PRESETS
        assert PROVIDER_PRESETS["vllm"]["default_base_url"] == "http://localhost:8000/v1"
