"""OpenAI-compatible LLM provider.

Supports OpenAI API and any OpenAI-compatible endpoints (vLLM, Together, etc.).
"""

from __future__ import annotations

import json
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


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider.

    Works with:
    - OpenAI API (api.openai.com)
    - Azure OpenAI
    - vLLM OpenAI-compatible server
    - Together AI
    - Any OpenAI-compatible endpoint
    """

    name = "openai"
    supports_streaming = True
    supports_tools = True
    supports_embeddings = True

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        default_model: str = "gpt-4o",
        timeout: float = 120.0,
        max_retries: int = 2,
        organization: str | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries
        self.organization = organization
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

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            model=data.get("model", ""),
            usage=usage,
            raw_response=data,
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
                                return
                            try:
                                data = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            chunk = self._parse_stream_chunk(data, model)
                            yield chunk

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

    def _parse_stream_chunk(self, data: dict[str, Any], model: str) -> StreamChunk:
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        delta = choice.get("delta", {}) or {}

        tool_calls_delta: list[dict[str, Any]] = []
        if raw_tc := delta.get("tool_calls"):
            tool_calls_delta = raw_tc

        raw_delta: dict[str, Any] | None = None
        if "reasoning_content" in delta and delta["reasoning_content"] is not None:
            raw_delta = {"reasoning_content": delta["reasoning_content"]}

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
