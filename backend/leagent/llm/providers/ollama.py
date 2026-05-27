"""Ollama LLM provider for local model inference.

Supports Ollama's native ``/api/chat`` endpoint with:

- Streaming (NDJSON) and non-streaming completions
- Tool/function calling (Ollama 0.3+)
- Structured output via ``format`` (JSON schema or ``json``)
- Thinking models via ``think`` parameter
- Vision (base64 images in messages)
- Model management (list, pull)
- Embeddings
"""

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


def _arguments_to_ollama_object(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"__raw__": raw}
    return parsed if isinstance(parsed, dict) else {}


def _arguments_to_json_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "{}"
    return json.dumps(value, ensure_ascii=False)


def _normalize_tool_call_delta(tc: dict[str, Any], index: int) -> dict[str, Any]:
    normalized = dict(tc)
    normalized.setdefault("index", index)
    fn = normalized.get("function")
    if isinstance(fn, dict):
        normalized_fn = dict(fn)
        if "arguments" in normalized_fn:
            normalized_fn["arguments"] = _arguments_to_json_string(
                normalized_fn.get("arguments"),
            )
        normalized["function"] = normalized_fn
    return normalized


class OllamaProvider(LLMProvider):
    """Ollama provider for local model inference.

    Ollama runs models locally and provides an HTTP API.
    Supports most open-source models like Llama, Mistral, Qwen, etc.
    """

    name = "ollama"
    supports_streaming = True
    supports_tools = True
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
        self._http_complete_client: httpx.AsyncClient | None = None
        self._http_stream_client: httpx.AsyncClient | None = None
        self._http_management_client: httpx.AsyncClient | None = None
        self._http_pull_client: httpx.AsyncClient | None = None

    def _get_default_model(self) -> str:
        return self.default_model

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
                timeout=self.timeout,
                trust_env=httpx_trust_env(),
            )
        return self._http_stream_client

    def _ensure_management_client(self) -> httpx.AsyncClient:
        if self._http_management_client is None:
            self._http_management_client = httpx.AsyncClient(
                timeout=30.0,
                trust_env=httpx_trust_env(),
            )
        return self._http_management_client

    def _ensure_pull_client(self) -> httpx.AsyncClient:
        if self._http_pull_client is None:
            self._http_pull_client = httpx.AsyncClient(
                timeout=3600.0,
                trust_env=httpx_trust_env(),
            )
        return self._http_pull_client

    async def aclose(self) -> None:
        """Release pooled HTTP connections."""
        for client in (
            self._http_complete_client,
            self._http_stream_client,
            self._http_management_client,
            self._http_pull_client,
        ):
            if client is not None:
                await client.aclose()
        self._http_complete_client = None
        self._http_stream_client = None
        self._http_management_client = None
        self._http_pull_client = None

    @staticmethod
    def _is_embedding_model(name: str) -> bool:
        lowered = name.lower()
        return "embed" in lowered

    @staticmethod
    def _model_matches(requested: str, installed: str) -> bool:
        """Return True when *installed* satisfies a configured *requested* id."""
        req = requested.strip()
        ins = installed.strip()
        if not req or not ins:
            return False
        if req == ins:
            return True
        if ins.startswith(req + ":"):
            return True
        req_base = req.split(":", 1)[0]
        ins_base = ins.split(":", 1)[0]
        return req_base == ins_base

    @classmethod
    def pick_test_model(
        cls,
        installed: list[str],
        *,
        preferred: str | None = None,
        configured: list[str] | None = None,
        default_model: str | None = None,
    ) -> str | None:
        """Choose a locally installed model for connectivity probes."""
        chat_models = [m for m in installed if m and not cls._is_embedding_model(m)]
        pool = chat_models or [m for m in installed if m]
        if not pool:
            return None

        def find_match(name: str) -> str | None:
            for available in pool:
                if cls._model_matches(name, available):
                    return available
            return None

        for candidate in (preferred, *(configured or []), default_model):
            if not candidate:
                continue
            hit = find_match(candidate)
            if hit:
                return hit
        return sorted(pool)[0]

    async def get_installed_model_names(self) -> list[str]:
        """Return model names reported by Ollama ``/api/tags``."""
        raw = await self.list_models()
        return [
            str(item.get("name") or "")
            for item in raw
            if isinstance(item, dict) and item.get("name")
        ]

    async def resolve_test_model(
        self,
        *,
        preferred: str | None = None,
        configured: list[str] | None = None,
    ) -> str:
        """Resolve a model id that exists locally for health / connection tests."""
        installed = await self.get_installed_model_names()
        picked = self.pick_test_model(
            installed,
            preferred=preferred,
            configured=configured,
            default_model=self.default_model,
        )
        if not picked:
            missing = preferred or self.default_model or "ollama"
            raise ModelNotFoundError(missing)
        return picked

    async def health_check(self) -> bool:
        """Verify Ollama is reachable and at least one chat model can respond."""
        try:
            test_model = await self.resolve_test_model()
        except Exception:
            return False
        try:
            response = await self.complete(
                messages=[ChatMessage.user("ping")],
                model=test_model,
                max_tokens=5,
            )
            return response.content is not None
        except Exception:
            return False

    def _build_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert ChatMessage list to Ollama message format.

        Handles vision content (images as base64) and tool result messages
        with the ``tool_name`` field.
        """
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
                            "arguments": _arguments_to_ollama_object(tc.arguments),
                        }
                    }
                    for tc in msg.tool_calls
                ]
            # Pass tool_name for tool-result messages so the model knows
            # which tool produced the result
            if msg.role.value == "tool" and msg.tool_call_id:
                ollama_msg["tool_name"] = msg.tool_call_id
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
                        arguments=_arguments_to_json_string(func.get("arguments")),
                    )
                )

        usage = TokenUsage(
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            total_tokens=data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        )

        finish_reason = "stop"
        if data.get("done_reason"):
            finish_reason = data["done_reason"]

        # Extract thinking content from thinking models
        reasoning_content: str | None = None
        thinking = message.get("thinking")
        if isinstance(thinking, str) and thinking.strip():
            reasoning_content = thinking

        return LLMResponse(
            content=message.get("content"),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            model=data.get("model", model),
            usage=usage,
            raw_response=data,
            reasoning_content=reasoning_content,
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

        # Structured output: JSON schema or "json" format
        fmt = kwargs.pop("format", None)
        if fmt:
            body["format"] = fmt

        # Thinking models: enable chain-of-thought reasoning
        think = kwargs.pop("think", None)
        if think is not None:
            body["think"] = think

        # Keep-alive duration for model in memory
        keep_alive = kwargs.pop("keep_alive", None)
        if keep_alive is not None:
            body["keep_alive"] = keep_alive

        # Pass through any additional options
        if kwargs.get("options"):
            body["options"].update(kwargs.pop("options"))

        url = f"{self.base_url}/api/chat"
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                client = self._ensure_complete_client()
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

        fmt = kwargs.pop("format", None)
        if fmt:
            body["format"] = fmt

        think = kwargs.pop("think", None)
        if think is not None:
            body["think"] = think

        keep_alive = kwargs.pop("keep_alive", None)
        if keep_alive is not None:
            body["keep_alive"] = keep_alive

        if kwargs.get("options"):
            body["options"].update(kwargs.pop("options"))

        url = f"{self.base_url}/api/chat"

        try:
            client = self._ensure_stream_client()
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
            for i, tc in enumerate(raw_tc):
                if not isinstance(tc, dict):
                    continue
                tool_calls_delta.append(_normalize_tool_call_delta(tc, i))

        finish_reason = None
        if data.get("done"):
            finish_reason = data.get("done_reason", "stop")

        # Extract thinking content in stream
        raw_delta: dict[str, Any] | None = None
        thinking = message.get("thinking")
        if isinstance(thinking, str) and thinking:
            raw_delta = {"reasoning_content": thinking}

        return StreamChunk(
            content=message.get("content", ""),
            tool_calls_delta=tool_calls_delta,
            finish_reason=finish_reason,
            model=data.get("model", model),
            raw_delta=raw_delta,
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
        if not texts:
            return EmbeddingResponse(
                embeddings=[],
                model=embed_model,
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            )

        url = f"{self.base_url}/api/embed"

        try:
            client = self._ensure_complete_client()
            response = await client.post(
                url,
                json={
                    "model": embed_model,
                    "input": texts,
                },
            )

            if response.status_code != 200:
                self._handle_error(response.status_code, response.text, embed_model)

            data = response.json()
            raw_embeddings = data.get("embeddings", [])
            embeddings = [
                emb if isinstance(emb, list) else []
                for emb in raw_embeddings
            ]
            total_prompt_tokens = int(data.get("prompt_eval_count", 0) or 0)

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
            client = self._ensure_management_client()
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
            client = self._ensure_pull_client()
            async with client.stream("POST", url, json={"name": model}) as response:
                if response.status_code != 200:
                    content = await response.aread()
                    raise LLMServiceError(
                        f"Failed to pull model: {content.decode()}",
                        model=model,
                        endpoint=self.base_url,
                    )
                async for _ in response.aiter_lines():
                    pass

        except httpx.RequestError as e:
            raise LLMServiceError(
                f"Failed to pull model: {e}",
                model=model,
                endpoint=self.base_url,
            ) from e
