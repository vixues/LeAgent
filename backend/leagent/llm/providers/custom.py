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
import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from leagent.llm.base import ChatMessage, LLMResponse, StreamChunk, ToolCall, ToolDefinition
from leagent.llm.providers.openai import OpenAIProvider, _extract_reasoning_text
from leagent.tools.executor import parse_tool_arguments_str

logger = logging.getLogger(__name__)

_SYNTHETIC_TOOL_ID_PREFIX = "call_content_"


def _tool_arguments_to_json_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False)


def _stringify_message_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
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


def _is_tool_call_payload(obj: dict[str, Any]) -> bool:
    """True when the object is only ``{"name": "...", "arguments": ...}``."""
    name = obj.get("name")
    if not isinstance(name, str) or not name.strip():
        return False
    if "arguments" not in obj:
        return False
    return not (set(obj.keys()) - {"name", "arguments"})


def _looks_like_content_tool_call_prefix(
    content: str,
    *,
    known_tool_names: set[str],
) -> bool:
    text = _strip_json_fence(content)
    if not text or not text.startswith("{"):
        return False
    if '"name"' in text and '"arguments"' in text:
        return True
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
    del known_tool_names  # shape-based detection; names are not whitelisted
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
    if not _is_tool_call_payload(obj):
        return None

    return {
        "index": 0,
        "id": f"{_SYNTHETIC_TOOL_ID_PREFIX}0",
        "type": "function",
        "function": {
            "name": name.strip(),
            "arguments": _tool_arguments_to_json_string(obj.get("arguments", {})),
        },
    }


def _flush_pending_content_tool_call(
    pending: str,
    *,
    known_tool_names: set[str],
    finish_reason: str | None = None,
    usage: Any = None,
    model: str = "",
) -> StreamChunk | None:
    if not pending:
        return None
    delta = _content_tool_call_delta_from_text(
        pending,
        known_tool_names=known_tool_names,
    )
    if delta is not None:
        return StreamChunk(
            tool_calls_delta=[delta],
            finish_reason=finish_reason,
            usage=usage,
            model=model,
        )
    return StreamChunk(
        content=pending,
        finish_reason=finish_reason,
        usage=usage,
        model=model,
    )


def _tool_call_from_content_delta(delta: dict[str, Any]) -> ToolCall:
    fn = delta.get("function") or {}
    return ToolCall(
        id=str(delta.get("id") or f"{_SYNTHETIC_TOOL_ID_PREFIX}0"),
        name=str(fn.get("name") or ""),
        arguments=_tool_arguments_to_json_string(fn.get("arguments")),
    )


