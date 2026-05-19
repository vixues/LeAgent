"""Ollama LLM provider for local model inference."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Literal

import httpx

from leagent.utils.httpx_proxy import httpx_trust_env

from leagent.exceptions.llm import (
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


class OllamaProvider(LLMProvider):
    """Ollama provider for local model inference.

    Ollama runs models locally and provides an HTTP API.
    Supports most open-source models like Llama, Mistral, Qwen, etc.
    """

    name = "ollama"
    supports_streaming = True
    supports_tools = True  # Ollama 0.3+ supports tools
    supports_embeddings = True

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = "llama3.2",
        timeout: float = 300.0,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self.max_retries = max_retries

    def _get_default_model(self) -> str:
        return self.default_model

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert ChatMessage list to Ollama message format."""
        result = []
        for msg in messages:
            ollama_msg: dict[str, Any] = {"role": msg.role.value}
            if msg.content is not None:
                ollama_msg["content"] = msg.content
            if msg.tool_calls:
                ollama_msg["tool_calls"] = [
                    {
                        "function": {
                            "name": tc.name,
                            "arguments": json.loads(tc.arguments) if tc.arguments else {},
                        }
                    }
                    for tc in msg.tool_calls
                ]
            result.append(ollama_msg)
        return result

    def _build_tools(self, tools: list[ToolDefinition] | None) -> list[dict[str, Any]] | None:
        """Convert ToolDefinition list to Ollama tool format."""
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
        """Parse Ollama /api/chat response."""
        message = data.get("message", {})

        tool_calls: list[ToolCall] = []
        if raw_tool_calls := message.get("tool_calls"):
            for i, tc in enumerate(raw_tool_calls):
                func = tc.get("function", {})
                tool_calls.append(
                    ToolCall(
                        id=f"call_{i}",
                        name=func.get("name", ""),
                        arguments=json.dumps(func.get("arguments", {})),
                    )
                )

        # Ollama provides eval_count for completion tokens
        usage = TokenUsage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        )

        finish_reason = "stop"
        if data.get("done_reason"):
            finish_reason = data["done_reason"]

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=data.get("model", model),
            usage=usage,
            raw_response=data,
        )

    def _handle_error(
        self,
        status_code: int,
        response_body: str,
        model: str,
    ) -> None:
        """Map HTTP errors to appropriate exceptions."""
        if status_code == 404:
            if "model" in response_body.lower():
                raise ModelNotFoundError(model)
            raise LLMServiceError(
                f"Not found: {response_body}",
                model=model,
                endpoint=self.base_url,
            )
        if status_code >= 500:
            raise LLMServiceError(
                f"Ollama server error: {response_body}",
                model=model,
                endpoint=self.base_url,
            )
        raise LLMServiceError(
            f"Ollama API error ({status_code}): {response_body}",
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
        body: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(messages),
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if tools:
            body["tools"] = self._build_tools(tools)

        if stop:
            body["options"]["stop"] = stop

        # Pass through any additional options
        if kwargs.get("options"):
            body["options"].update(kwargs["options"])

        url = f"{self.base_url}/api/chat"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=httpx_trust_env()) as client:
                    response = await client.post(url, json=body)

                if response.status_code == 200:
                    return self._parse_response(response.json(), model)

                if attempt < self.max_retries and response.status_code >= 500:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
                    continue

                self._handle_error(response.status_code, response.text, model)

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
        body: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(messages),
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if tools:
            body["tools"] = self._build_tools(tools)

        if stop:
            body["options"]["stop"] = stop

        if kwargs.get("options"):
            body["options"].update(kwargs["options"])

        url = f"{self.base_url}/api/chat"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=httpx_trust_env()) as client:
                async with client.stream("POST", url, json=body) as response:
                    if response.status_code != 200:
                        content = await response.aread()
                        self._handle_error(response.status_code, content.decode(), model)

                    async for line in response.aiter_lines():
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                            chunk = self._parse_stream_chunk(data, model)
                            yield chunk

                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(model=model, timeout_sec=int(self.timeout)) from e
        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Stream request failed: {e}",
                model=model,
                endpoint=self.base_url,
            ) from e

    def _parse_stream_chunk(self, data: dict[str, Any], model: str) -> StreamChunk:
        """Parse a single streaming chunk from Ollama."""
        message = data.get("message", {})

        tool_calls_delta: list[dict[str, Any]] = []
        if raw_tc := message.get("tool_calls"):
            tool_calls_delta = raw_tc

        finish_reason = None
        if data.get("done"):
            finish_reason = data.get("done_reason", "stop")

        return StreamChunk(
            content=message.get("content", ""),
            tool_calls_delta=tool_calls_delta,
            finish_reason=finish_reason,
            model=data.get("model", model),
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """Generate embeddings using Ollama.

        Note: Ollama's embed endpoint processes one text at a time,
        so we batch internally.
        """
        embed_model = model or "nomic-embed-text"

        embeddings: list[list[float]] = []
        total_prompt_tokens = 0

        url = f"{self.base_url}/api/embed"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, trust_env=httpx_trust_env()) as client:
                for text in texts:
                    body = {
                        "model": embed_model,
                        "input": text,
                    }

                    response = await client.post(url, json=body)

                    if response.status_code != 200:
                        self._handle_error(response.status_code, response.text, embed_model)

                    data = response.json()

                    # Ollama returns embeddings as a list (even for single input)
                    embed_data = data.get("embeddings", [[]])[0]
                    embeddings.append(embed_data)

                    total_prompt_tokens += data.get("prompt_eval_count", 0)

        except httpx.TimeoutException as e:
            raise LLMTimeoutError(model=embed_model, timeout_sec=int(self.timeout)) from e
        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Embedding request failed: {e}",
                model=embed_model,
                endpoint=self.base_url,
            ) from e

        return EmbeddingResponse(
            embeddings=embeddings,
            model=embed_model,
            usage=TokenUsage(
                prompt_tokens=total_prompt_tokens,
                completion_tokens=0,
                total_tokens=total_prompt_tokens,
            ),
        )

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models in Ollama."""
        url = f"{self.base_url}/api/tags"

        try:
            async with httpx.AsyncClient(timeout=30.0, trust_env=httpx_trust_env()) as client:
                response = await client.get(url)

            if response.status_code != 200:
                raise LLMServiceError(
                    f"Failed to list models: {response.text}",
                    endpoint=self.base_url,
                )

            data = response.json()
            return data.get("models", [])

        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Failed to list models: {e}",
                endpoint=self.base_url,
            ) from e

    async def pull_model(self, model: str) -> None:
        """Pull a model from the Ollama registry."""
        url = f"{self.base_url}/api/pull"

        try:
            async with httpx.AsyncClient(timeout=3600.0, trust_env=httpx_trust_env()) as client:
                async with client.stream("POST", url, json={"name": model}) as response:
                    if response.status_code != 200:
                        content = await response.aread()
                        raise LLMServiceError(
                            f"Failed to pull model: {content.decode()}",
                            model=model,
                            endpoint=self.base_url,
                        )
                    # Consume the stream to wait for completion
                    async for _ in response.aiter_lines():
                        pass

        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Failed to pull model: {e}",
                model=model,
                endpoint=self.base_url,
            ) from e
