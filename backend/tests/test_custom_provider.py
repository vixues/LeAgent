from __future__ import annotations

import json
import logging

import pytest

from leagent.exceptions.llm import LLMServiceError
from leagent.llm.base import ChatMessage, LLMResponse, StreamChunk, ToolCall, ToolDefinition
from leagent.llm.providers.custom import CustomOpenAIProvider
from leagent.llm.providers.openai import OpenAIProvider


class TestCustomProviderStreamSanitization:
    @pytest.mark.asyncio
    async def test_structured_tool_call_strips_duplicate_json_content(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        payload = json.dumps(
            {"name": "markdown_processor", "arguments": {"operation": "read"}},
            ensure_ascii=False,
        )

        async def fake_openai_stream(*_args, **_kwargs):
            yield StreamChunk(
                content=payload,
                tool_calls_delta=[{
                    "index": 0,
                    "id": "call_real_1",
                    "type": "function",
                    "function": {
                        "name": "markdown_processor",
                        "arguments": json.dumps({"operation": "read"}),
                    },
                }],
                finish_reason="tool_calls",
                model="custom",
            )

        monkeypatch.setattr(OpenAIProvider, "stream", fake_openai_stream)

        chunks = [
            chunk
            async for chunk in p.stream(
                messages=[ChatMessage.user("read md")],
                model="custom",
            )
        ]

        assert [c.content for c in chunks if c.content] == []
        assert len([c for c in chunks if c.tool_calls_delta]) == 1

    @pytest.mark.asyncio
    async def test_second_content_json_not_emitted_after_first_tool_call(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        payload = json.dumps(
            {"name": "echo", "arguments": {"text": "hi"}},
            ensure_ascii=False,
        )

        async def fake_openai_stream(*_args, **_kwargs):
            yield StreamChunk(content=payload, model="custom")
            yield StreamChunk(content=payload, finish_reason="stop", model="custom")

        monkeypatch.setattr(OpenAIProvider, "stream", fake_openai_stream)

        chunks = [
            chunk
            async for chunk in p.stream(messages=[ChatMessage.user("hi")], model="custom")
        ]

        assert [c.content for c in chunks if c.content] == []
        assert len([c for c in chunks if c.tool_calls_delta]) == 1


class TestCustomProviderStreamParsing:
    def _parse(self, provider: CustomOpenAIProvider, payload: dict) -> StreamChunk:
        return provider._parse_stream_chunk(payload, "custom-model")

    def test_null_content_coalesced_to_empty_string(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        chunk = self._parse(
            p,
            {
                "model": "custom-model",
                "choices": [{"delta": {"content": None}, "finish_reason": None}],
            },
        )
        assert chunk.content == ""

    def test_reasoning_content_surfaces_via_raw_delta(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        chunk = self._parse(
            p,
            {
                "model": "custom-model",
                "choices": [{
                    "delta": {
                        "content": "",
                        "reasoning_content": "thinking step",
                    },
                    "finish_reason": None,
                }],
            },
        )
        assert chunk.raw_delta is not None
        assert chunk.raw_delta.get("reasoning_content") == "thinking step"

    def test_stream_usage_extracted_from_payload(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        chunk = self._parse(
            p,
            {
                "model": "custom-model",
                "choices": [{"delta": {"content": "hi"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )
        assert chunk.usage is not None
        assert chunk.usage.prompt_tokens == 10
        assert chunk.usage.completion_tokens == 5


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

    @pytest.mark.asyncio
    async def test_markdown_processor_json_single_chunk_without_tools_list(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        payload = json.dumps(
            {
                "name": "markdown_processor",
                "arguments": {
                    "operation": "create",
                    "file_path": "example.md",
                    "content": "# Hello",
                },
            },
            ensure_ascii=False,
        )

        async def fake_openai_stream(*_args, **_kwargs):
            yield StreamChunk(content=payload, finish_reason="stop", model="custom")

        monkeypatch.setattr(OpenAIProvider, "stream", fake_openai_stream)

        chunks = [
            chunk
            async for chunk in p.stream(
                messages=[ChatMessage.user("create md")],
                model="custom",
            )
        ]

        assert [chunk.content for chunk in chunks if chunk.content] == []
        assert len([c for c in chunks if c.tool_calls_delta]) == 1
        delta = chunks[0].tool_calls_delta[0]
        assert delta["function"]["name"] == "markdown_processor"

    def test_non_streaming_content_json_becomes_tool_call(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        payload = json.dumps(
            {
                "name": "markdown_processor",
                "arguments": {"operation": "create", "file_path": "a.md"},
            },
            ensure_ascii=False,
        )
        resp = p._parse_response({
            "model": "custom-model",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": payload,
                    "tool_calls": None,
                },
                "finish_reason": "stop",
            }],
        })

        assert isinstance(resp, LLMResponse)
        assert resp.content is None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "markdown_processor"
        assert resp.finish_reason == "tool_calls"

    def test_synthetic_content_tool_history_is_text_for_custom_gateway(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        body = p._build_request_body(
            messages=[
                ChatMessage.user("create md"),
                ChatMessage.assistant(
                    tool_calls=[
                        ToolCall(
                            id="standard_call",
                            name="unused",
                            arguments=json.dumps({"value": 1}),
                        )
                    ],
                ),
            ],
            model="custom",
            temperature=0.1,
            max_tokens=1024,
            tools=None,
            tool_choice=None,
            stop=None,
        )

        assert body["messages"][1]["tool_calls"][0]["function"]["name"] == "unused"

    def test_call_content_history_avoids_tool_messages(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        body = p._build_request_body(
            messages=[
                ChatMessage.user("create md"),
                ChatMessage.assistant(
                    tool_calls=[
                        ToolCall(
                            id="call_content_0",
                            name="markdown_processor",
                            arguments=json.dumps({"operation": "write"}),
                        )
                    ],
                ),
                ChatMessage.tool('{"success": true}', "call_content_0"),
            ],
            model="custom",
            temperature=0.1,
            max_tokens=1024,
            tools=None,
            tool_choice=None,
            stop=None,
        )

        assert "tool_calls" not in body["messages"][1]
        assert body["messages"][1]["role"] == "assistant"
        assert body["messages"][1].get("content") in (None, "")
        assert body["messages"][2] == {
            "role": "user",
            "content": 'Tool result for call_content_0:\n{"success": true}',
        }

    def test_dict_message_content_stringified(self) -> None:
        from leagent.llm.providers.custom import _normalize_custom_request_messages

        out = _normalize_custom_request_messages([{"role": "user", "content": {"k": 1}}])
        assert out[0]["content"] == '{"k": 1}'

    def test_non_streaming_reasoning_content_preserved(self) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        resp = p._parse_response({
            "model": "custom-model",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "done",
                    "reasoning_content": "thought first",
                },
                "finish_reason": "stop",
            }],
        })
        assert resp.reasoning_content == "thought first"
        assert resp.content == "done"


class TestCustomProviderErrorHandling:
    def test_handle_error_logs_message_shape_hint(self, caplog: pytest.LogCaptureFixture) -> None:
        p = CustomOpenAIProvider(api_key="k", base_url="https://custom.example/v1")
        with caplog.at_level(logging.ERROR):
            with pytest.raises(LLMServiceError, match="concatenate str"):
                p._handle_error(
                    400,
                    {"error": {"message": 'can only concatenate str (not "dict") to str'}},
                    "custom-model",
                )
        assert "custom_gateway_message_shape_error" in caplog.text


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
