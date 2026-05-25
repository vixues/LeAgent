"""Anthropic LLM provider.

Supports Claude models via the Anthropic Messages API with:

- Streaming completions (text + tool use via ``input_json_delta``)
- Tool/function calling (``tool_use`` / ``tool_result`` block protocol)
- Adaptive thinking (``thinking: {type: "adaptive"}``) for Opus 4.7+
- Vision (base64 and URL image content blocks)
- Pooled HTTP clients for connection reuse
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

import httpx
import structlog

from leagent.utils.httpx_proxy import httpx_trust_env

from leagent.exceptions.llm import (
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
)
from leagent.llm.base import (
    ChatMessage,
    EmbeddingResponse,
    LLMProvider,
    LLMResponse,
    MessageRole,
    StreamChunk,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)


logger = structlog.get_logger(__name__)

_STREAM_HTTPX_TIMEOUT = httpx.Timeout(connect=30.0, read=None, write=60.0, pool=10.0)
_STREAM_HTTPX_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=60.0)


class AnthropicProvider(LLMProvider):
    """Anthropic provider for Claude models.

    Supports:
    - Claude 3.x, Claude 4.x, and Opus 4.7 series
    - Streaming completions with tool use assembly
    - Tool/function calling
    - Adaptive thinking (Opus 4.7+)
    - Vision (base64 images)
    """

    name = "anthropic"
    supports_streaming = True
    supports_tools = True
    supports_embeddings = False
    supports_vision = True

    BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-sonnet-4-20250514",
        timeout: float = 120.0,
        max_retries: int = 2,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self._http_complete_client: httpx.AsyncClient | None = None
        self._http_stream_client: httpx.AsyncClient | None = None

    def _ensure_complete_client(self) -> httpx.AsyncClient:
        if self._http_complete_client is None:
            self._http_complete_client = httpx.AsyncClient(
                timeout=self.timeout,
                trust_env=httpx_trust_env(),
            )
        return self._http_complete_client

    def _ensure_stream_client(self) -> httpx.AsyncClient:
        if self._http_stream_client is None:
            self._http_stream_client = httpx.AsyncClient(
                timeout=_STREAM_HTTPX_TIMEOUT,
                limits=_STREAM_HTTPX_LIMITS,
                trust_env=httpx_trust_env(),
            )
        return self._http_stream_client

    async def aclose(self) -> None:
        """Release pooled HTTP connections."""
        for client in (self._http_complete_client, self._http_stream_client):
            if client is not None:
                await client.aclose()
        self._http_complete_client = None
        self._http_stream_client = None

    def _get_default_model(self) -> str:
        return self.default_model

    def _get_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }

    def _split_messages(
        self, messages: list[ChatMessage]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Separate the system prompt from the conversation messages.

        Anthropic's API requires the system prompt as a top-level parameter,
        not as an entry in the messages array.  Also handles vision content
        (images encoded as base64).
        """
        system: str | None = None
        chat_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system = msg.content or ""
            elif msg.role == MessageRole.TOOL:
                chat_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_call_id or "",
                            "content": msg.content or "",
                        }
                    ],
                })
            elif msg.tool_calls:
                content: list[dict[str, Any]] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    args: dict[str, Any]
                    if isinstance(tc.arguments, dict):
                        args = tc.arguments
                    elif isinstance(tc.arguments, str):
                        try:
                            parsed = json.loads(tc.arguments)
                        except (json.JSONDecodeError, TypeError):
                            parsed = None
                        if isinstance(parsed, dict):
                            args = parsed
                        else:
                            from leagent.tools.executor import parse_tool_arguments_str

                            recovered = (
                                parse_tool_arguments_str(tc.arguments)
                                if tc.arguments
                                else None
                            )
                            args = recovered if isinstance(recovered, dict) else {}
                            if not args:
                                logger.warning(
                                    "anthropic_tool_arguments_roundtrip_parse_failed",
                                    tool_name=tc.name,
                                    tool_call_id=tc.id,
                                    args_preview=(tc.arguments or "")[:400],
                                )
                    else:
                        args = {}
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": args,
                    })
                chat_messages.append({"role": "assistant", "content": content})
            else:
                chat_messages.append({
                    "role": msg.role.value,
                    "content": msg.content or "",
                })

        return system, chat_messages

    def _build_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Convert ToolDefinition list to Anthropic tool schema format."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def _build_request_body(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        tools: list[ToolDefinition] | None,
        tool_choice: Literal["auto", "none", "required"] | str | None,
        stop: list[str] | None,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        system, chat_messages = self._split_messages(messages)

        body: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

        if system:
            body["system"] = system

        if stop:
            body["stop_sequences"] = stop

        if tools:
            body["tools"] = self._build_tools(tools)
            if tool_choice:
                if tool_choice == "auto":
                    body["tool_choice"] = {"type": "auto"}
                elif tool_choice == "required":
                    body["tool_choice"] = {"type": "any"}
                elif tool_choice == "none":
                    body["tool_choice"] = {"type": "none"}
                else:
                    body["tool_choice"] = {"type": "tool", "name": tool_choice}

        # Adaptive thinking support (Opus 4.7+)
        thinking = kwargs.pop("thinking", None)
        if thinking:
            body["thinking"] = thinking

        return body

    def _parse_response(self, data: dict[str, Any], model: str) -> LLMResponse:
        """Parse Anthropic Messages API response into LLMResponse."""
        text_content: str | None = None
        tool_calls: list[ToolCall] = []
        reasoning_content: str | None = None

        for block in data.get("content", []):
            block_type = block.get("type")
            if block_type == "text":
                text_content = block.get("text", "")
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=json.dumps(block.get("input", {})),
                    )
                )
            elif block_type == "thinking":
                reasoning_content = block.get("thinking", "")

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
        )

        stop_reason = data.get("stop_reason", "end_turn")
        finish_reason = "stop"
        if stop_reason == "tool_use":
            finish_reason = "tool_calls"
        elif stop_reason == "max_tokens":
            finish_reason = "length"

        return LLMResponse(
            content=text_content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            stop_reason=stop_reason,
            model=data.get("model", model),
            usage=usage,
            raw_response=data,
            reasoning_content=reasoning_content,
        )

    def _handle_error(self, status_code: int, error_body: Any, model: str) -> None:
        error_msg = str(error_body)
        if isinstance(error_body, dict):
            error_info = error_body.get("error", {})
            error_msg = error_info.get("message", str(error_body))

        if status_code == 429:
            raise LLMRateLimitError(model=model)
        if status_code == 408:
            raise LLMTimeoutError(model=model, timeout_sec=int(self.timeout))
        raise LLMServiceError(
            f"Anthropic API error {status_code}: {error_msg}",
            model=model,
            endpoint=self.base_url,
        )

    async def complete(
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
    ) -> LLMResponse:
        body = self._build_request_body(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            stream=False,
            **kwargs,
        )

        url = f"{self.base_url}/messages"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                client = self._ensure_complete_client()
                response = await client.post(url, headers=self._get_headers(), json=body)

                if response.status_code == 200:
                    return self._parse_response(response.json(), model)

                try:
                    error_body = response.json()
                except json.JSONDecodeError:
                    error_body = response.text

                if response.status_code == 429 and attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue

                self._handle_error(response.status_code, error_body, model)

            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise LLMTimeoutError(model=model, timeout_sec=int(self.timeout)) from e

            except httpx.RequestError as e:
                last_error = e
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise LLMServiceError(
                    f"Request failed: {e}",
                    model=model,
                    endpoint=self.base_url,
                ) from e

        raise LLMServiceError(
            f"Max retries exceeded: {last_error}",
            model=model,
            endpoint=self.base_url,
        )

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
        body = self._build_request_body(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            stream=True,
            **kwargs,
        )

        url = f"{self.base_url}/messages"

        # Accumulators for streaming tool use assembly
        pending_tool_calls: dict[int, dict[str, Any]] = {}

        try:
            client = self._ensure_stream_client()
            async with client.stream("POST", url, headers=self._get_headers(), json=body) as response:
                if response.status_code != 200:
                    content = await response.aread()
                    try:
                        error_body = json.loads(content)
                    except json.JSONDecodeError:
                        error_body = content.decode()
                    self._handle_error(response.status_code, error_body, model)

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[len("data: "):]
                    if raw.strip() in ("", "[DONE]"):
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    chunk = self._process_stream_event(
                        event, model, pending_tool_calls
                    )
                    if chunk is not None:
                        yield chunk

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(model=model, timeout_sec=int(self.timeout)) from e
        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Stream request failed: {e}",
                model=model,
                endpoint=self.base_url,
            ) from e

    def _process_stream_event(
        self,
        event: dict[str, Any],
        model: str,
        pending_tool_calls: dict[int, dict[str, Any]],
    ) -> StreamChunk | None:
        """Process a single SSE event from Anthropic's streaming API.

        Handles text deltas, tool use block assembly via input_json_delta,
        thinking blocks, and message-level events.
        """
        event_type = event.get("type", "")

        if event_type == "content_block_start":
            index = event.get("index", 0)
            content_block = event.get("content_block", {})
            block_type = content_block.get("type")

            if block_type == "tool_use":
                pending_tool_calls[index] = {
                    "id": content_block.get("id", ""),
                    "name": content_block.get("name", ""),
                    "arguments_json": "",
                }
            elif block_type == "thinking":
                return StreamChunk(
                    raw_delta={"thinking_start": True},
                    model=model,
                )
            return None

        if event_type == "content_block_delta":
            index = event.get("index", 0)
            delta = event.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta":
                return StreamChunk(content=delta.get("text", ""), model=model)

            if delta_type == "input_json_delta":
                partial_json = delta.get("partial_json", "")
                if index in pending_tool_calls:
                    pending_tool_calls[index]["arguments_json"] += partial_json
                return None

            if delta_type == "thinking_delta":
                thinking_text = delta.get("thinking", "")
                return StreamChunk(
                    raw_delta={"reasoning_content": thinking_text},
                    model=model,
                )

            return None

        if event_type == "content_block_stop":
            index = event.get("index", 0)
            if index in pending_tool_calls:
                tc_data = pending_tool_calls.pop(index)
                tool_call_delta = [
                    {
                        "index": index,
                        "id": tc_data["id"],
                        "type": "function",
                        "function": {
                            "name": tc_data["name"],
                            "arguments": tc_data["arguments_json"],
                        },
                    }
                ]
                return StreamChunk(
                    tool_calls_delta=tool_call_delta,
                    model=model,
                )
            return None

        if event_type == "message_delta":
            delta = event.get("delta", {})
            stop_reason = delta.get("stop_reason")
            usage_data = event.get("usage", {})
            usage = None
            if usage_data:
                usage = TokenUsage(
                    prompt_tokens=0,
                    completion_tokens=usage_data.get("output_tokens", 0),
                    total_tokens=usage_data.get("output_tokens", 0),
                )
            if stop_reason:
                finish_reason = "stop"
                if stop_reason == "tool_use":
                    finish_reason = "tool_calls"
                elif stop_reason == "max_tokens":
                    finish_reason = "length"
                return StreamChunk(
                    finish_reason=finish_reason,
                    model=model,
                    usage=usage,
                )
            return None

        if event_type == "message_start":
            message = event.get("message", {})
            usage_data = message.get("usage", {})
            if usage_data:
                usage = TokenUsage(
                    prompt_tokens=usage_data.get("input_tokens", 0),
                    completion_tokens=usage_data.get("output_tokens", 0),
                    total_tokens=(
                        usage_data.get("input_tokens", 0)
                        + usage_data.get("output_tokens", 0)
                    ),
                )
                return StreamChunk(usage=usage, model=model)
            return None

        return None

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        raise NotImplementedError("Anthropic does not support embeddings")
