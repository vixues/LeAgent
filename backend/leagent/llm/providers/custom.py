"""Custom OpenAI-compatible provider with tolerant tool-call parsing.

Many self-hosted or gateway-backed OpenAI-compatible endpoints are close to
the Chat Completions shape, but differ in tool-call details:

- ``function.arguments`` may be streamed as an object instead of a JSON string.
- Some models emit ``{"name": "...", "arguments": {...}}`` in ``content``
  instead of structured ``tool_calls``.

Keep those compatibility shims here so the standard OpenAI provider remains
strict and provider-specific subclasses can opt in explicitly.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

from leagent.llm.base import ChatMessage, LLMResponse, StreamChunk, ToolDefinition
from leagent.llm.providers.openai import OpenAIProvider
from leagent.tools.executor import parse_tool_arguments_str


def _tool_arguments_to_json_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False)


def _known_tool_names(tools: list[ToolDefinition] | None) -> set[str]:
    return {tool.name for tool in tools or [] if tool.name}


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    first_newline = stripped.find("\n")
    if first_newline < 0:
        return stripped
    fence_label = stripped[3:first_newline].strip().lower()
    if fence_label not in ("", "json", "jsonc"):
        return stripped
    body = stripped[first_newline + 1 :]
    closing = body.rfind("```")
    if closing >= 0:
        body = body[:closing]
    return body.strip()


def _looks_like_content_tool_call_prefix(
    content: str,
    *,
    known_tool_names: set[str],
) -> bool:
    text = _strip_json_fence(content)
    if not text or not text.startswith("{"):
        return False
    if '"name"' in text or "'name'" in text:
        return True
    if known_tool_names and any(name in text for name in known_tool_names):
        return True
    return len(text) < 80


def _content_tool_call_delta_from_text(
    content: str,
    *,
    known_tool_names: set[str],
) -> dict[str, Any] | None:
    text = _strip_json_fence(content)
    if not text or '"name"' not in text:
        return None
    try:
        loaded = json.loads(text)
        obj = loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        parsed = parse_tool_arguments_str(text)
        obj = parsed if isinstance(parsed, dict) else None
    if not obj:
        return None

    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    name = name.strip()
    if known_tool_names and name not in known_tool_names:
        return None

    return {
        "index": 0,
        "id": "call_content_0",
        "type": "function",
        "function": {
            "name": name,
            "arguments": _tool_arguments_to_json_string(obj.get("arguments", {})),
        },
    }


class CustomOpenAIProvider(OpenAIProvider):
    """OpenAI-compatible provider for non-standard custom gateways."""

    name = "custom"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        default_model: str = "",
        timeout: float = 120.0,
        max_retries: int = 2,
        parse_think_tags: bool = True,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            timeout=timeout,
            max_retries=max_retries,
            parse_think_tags=parse_think_tags,
        )

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        normalized_data = dict(data)
        choices = list(normalized_data.get("choices") or [])
        if choices:
            first = dict(choices[0])
            message = dict(first.get("message") or {})
            tool_calls: list[dict[str, Any]] = []
            for tc in message.get("tool_calls") or []:
                if not isinstance(tc, dict):
                    continue
                item = dict(tc)
                function = item.get("function")
                if isinstance(function, dict):
                    fn = dict(function)
                    fn["arguments"] = _tool_arguments_to_json_string(fn.get("arguments"))
                    item["function"] = fn
                tool_calls.append(item)
            if tool_calls:
                message["tool_calls"] = tool_calls
                first["message"] = message
                choices[0] = first
                normalized_data["choices"] = choices
        return super()._parse_response(normalized_data)

    def _parse_stream_chunk(self, data: dict[str, Any], model: str) -> StreamChunk:
        chunk = super()._parse_stream_chunk(data, model)
        if chunk.tool_calls_delta:
            chunk.tool_calls_delta = self._normalize_tool_call_deltas(chunk.tool_calls_delta)
        return chunk

    def _normalize_tool_call_deltas(
        self,
        raw_tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for tc in raw_tool_calls:
            if not isinstance(tc, dict):
                continue
            item = dict(tc)
            function = item.get("function")
            if isinstance(function, dict):
                fn = dict(function)
                if "arguments" in fn:
                    fn["arguments"] = _tool_arguments_to_json_string(fn.get("arguments"))
                item["function"] = fn
            normalized.append(item)
        return normalized

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        tools: list[ToolDefinition] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        known_names = _known_tool_names(tools)
        pending_content_tool_call = ""

        async for chunk in super().stream(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            **kwargs,
        ):
            content = chunk.content or ""
            should_buffer = bool(
                content
                and tools
                and (
                    pending_content_tool_call
                    or _looks_like_content_tool_call_prefix(
                        content,
                        known_tool_names=known_names,
                    )
                )
            )
            if not should_buffer:
                if pending_content_tool_call:
                    yield StreamChunk(content=pending_content_tool_call, model=chunk.model or model)
                    pending_content_tool_call = ""
                yield chunk
                continue

            pending_content_tool_call += content
            delta = _content_tool_call_delta_from_text(
                pending_content_tool_call,
                known_tool_names=known_names,
            )
            if chunk.raw_delta:
                yield StreamChunk(raw_delta=chunk.raw_delta, model=chunk.model or model)
            if delta is None:
                if chunk.finish_reason:
                    yield StreamChunk(
                        content=pending_content_tool_call,
                        finish_reason=chunk.finish_reason,
                        model=chunk.model or model,
                        usage=chunk.usage,
                    )
                    pending_content_tool_call = ""
                continue

            yield StreamChunk(
                tool_calls_delta=[delta],
                finish_reason=chunk.finish_reason,
                model=chunk.model or model,
                usage=chunk.usage,
            )
            pending_content_tool_call = ""

        if pending_content_tool_call:
            yield StreamChunk(content=pending_content_tool_call, model=model)
