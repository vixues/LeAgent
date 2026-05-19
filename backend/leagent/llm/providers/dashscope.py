"""DashScope (Alibaba Cloud) LLM provider.

Supports Qwen models and other models available on DashScope.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

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


class DashScopeProvider(LLMProvider):
    """DashScope provider for Alibaba Cloud's LLM services.

    Supports:
    - Qwen series (qwen-turbo, qwen-plus, qwen-max, qwen2.5-72b-instruct, etc.)
    - Text embedding models
    - Function calling
    """

    name = "dashscope"
    supports_streaming = True
    supports_tools = True
    supports_embeddings = True

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        api_key: str,
        default_model: str = "qwen-plus",
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries

    def _get_default_model(self) -> str:
        return self.default_model

    def _get_headers(self, stream: bool = False) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if stream:
            headers["X-DashScope-SSE"] = "enable"
        return headers

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert to DashScope message format."""
        result = []
        for msg in messages:
            ds_msg: dict[str, Any] = {"role": msg.role.value}
            if msg.content is not None:
                ds_msg["content"] = msg.content
            if msg.name:
                ds_msg["name"] = msg.name
            if msg.tool_calls:
                ds_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                ds_msg["tool_call_id"] = msg.tool_call_id
            result.append(ds_msg)
        return result

    def _build_tools(self, tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
        """Convert tools to DashScope format."""
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _parse_response(self, data: dict[str, Any], model: str) -> LLMResponse:
        """Parse DashScope response."""
        output = data.get("output", {})
        choices = output.get("choices", [{}])
        choice = choices[0] if choices else {}
        message = choice.get("message", {})

        tool_calls: list[ToolCall] = []
        if raw_tool_calls := message.get("tool_calls"):
            for tc in raw_tool_calls:
                func = tc.get("function", {})
                tool_calls.append(
                    ToolCall(
                        id=tc.get("id", ""),
                        name=func.get("name", ""),
                        arguments=func.get("arguments", "{}"),
                    )
                )

        usage_data = data.get("usage", {})
        usage = TokenUsage(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            model=output.get("model", model),
            usage=usage,
            raw_response=data,
        )

    def _handle_error(
        self,
        status_code: int,
        response_body: dict[str, Any] | str,
        model: str,
    ) -> None:
        """Map DashScope errors to exceptions."""
        error_msg = ""
        error_code = ""

        if isinstance(response_body, dict):
            error_code = response_body.get("code", "")
            error_msg = response_body.get("message", str(response_body))
        else:
            error_msg = response_body

        if status_code == 401 or error_code == "InvalidApiKey":
            raise LLMServiceError(
                "Invalid DashScope API key",
                model=model,
                endpoint=self.BASE_URL,
            )

        if error_code == "ModelNotFound" or status_code == 404:
            raise ModelNotFoundError(model)

        if status_code == 429 or error_code in ("RateLimitExceeded", "QuotaExceeded"):
            raise LLMRateLimitError(model=model)

        if status_code >= 500:
            raise LLMServiceError(
                f"DashScope server error: {error_msg}",
                model=model,
                endpoint=self.BASE_URL,
            )

        raise LLMServiceError(
            f"DashScope API error ({error_code}): {error_msg}",
            model=model,
            endpoint=self.BASE_URL,
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
        body: dict[str, Any] = {
            "model": model,
            "input": {
                "messages": self._build_messages(messages),
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "result_format": "message",
            },
        }

        if tools:
            body["input"]["tools"] = self._build_tools(tools)
            if tool_choice:
                body["parameters"]["tool_choice"] = tool_choice

        if stop:
            body["parameters"]["stop"] = stop

        # Add any extra parameters
        if kwargs.get("top_p"):
            body["parameters"]["top_p"] = kwargs["top_p"]
        if kwargs.get("seed"):
            body["parameters"]["seed"] = kwargs["seed"]
        if kwargs.get("enable_search"):
            body["parameters"]["enable_search"] = kwargs["enable_search"]

        url = f"{self.BASE_URL}/services/aigc/text-generation/generation"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=httpx_trust_env()) as client:
                    response = await client.post(
                        url,
                        headers=self._get_headers(),
                        json=body,
                    )

                if response.status_code == 200:
                    data = response.json()
                    # DashScope returns errors in JSON body even with 200 status
                    if data.get("code") and data.get("code") != "200":
                        self._handle_error(200, data, model)
                    return self._parse_response(data, model)

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
                    endpoint=self.BASE_URL,
                ) from e

        raise LLMServiceError(
            f"Max retries exceeded: {last_error}",
            model=model,
            endpoint=self.BASE_URL,
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
        body: dict[str, Any] = {
            "model": model,
            "input": {
                "messages": self._build_messages(messages),
            },
            "parameters": {
                "temperature": temperature,
                "max_tokens": max_tokens,
                "result_format": "message",
                "incremental_output": True,
            },
        }

        if tools:
            body["input"]["tools"] = self._build_tools(tools)
            if tool_choice:
                body["parameters"]["tool_choice"] = tool_choice

        if stop:
            body["parameters"]["stop"] = stop

        if kwargs.get("top_p"):
            body["parameters"]["top_p"] = kwargs["top_p"]

        url = f"{self.BASE_URL}/services/aigc/text-generation/generation"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=httpx_trust_env()) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=self._get_headers(stream=True),
                    json=body,
                ) as response:
                    if response.status_code != 200:
                        content = await response.aread()
                        try:
                            error_body = json.loads(content)
                        except json.JSONDecodeError:
                            error_body = content.decode()
                        self._handle_error(response.status_code, error_body, model)

                    async for line in response.aiter_lines():
                        if not line or line.startswith(":"):
                            continue

                        # DashScope uses "data:" prefix for SSE
                        if line.startswith("data:"):
                            data_str = line[5:].strip()
                            if not data_str:
                                continue

                            try:
                                data = json.loads(data_str)

                                # Check for errors in stream
                                if data.get("code") and data.get("code") != "200":
                                    self._handle_error(200, data, model)

                                chunk = self._parse_stream_chunk(data, model)
                                yield chunk

                            except json.JSONDecodeError:
                                continue

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(model=model, timeout_sec=int(self.timeout)) from e
        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Stream request failed: {e}",
                model=model,
                endpoint=self.BASE_URL,
            ) from e

    def _parse_stream_chunk(self, data: dict[str, Any], model: str) -> StreamChunk:
        """Parse a streaming chunk from DashScope."""
        output = data.get("output", {})
        choices = output.get("choices", [{}])
        choice = choices[0] if choices else {}
        message = choice.get("message", {})

        tool_calls_delta: list[dict[str, Any]] = []
        if raw_tc := message.get("tool_calls"):
            tool_calls_delta = raw_tc

        return StreamChunk(
            content=message.get("content", ""),
            tool_calls_delta=tool_calls_delta,
            finish_reason=choice.get("finish_reason"),
            model=output.get("model", model),
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """Generate embeddings using DashScope embedding models."""
        embed_model = model or "text-embedding-v2"

        body: dict[str, Any] = {
            "model": embed_model,
            "input": {
                "texts": texts,
            },
            "parameters": {
                "text_type": kwargs.get("text_type", "document"),
            },
        }

        url = f"{self.BASE_URL}/services/embeddings/text-embedding/text-embedding"

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

            # Check for errors in response body
            if data.get("code") and data.get("code") != "200":
                self._handle_error(200, data, embed_model)

            output = data.get("output", {})
            embeddings_data = output.get("embeddings", [])

            # Sort by text_index to maintain order
            sorted_data = sorted(embeddings_data, key=lambda x: x.get("text_index", 0))
            embeddings = [item["embedding"] for item in sorted_data]

            usage_data = data.get("usage", {})
            usage = TokenUsage(
                prompt_tokens=usage_data.get("total_tokens", 0),
                completion_tokens=0,
                total_tokens=usage_data.get("total_tokens", 0),
            )

            return EmbeddingResponse(
                embeddings=embeddings,
                model=embed_model,
                usage=usage,
            )

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(model=embed_model, timeout_sec=int(self.timeout)) from e
        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Embedding request failed: {e}",
                model=embed_model,
                endpoint=self.BASE_URL,
            ) from e
