from __future__ import annotations

import json

import pytest

from leagent.llm.base import ChatMessage, StreamChunk, ToolDefinition
from leagent.llm.providers.custom import CustomOpenAIProvider
from leagent.llm.providers.openai import OpenAIProvider


class TestCustomProviderParsing:
    def test_non_streaming_dict_arguments_normalized(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        resp = p._parse_response({
            "model": "custom-model",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "ask_user",
                            "arguments": {"questions": []},
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        })

        assert resp.tool_calls[0].name == "ask_user"
        assert json.loads(resp.tool_calls[0].arguments) == {"questions": []}

    def test_streaming_dict_arguments_normalized(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        chunk = p._parse_stream_chunk(
            {
                "model": "custom-model",
                "choices": [{
                    "delta": {
                        "tool_calls": [{
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "ask_user",
                                "arguments": {"questions": []},
                            },
                        }],
                    },
                    "finish_reason": None,
                }],
            },
            "custom-model",
        )

        args = chunk.tool_calls_delta[0]["function"]["arguments"]
        assert isinstance(args, str)
        assert json.loads(args) == {"questions": []}

    @pytest.mark.asyncio
    async def test_content_json_tool_call_is_converted_before_visible_text(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        payload = json.dumps(
            {
                "name": "ask_user",
                "arguments": {"questions": [{"id": "q", "prompt": "Continue?"}]},
            },
            ensure_ascii=False,
        )

        async def fake_openai_stream(*_args, **_kwargs):
            yield StreamChunk(content=payload[:12], model="custom")
            yield StreamChunk(content=payload[12:], finish_reason="stop", model="custom")

        monkeypatch.setattr(OpenAIProvider, "stream", fake_openai_stream)

        chunks = [
            chunk
            async for chunk in p.stream(
                messages=[ChatMessage.user("ask")],
                model="custom",
                tools=[
                    ToolDefinition(
                        name="ask_user",
                        description="Ask the user",
                        parameters={"type": "object"},
                    ),
                ],
            )
        ]

        assert [chunk.content for chunk in chunks if chunk.content] == []
        tool_delta_chunks = [chunk for chunk in chunks if chunk.tool_calls_delta]
        assert len(tool_delta_chunks) == 1
        delta = tool_delta_chunks[0].tool_calls_delta[0]
        assert delta["function"]["name"] == "ask_user"
        assert json.loads(delta["function"]["arguments"]) == {
            "questions": [{"id": "q", "prompt": "Continue?"}],
        }


class TestCustomProviderWiring:
    def test_providers_package_exports_custom(self) -> None:
        from leagent.llm.providers import CustomOpenAIProvider as Exported

        assert Exported is CustomOpenAIProvider

    def test_provider_config_constructs_custom_provider(self) -> None:
        from leagent.llm.provider_config import ProviderConfig, ProviderConfigService

        pc = ProviderConfig(
            name="acme",
            type="custom",
            enabled=True,
            api_key="k",
            base_url="https://api.example.com/v1",
            models=[{"name": "custom-model", "tier": "tier1"}],
            timeout=30,
        )
        svc = ProviderConfigService.__new__(ProviderConfigService)
        provider = svc._create_llm_provider(pc)
        assert isinstance(provider, CustomOpenAIProvider)
        assert provider.base_url == "https://api.example.com/v1"
        assert provider.default_model == "custom-model"
