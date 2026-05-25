"""DashScope (Alibaba Cloud) LLM provider.

DashScope exposes an OpenAI-compatible ``/chat/completions`` endpoint so
most of the work is handled by :class:`OpenAIProvider`. This subclass adds:

- Default base URL pinned to DashScope's OpenAI-compatible endpoint.
- ``enable_thinking`` injection for Qwen3 thinking models, configurable
  via settings and per-request overrides.
- ``reasoning_content`` extraction for both streaming and non-streaming
  responses (Qwen3 thinking mode), surfaced via ``StreamChunk.raw_delta``
  / ``LLMResponse.reasoning_content``.
- Settings-driven ``enable_search`` injection.
- ``thinking_budget``, ``preserve_thinking`` forwarding in request body.
- Cache metrics logging from ``prompt_tokens_details.cached_tokens``.
- Diagnostic error handling for DashScope-specific 400 errors.

The ``name`` attribute stays ``"dashscope"`` so the registry can route by
provider type.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from leagent.llm.base import (
    ChatMessage,
    EmbeddingResponse,
    LLMResponse,
    StreamChunk,
    TokenUsage,
    ToolDefinition,
)
from leagent.llm.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)

_THINKING_CAPABLE_PREFIXES = (
    "qwen3",
    "qwq",
)

_DASHSCOPE_EXTRA_BODY_KEYS = frozenset({
    "enable_thinking",
    "enable_search",
    "thinking_budget",
    "preserve_thinking",
    "search_options",
    "enable_code_interpreter",
    "top_k",
    "repetition_penalty",
    "skill",
    "vl_high_resolution_images",
})


class DashScopeProvider(OpenAIProvider):
    """OpenAI-compatible provider for Alibaba Cloud DashScope (Qwen models).

    Uses the OpenAI-compatible endpoint at
    ``https://dashscope.aliyuncs.com/compatible-mode/v1``.
    """

    name = "dashscope"
    supports_streaming = True
    supports_tools = True
    supports_embeddings = True

    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL = "qwen-plus"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        default_model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        max_retries: int = 2,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            default_model=default_model or self.DEFAULT_MODEL,
            timeout=timeout,
            max_retries=max_retries,
        )

    # ------------------------------------------------------------------
    # Settings merge
    # ------------------------------------------------------------------

    def _merge_dashscope_settings(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Inject ``enable_thinking`` / ``enable_search`` from app settings.

        Explicit kwargs win over settings.
        """
        try:
            from leagent.config.settings import get_settings
            llm = get_settings().llm
        except Exception:
            return kwargs

        merged = dict(kwargs)

        if llm.dashscope_enable_thinking is not None:
            merged.setdefault("enable_thinking", llm.dashscope_enable_thinking)

        if llm.dashscope_enable_search:
            merged.setdefault("enable_search", True)

        return merged

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
        enable_thinking = kwargs.pop("enable_thinking", None)
        if enable_thinking is None and self._is_thinking_model(model):
            enable_thinking = True

        enable_search = kwargs.pop("enable_search", None)
        thinking_budget = kwargs.pop("thinking_budget", None)
        preserve_thinking = kwargs.pop("preserve_thinking", None)
        search_options = kwargs.pop("search_options", None)

        body = super()._build_request_body(
            messages, model, temperature, max_tokens, tools, tool_choice, stop, stream, **kwargs
        )

        if enable_thinking is not None:
            body["enable_thinking"] = enable_thinking

        if enable_search is not None:
            body["enable_search"] = enable_search

        if thinking_budget is not None:
            body["thinking_budget"] = thinking_budget

        if preserve_thinking is not None:
            body["preserve_thinking"] = preserve_thinking

        if search_options is not None:
            body["search_options"] = search_options

        return body

    def _is_thinking_model(self, model: str) -> bool:
        """Return True if the model supports Qwen3 thinking mode."""
        model_lower = model.lower()
        return any(model_lower.startswith(prefix) for prefix in _THINKING_CAPABLE_PREFIXES)

    # ------------------------------------------------------------------
    # Non-streaming completion
    # ------------------------------------------------------------------

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
        kwargs = self._merge_dashscope_settings(kwargs)
        return await super().complete(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            **kwargs,
        )

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        response = super()._parse_response(data)

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        rc = message.get("reasoning_content")
        if isinstance(rc, str) and rc.strip():
            response.reasoning_content = rc

        self._log_cache_metrics(response.usage, response.model)
        return response

    # ------------------------------------------------------------------
    # Streaming completion
    # ------------------------------------------------------------------

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
        kwargs = self._merge_dashscope_settings(kwargs)
        async for chunk in super().stream(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            **kwargs,
        ):
            if chunk.usage:
                self._log_cache_metrics(chunk.usage, chunk.model)
            yield chunk

    def _parse_stream_chunk(self, data: dict[str, Any], model: str) -> StreamChunk:
        chunk = super()._parse_stream_chunk(data, model)
        choices = data.get("choices") or []
        choice = choices[0] if choices else {}
        delta = choice.get("delta", {}) or {}

        content_val = delta.get("content")
        content = "" if content_val is None else str(content_val)

        raw_delta = chunk.raw_delta
        if reasoning := delta.get("reasoning_content"):
            raw_delta = {**(raw_delta or {}), "reasoning_content": reasoning}

        if raw_tc := delta.get("tool_calls"):
            tool_calls_delta = raw_tc
        else:
            tool_calls_delta = list(chunk.tool_calls_delta)

        usage = chunk.usage
        if usage is None:
            raw_usage = data.get("usage")
            if isinstance(raw_usage, dict) and raw_usage:
                completion_detail = raw_usage.get("completion_tokens_details") or {}
                prompt_detail = raw_usage.get("prompt_tokens_details") or {}
                cached = int(prompt_detail.get("cached_tokens", 0) or 0)
                usage = TokenUsage(
                    prompt_tokens=int(raw_usage.get("prompt_tokens", 0)),
                    completion_tokens=int(raw_usage.get("completion_tokens", 0)),
                    total_tokens=int(raw_usage.get("total_tokens", 0)),
                    reasoning_tokens=int(completion_detail.get("reasoning_tokens", 0)),
                    prompt_cache_hit_tokens=cached,
                )

        return StreamChunk(
            content=content,
            tool_calls_delta=tool_calls_delta,
            finish_reason=chunk.finish_reason,
            model=chunk.model,
            raw_delta=raw_delta,
            usage=usage,
        )

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
                error_msg = response_body.get("error", {}).get("message", "")
            else:
                error_msg = str(response_body)
            error_lower = error_msg.lower()

            if "reasoning_content" in error_lower:
                logger.error(
                    "dashscope_reasoning_content_passback_error",
                    extra={
                        "model": model,
                        "hint": (
                            "Qwen3 tool-call turns require reasoning_content to be "
                            "passed back in the assistant message. Ensure "
                            "ChatMessage.reasoning_content is preserved on assistant "
                            "messages that contain tool_calls."
                        ),
                    },
                )
            if "enable_thinking" in error_lower:
                logger.error(
                    "dashscope_enable_thinking_error",
                    extra={
                        "model": model,
                        "hint": (
                            "enable_thinking may not be supported by this model. "
                            "Set DASHSCOPE_ENABLE_THINKING=false or use a Qwen3/QwQ model."
                        ),
                    },
                )
            if "tool_choice" in error_lower and "thinking" in error_lower:
                logger.error(
                    "dashscope_tool_choice_thinking_error",
                    extra={
                        "model": model,
                        "hint": (
                            "Thinking-mode models do not support forced tool_choice. "
                            "Use tool_choice='auto' instead."
                        ),
                    },
                )

        super()._handle_error(status_code, response_body, model)

    # ------------------------------------------------------------------
    # Cache metrics observability
    # ------------------------------------------------------------------

    def _log_cache_metrics(self, usage: TokenUsage | None, model: str) -> None:
        """Emit structured log for DashScope context-cache hit ratios."""
        if usage is None:
            return
        cached = usage.prompt_cache_hit_tokens
        total_prompt = usage.prompt_tokens
        if cached <= 0 or total_prompt <= 0:
            return
        hit_ratio = cached / total_prompt
        logger.debug(
            "dashscope_cache_metrics",
            extra={
                "model": model,
                "prompt_cache_hit_tokens": cached,
                "prompt_tokens": total_prompt,
                "cache_hit_ratio": round(hit_ratio, 4),
            },
        )

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
        **kwargs: Any,
    ) -> EmbeddingResponse:
        """Generate embeddings using DashScope's OpenAI-compatible endpoint."""
        embed_model = model or "text-embedding-v3"
        return await super().embed(texts, model=embed_model, **kwargs)
