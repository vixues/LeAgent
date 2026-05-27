"""OpenAI-compatible LLM provider.

Supports OpenAI API and any OpenAI-compatible endpoints (vLLM, Together, etc.).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, AsyncIterator, Literal

import httpx

from leagent.utils.httpx_proxy import httpx_trust_env

from leagent.exceptions.llm import (
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    ModelNotFoundError,
)
from leagent.llm.base import (
    ChatMessage,
    EmbeddingResponse,
    LLMProvider,
    LLMResponse,
    StreamChunk,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)

# Streaming uses infinite read timeout; connect/write stay bounded.
_STREAM_HTTPX_TIMEOUT = httpx.Timeout(connect=30.0, read=None, write=60.0, pool=10.0)
_STREAM_HTTPX_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20, keepalive_expiry=60.0)

if TYPE_CHECKING:
    from collections.abc import Mapping

# OpenAI-compatible gateways use different field names for chain-of-thought text.
_REASONING_DELTA_KEYS = ("reasoning_content", "thinking", "reasoning")
_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_CONTEXT_WINDOW_RE = re.compile(r"maximum context length is\s+(\d+)", re.IGNORECASE)
_REQUESTED_OUTPUT_RE = re.compile(r"requested\s+(\d+)\s+output tokens", re.IGNORECASE)
_PROMPT_INPUT_RE = re.compile(r"prompt contains at least\s+(\d+)\s+input tokens", re.IGNORECASE)


def _extract_reasoning_text(payload: dict[str, Any]) -> str | None:
    """Return the first non-empty reasoning/thinking string from *payload*."""
    for key in _REASONING_DELTA_KEYS:
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def _context_retry_max_tokens(response_body: dict[str, Any] | str, current: int) -> int | None:
    """Return a smaller max_tokens from OpenAI-compatible context-window errors."""
    if current <= 256:
        return None
    if isinstance(response_body, dict):
        error_obj = response_body.get("error", {})
        message = error_obj.get("message", str(response_body))
    else:
        message = response_body
    if not isinstance(message, str):
        return None
    max_match = _CONTEXT_WINDOW_RE.search(message)
    prompt_match = _PROMPT_INPUT_RE.search(message)
    if not max_match or not prompt_match:
        return None
    context_window = int(max_match.group(1))
    prompt_tokens = int(prompt_match.group(1))
    requested_match = _REQUESTED_OUTPUT_RE.search(message)
    requested = int(requested_match.group(1)) if requested_match else current
    margin = min(1024, max(128, context_window // 512))
    available = context_window - prompt_tokens - margin
    if available < 256:
        available = max(256, context_window - prompt_tokens)
    next_max = min(current, requested, available)
    return next_max if 0 < next_max < current else None


def _split_complete_think_tags(content: str | None) -> tuple[str | None, str | None]:
    """Extract ``<think>...</think>`` blocks from non-streaming content."""
    if not content or _THINK_OPEN not in content:
        return content, None
    visible: list[str] = []
    reasoning: list[str] = []
    in_think = False
    i = 0
    while i < len(content):
        tag = _THINK_CLOSE if in_think else _THINK_OPEN
        idx = content.find(tag, i)
        if idx < 0:
            (reasoning if in_think else visible).append(content[i:])
            break
        if idx > i:
            (reasoning if in_think else visible).append(content[i:idx])
        in_think = not in_think
        i = idx + len(tag)
    thought = "".join(reasoning).strip()
    return "".join(visible).lstrip(), thought or None


def _split_stream_think_tags(
    content: str,
    *,
    in_think: bool,
    pending: str,
) -> tuple[list[tuple[str, str]], bool, str]:
    """Split streamed content into visible/thinking parts, preserving partial tags."""
    text = pending + content
    pending = ""
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(text):
        tag = _THINK_CLOSE if in_think else _THINK_OPEN
        idx = text.find(tag, i)
        if idx >= 0:
            if idx > i:
                out.append(("thinking" if in_think else "content", text[i:idx]))
            in_think = not in_think
            i = idx + len(tag)
            continue

        max_keep = min(len(tag) - 1, len(text) - i)
        keep = 0
        for n in range(max_keep, 0, -1):
            if tag.startswith(text[len(text) - n :]):
                keep = n
                break
        emit_end = len(text) - keep
        if emit_end > i:
            out.append(("thinking" if in_think else "content", text[i:emit_end]))
        pending = text[emit_end:]
        break
    return out, in_think, pending


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider.

    Works with:
    - OpenAI API (api.openai.com)
    - Azure OpenAI
    - vLLM OpenAI-compatible server
    - Together AI
    - Any OpenAI-compatible endpoint

    Supports structured outputs via ``response_format`` (json_schema with
    strict mode) and reasoning models via ``reasoning_effort``.
    """

    name = "openai"
    supports_streaming = True
    supports_tools = True
    supports_embeddings = True
    supports_structured_output = True
    supports_vision = True

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o",
        timeout: float = 120.0,
        max_retries: int = 2,
        organization: str | None = None,
        default_headers: Mapping[str, str] | None = None,
        parse_think_tags: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.organization = organization
        self.parse_think_tags = parse_think_tags
        self._extra_headers = dict(default_headers) if default_headers else {}
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
        """Release pooled HTTP connections (optional lifecycle hook)."""
        for client in (self._http_complete_client, self._http_stream_client):
            if client is not None:
                await client.aclose()
        self._http_complete_client = None
        self._http_stream_client = None

    def _get_default_model(self) -> str:
        return self.default_model

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.organization:
            headers["OpenAI-Organization"] = self.organization
        return headers

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
        body: dict[str, Any] = {
            "model": model,
            "messages": [m.to_openai_format() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            body["tools"] = [t.to_openai_format() for t in tools]
            if tool_choice:
                if tool_choice in ("auto", "none", "required"):
                    body["tool_choice"] = tool_choice
                else:
                    body["tool_choice"] = {
                        "type": "function",
                        "function": {"name": tool_choice},
                    }

        if stop:
            body["stop"] = stop

        if stream:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}

        # Structured outputs via response_format (json_schema with strict mode)
        response_format = kwargs.pop("response_format", None)
        if response_format:
            body["response_format"] = response_format

        # Reasoning effort for o-series and GPT-5.x reasoning models
        reasoning_effort = kwargs.pop("reasoning_effort", None)
        if reasoning_effort:
            body["reasoning_effort"] = reasoning_effort

        body.update(kwargs)
        return body

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})

        tool_calls: list[ToolCall] = []
        if raw_tool_calls := message.get("tool_calls"):
            for tc in raw_tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc["id"],
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    )
                )

        usage = self._usage_from_response_payload(data) or TokenUsage()
        reasoning_content = _extract_reasoning_text(message)
        content = message.get("content")
        if self.parse_think_tags:
            content, tagged_reasoning = _split_complete_think_tags(content)
            if tagged_reasoning:
                reasoning_content = (
                    f"{reasoning_content}\n{tagged_reasoning}".strip()
                    if reasoning_content
                    else tagged_reasoning
                )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            model=data.get("model", ""),
            usage=usage,
            raw_response=data,
            reasoning_content=reasoning_content,
        )

    def _handle_error(
        self,
        status_code: int,
        response_body: dict[str, Any] | str,
        model: str,
    ) -> None:
        """Map HTTP errors to appropriate exceptions."""
        error_msg = ""
        if isinstance(response_body, dict):
            error_obj = response_body.get("error", {})
            error_msg = error_obj.get("message", str(response_body))
        else:
            error_msg = response_body

        if status_code == 401:
            raise LLMServiceError(
                "Invalid API key or authentication failed",
                model=model,
                endpoint=self.base_url,
            )
        if status_code == 404:
            raise ModelNotFoundError(model)
        if status_code == 429:
            retry_after = None
            if isinstance(response_body, dict):
                retry_after = response_body.get("error", {}).get("retry_after")
            raise LLMRateLimitError(model=model, retry_after=retry_after)
        if status_code >= 500:
            raise LLMServiceError(
                f"Server error: {error_msg}",
                model=model,
                endpoint=self.base_url,
            )

        raise LLMServiceError(
            f"API error ({status_code}): {error_msg}",
            model=model,
            endpoint=self.base_url,
        )

    @staticmethod
    def _usage_from_response_payload(data: dict[str, Any]) -> TokenUsage | None:
        raw = data.get("usage")
        if not isinstance(raw, dict) or not raw:
            return None
        completion_detail = raw.get("completion_tokens_details") or {}
        prompt_detail = raw.get("prompt_tokens_details") or {}
        cached_alt = 0
        if isinstance(prompt_detail, dict):
            cached_alt = int(prompt_detail.get("cached_tokens", 0) or 0)
        hit = int(raw.get("prompt_cache_hit_tokens", 0) or 0) or cached_alt
        miss = int(raw.get("prompt_cache_miss_tokens", 0) or 0)
        return TokenUsage(
            prompt_tokens=int(raw.get("prompt_tokens", 0)),
            completion_tokens=int(raw.get("completion_tokens", 0)),
            total_tokens=int(raw.get("total_tokens", 0)),
            reasoning_tokens=int(completion_detail.get("reasoning_tokens", 0)),
            prompt_cache_hit_tokens=hit,
            prompt_cache_miss_tokens=miss,
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
            **kwargs,
        )

        url = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                client = self._ensure_complete_client()
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=body,
                )

                if response.status_code == 200:
                    return self._parse_response(response.json())

                try:
                    error_body = response.json()
                except json.JSONDecodeError:
                    error_body = response.text

                retry_max = _context_retry_max_tokens(error_body, int(body.get("max_tokens", max_tokens) or max_tokens))
                if retry_max is not None and attempt < self.max_retries:
                    body = {**body, "max_tokens": retry_max}
                    continue

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

        url = f"{self.base_url}/chat/completions"

        in_think = False
        pending_think_tag = ""
        for context_attempt in range(3):
            try:
                client = self._ensure_stream_client()
                async with client.stream(
                    "POST",
                    url,
                    headers=self._get_headers(),
                    json=body,
                ) as response:
                    if response.status_code != 200:
                        content = await response.aread()
                        try:
                            error_body = json.loads(content)
                        except json.JSONDecodeError:
                            error_body = content.decode()
                        retry_max = _context_retry_max_tokens(
                            error_body,
                            int(body.get("max_tokens", max_tokens) or max_tokens),
                        )
                        if retry_max is not None and context_attempt < 2:
                            body = {**body, "max_tokens": retry_max}
                            continue
                        self._handle_error(response.status_code, error_body, model)

                    line_buf = b""
                    async for piece in response.aiter_bytes():
                        line_buf += piece
                        while True:
                            nl = line_buf.find(b"\n")
                            if nl < 0:
                                break
                            raw_line = line_buf[:nl]
                            line_buf = line_buf[nl + 1 :]
                            line = raw_line.decode("utf-8", errors="replace").rstrip("\r")
                            if not line or line.startswith(":"):
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    if pending_think_tag:
                                        yield StreamChunk(
                                            content="" if in_think else pending_think_tag,
                                            raw_delta={"reasoning_content": pending_think_tag} if in_think else None,
                                            model=model,
                                        )
                                    return
                                try:
                                    data = json.loads(data_str)
                                except json.JSONDecodeError:
                                    continue
                                chunk = self._parse_stream_chunk(data, model)
                                if not self.parse_think_tags:
                                    yield chunk
                                    continue
                                async for split_chunk in self._split_think_chunk(
                                    chunk,
                                    in_think=in_think,
                                    pending=pending_think_tag,
                                ):
                                    in_think = bool(split_chunk.raw_delta and split_chunk.raw_delta.get("__in_think"))
                                    pending_think_tag = str(
                                        (split_chunk.raw_delta or {}).get("__pending_think_tag", "")
                                    )
                                    clean_raw = dict(split_chunk.raw_delta or {})
                                    clean_raw.pop("__in_think", None)
                                    clean_raw.pop("__pending_think_tag", None)
                                    split_chunk.raw_delta = clean_raw or None
                                    yield split_chunk
                    if self.parse_think_tags and pending_think_tag:
                        yield StreamChunk(
                            content="" if in_think else pending_think_tag,
                            raw_delta={"reasoning_content": pending_think_tag} if in_think else None,
                            model=model,
                        )
                    return

            except httpx.TimeoutException as e:
                raise LLMTimeoutError(model=model, timeout_sec=int(self.timeout)) from e
            except httpx.RequestError as e:
                # Some proxy/TLS errors have an empty str(e); keep type+repr for diagnostics.
                detail = str(e) or repr(e)
                raise LLMServiceError(
                    f"Stream request failed ({type(e).__name__}): {detail}",
                    model=model,
                    endpoint=self.base_url,
                ) from e

    async def _split_think_chunk(
        self,
        chunk: StreamChunk,
        *,
        in_think: bool,
        pending: str,
    ) -> AsyncIterator[StreamChunk]:
        """Convert ``<think>`` tags in content deltas to reasoning deltas.

        Some local OpenAI-compatible servers expose thinking as literal tags in
        ``delta.content`` instead of a provider-specific ``reasoning_content``
        field. Keep the UI-facing content clean while preserving the reasoning
        stream for persistence and the thinking panel.
        """
        state_raw = {
            "__in_think": in_think,
            "__pending_think_tag": pending,
        }
        if not chunk.content:
            raw_delta = {**(chunk.raw_delta or {}), **state_raw}
            yield StreamChunk(
                content=chunk.content,
                tool_calls_delta=chunk.tool_calls_delta,
                finish_reason=chunk.finish_reason,
                model=chunk.model,
                raw_delta=raw_delta,
                usage=chunk.usage,
            )
            return

        pieces, next_in_think, next_pending = _split_stream_think_tags(
            chunk.content,
            in_think=in_think,
            pending=pending,
        )
        state_raw = {
            "__in_think": next_in_think,
            "__pending_think_tag": next_pending,
        }
        if not pieces:
            raw_delta = {**(chunk.raw_delta or {}), **state_raw}
            yield StreamChunk(
                content="",
                tool_calls_delta=chunk.tool_calls_delta,
                finish_reason=chunk.finish_reason,
                model=chunk.model,
                raw_delta=raw_delta,
                usage=chunk.usage,
            )
            return

        last_idx = len(pieces) - 1
        for idx, (kind, text) in enumerate(pieces):
            is_last = idx == last_idx
            raw_delta: dict[str, Any] = dict(chunk.raw_delta or {}) if is_last else {}
            if kind == "thinking":
                raw_delta["reasoning_content"] = (
                    f"{raw_delta.get('reasoning_content', '')}{text}"
                    if raw_delta.get("reasoning_content")
                    else text
                )
            raw_delta.update(state_raw)
            yield StreamChunk(
                content=text if kind == "content" else "",
                tool_calls_delta=chunk.tool_calls_delta if is_last else [],
                finish_reason=chunk.finish_reason if is_last else None,
                model=chunk.model,
                raw_delta=raw_delta,
                usage=chunk.usage if is_last else None,
            )

    def _parse_stream_chunk(self, data: dict[str, Any], model: str) -> StreamChunk:
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        delta = choice.get("delta", {}) or {}

        tool_calls_delta: list[dict[str, Any]] = []
        if raw_tc := delta.get("tool_calls"):
            tool_calls_delta = raw_tc

        raw_delta: dict[str, Any] | None = None
        reasoning = _extract_reasoning_text(delta)
        if reasoning is not None:
            raw_delta = {"reasoning_content": reasoning}

        content_val = delta.get("content")
        content = "" if content_val is None else str(content_val)

        return StreamChunk(
            content=content,
            tool_calls_delta=tool_calls_delta,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model", model),
            raw_delta=raw_delta,
            usage=self._usage_from_response_payload(data),
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        embed_model = model or "text-embedding-3-small"

        body: dict[str, Any] = {
            "model": embed_model,
            "input": texts,
            **kwargs,
        }

        url = f"{self.base_url}/embeddings"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=httpx_trust_env()) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=body,
                )

            if response.status_code != 200:
                try:
                    error_body = response.json()
                except json.JSONDecodeError:
                    error_body = response.text
                self._handle_error(response.status_code, error_body, embed_model)

            data = response.json()
            embeddings = [item["embedding"] for item in data.get("data", [])]

            usage_data = data.get("usage", {})
            usage = TokenUsage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=0,
                total_tokens=usage_data.get("total_tokens", 0),
            )

            return EmbeddingResponse(
                embeddings=embeddings,
                model=data.get("model", embed_model),
                usage=usage,
            )

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(model=embed_model, timeout_sec=int(self.timeout)) from e
        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Embedding request failed: {e}",
                model=embed_model,
                endpoint=self.base_url,
            ) from e