def _normalize_tool_call_records(
    tool_calls: list[Any],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for tc in tool_calls:
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


def _normalize_custom_request_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Make synthetic content-tool history digestible for loose gateways."""
    normalized: list[dict[str, Any]] = []
    synthetic_tool_ids: set[str] = set()

    for msg in messages:
        item = dict(msg)
        if "content" in item:
            item["content"] = _stringify_message_content(item.get("content"))

        tool_calls = item.get("tool_calls")
        if isinstance(tool_calls, list):
            next_tool_calls: list[dict[str, Any]] = []
            synthetic_payloads: list[str] = []
            for tc in _normalize_tool_call_records(tool_calls):
                call_id = str(tc.get("id") or "")
                if call_id.startswith(_SYNTHETIC_TOOL_ID_PREFIX):
                    synthetic_tool_ids.add(call_id)
                    fn = tc.get("function") or {}
                    synthetic_payloads.append(json.dumps(
                        {
                            "name": fn.get("name") or tc.get("name") or "",
                            "arguments": fn.get("arguments") or "{}",
                        },
                        ensure_ascii=False,
                    ))
                else:
                    next_tool_calls.append(tc)

            if synthetic_payloads:
                prior = item.get("content")
                item["content"] = "\n\n".join(
                    part for part in [prior, *synthetic_payloads] if part
                )
                item.pop("tool_calls", None)
            elif next_tool_calls:
                item["tool_calls"] = next_tool_calls
            else:
                item.pop("tool_calls", None)

        if (
            item.get("role") == "tool"
            and str(item.get("tool_call_id") or "") in synthetic_tool_ids
        ):
            normalized.append({
                "role": "user",
                "content": (
                    f"Tool result for {item.get('name') or item.get('tool_call_id')}:\n"
                    f"{item.get('content') or ''}"
                ),
            })
            continue

        normalized.append(item)

    return normalized


class _ContentToolCallBuffer:
    """Coalesce assistant ``content`` that encodes a tool call as JSON text."""

    def __init__(self, known_tool_names: set[str]) -> None:
        self._known_tool_names = known_tool_names
        self._pending = ""

    def ingest(self, chunk: StreamChunk, *, default_model: str) -> list[StreamChunk]:
        out: list[StreamChunk] = []
        content = chunk.content or ""
        should_buffer = bool(
            content
            and (
                self._pending
                or _looks_like_content_tool_call_prefix(
                    content,
                    known_tool_names=self._known_tool_names,
                )
            )
        )
        if not should_buffer:
            if self._pending:
                flushed = _flush_pending_content_tool_call(
                    self._pending,
                    known_tool_names=self._known_tool_names,
                    model=chunk.model or default_model,
                )
                if flushed is not None:
                    out.append(flushed)
                self._pending = ""
            out.append(chunk)
            return out

        self._pending += content
        if chunk.raw_delta:
            out.append(StreamChunk(raw_delta=chunk.raw_delta, model=chunk.model or default_model))

        delta = _content_tool_call_delta_from_text(
            self._pending,
            known_tool_names=self._known_tool_names,
        )
        if delta is None:
            if chunk.finish_reason:
                flushed = _flush_pending_content_tool_call(
                    self._pending,
                    known_tool_names=self._known_tool_names,
                    finish_reason=chunk.finish_reason,
                    model=chunk.model or default_model,
                    usage=chunk.usage,
                )
                if flushed is not None:
                    out.append(flushed)
                self._pending = ""
            return out

        out.append(StreamChunk(
            tool_calls_delta=[delta],
            finish_reason=chunk.finish_reason,
            model=chunk.model or default_model,
            usage=chunk.usage,
        ))
        self._pending = ""
        return out

    def flush_tail(self, *, model: str) -> StreamChunk | None:
        if not self._pending:
            return None
        flushed = _flush_pending_content_tool_call(
            self._pending,
            known_tool_names=self._known_tool_names,
            model=model,
        )
        self._pending = ""
        return flushed


class CustomOpenAIProvider(OpenAIProvider):
    """OpenAI-compatible provider for non-standard custom gateways."""

    name = "custom"
    supports_streaming = True
    supports_tools = True

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

    # ------------------------------------------------------------------
    # Request body construction
    # ------------------------------------------------------------------

    def _build_request_body(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
        tool_choice: Literal["auto", "none", "required"] | str | None,
        stop: list[str] | None,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        body = super()._build_request_body(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            stream=stream,
            **kwargs,
        )
        raw_messages = body.get("messages")
        if isinstance(raw_messages, list):
            body["messages"] = _normalize_custom_request_messages(raw_messages)
        return body

    # ------------------------------------------------------------------
    # Non-streaming completion
    # ------------------------------------------------------------------

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        normalized_data = dict(data)
        choices = list(normalized_data.get("choices") or [])
        if choices:
            first = dict(choices[0])
            message = dict(first.get("message") or {})
            tool_calls = _normalize_tool_call_records(message.get("tool_calls") or [])
            if tool_calls:
                message["tool_calls"] = tool_calls
                first["message"] = message
                choices[0] = first
                normalized_data["choices"] = choices

        response = super()._parse_response(normalized_data)

        choice = (normalized_data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        rc = message.get("reasoning_content")
        if isinstance(rc, str) and rc.strip():
            response.reasoning_content = rc

        if response.tool_calls:
            return response

        content = response.content or ""
        if content.strip():
            delta = _content_tool_call_delta_from_text(content, known_tool_names=set())
            if delta is not None:
                return LLMResponse(
                    content=None,
                    tool_calls=[_tool_call_from_content_delta(delta)],
                    finish_reason="tool_calls",
                    model=response.model,
                    usage=response.usage,
                    raw_response=response.raw_response,
                    reasoning_content=response.reasoning_content,
                )
        return response

    # ------------------------------------------------------------------
    # Streaming completion
    # ------------------------------------------------------------------

    def _parse_stream_chunk(self, data: dict[str, Any], model: str) -> StreamChunk:
        chunk = super()._parse_stream_chunk(data, model)
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        delta = choice.get("delta", {}) or {}

        content_val = delta.get("content")
        content = "" if content_val is None else str(content_val)

        raw_delta = chunk.raw_delta
        if reasoning := _extract_reasoning_text(delta):
            raw_delta = {**(raw_delta or {}), "reasoning_content": reasoning}

        if raw_tc := delta.get("tool_calls"):
            tool_calls_delta = self._normalize_tool_call_deltas(raw_tc)
        else:
            tool_calls_delta = self._normalize_tool_call_deltas(list(chunk.tool_calls_delta))

        usage = chunk.usage or self._usage_from_response_payload(data)

        return StreamChunk(
            content=content,
            tool_calls_delta=tool_calls_delta,
            finish_reason=chunk.finish_reason,
            model=chunk.model,
            raw_delta=raw_delta,
            usage=usage,
        )

    def _normalize_tool_call_deltas(
        self,
        raw_tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return _normalize_tool_call_records(raw_tool_calls)

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
        buffer = _ContentToolCallBuffer(_known_tool_names(tools))

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
            for emitted in buffer.ingest(chunk, default_model=model):
                yield emitted

        tail = buffer.flush_tail(model=model)
        if tail is not None:
            yield tail

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_error(
        self,
        status_code: int,
        response_body: dict[str, Any] | str,
        model: str,
    ) -> None:
        if status_code == 400:
            error_msg = ""
            if isinstance(response_body, dict):
                error_obj = response_body.get("error", {})
                if isinstance(error_obj, dict):
                    error_msg = str(error_obj.get("message", ""))
                else:
                    error_msg = str(response_body)
            else:
                error_msg = str(response_body)
            lowered = error_msg.lower()
            if "concatenate str" in lowered and "dict" in lowered:
                logger.error(
                    "custom_gateway_message_shape_error",
                    extra={
                        "model": model,
                        "hint": (
                            "The gateway rejected OpenAI-shaped tool history. "
                            "Synthetic call_content_* tool turns are rewritten to "
                            "plain text before send; verify provider type is 'custom' "
                            "or 'vllm' (not strict 'openai')."
                        ),
                    },
                )
        super()._handle_error(status_code, response_body, model)
