"""DeepSeek LLM provider.

DeepSeek exposes an OpenAI-compatible ``/chat/completions`` endpoint so
most of the work is already handled by :class:`OpenAIProvider`. This
subclass adds:

- Default base URL / model pinned to DeepSeek's V4 values.
- ``thinking`` / ``reasoning_effort`` injection from settings + per-request
  contextvar overrides (default: thinking enabled).
- Stripping of deprecated ``frequency_penalty`` / ``presence_penalty`` from
  *all* requests, plus ``temperature`` / ``top_p`` in thinking mode (the API
  silently ignores these).
- ``reasoning_content`` extraction for both streaming and non-streaming
  responses, surfaced via ``StreamChunk.raw_delta`` / ``LLMResponse``.
- ``user_id`` injection for per-user KV cache isolation.
- ``fim_complete()`` for Fill-In-the-Middle code infill (beta endpoint).
- Structured logging of cache hit/miss ratios per response.
- Diagnostic detection of 400 errors caused by missing ``reasoning_content``
  on tool-call turns.

The ``name`` attribute stays ``"deepseek"`` so the registry can route by
provider type.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from leagent.llm.base import ChatMessage, LLMResponse, StreamChunk, TokenUsage, ToolCall, ToolDefinition
from leagent.llm.providers.openai import OpenAIProvider
from leagent.utils.httpx_proxy import httpx_trust_env

logger = logging.getLogger(__name__)

_DEEPSEEK_DEPRECATED_PARAMS = frozenset({"frequency_penalty", "presence_penalty"})
_THINKING_MODE_SUPPRESSED_PARAMS = frozenset({"temperature", "top_p"}) | _DEEPSEEK_DEPRECATED_PARAMS

_USER_ID_RE = re.compile(r"[^a-zA-Z0-9\-_]")

# ---------------------------------------------------------------------------
# Per-request contextvar overrides (set from the API layer)
# ---------------------------------------------------------------------------

_reasoning_effort_override: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_reasoning_effort_override", default=None
)

_deepseek_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_deepseek_user_id", default=None
)


def set_reasoning_effort_override(effort: str | None) -> contextvars.Token[str | None]:
    """Set per-request reasoning effort (e.g. 'high', 'max'). Returns a reset token."""
    return _reasoning_effort_override.set(effort)


def reset_reasoning_effort_override(token: contextvars.Token[str | None]) -> None:
    """Reset the reasoning effort override using the token from :func:`set_reasoning_effort_override`."""
    _reasoning_effort_override.reset(token)


def set_deepseek_user_id(user_id: str | None) -> contextvars.Token[str | None]:
    """Set per-request user_id for DeepSeek KV cache isolation. Returns a reset token."""
    return _deepseek_user_id.set(user_id)


def reset_deepseek_user_id(token: contextvars.Token[str | None]) -> None:
    """Reset the user_id override using the token from :func:`set_deepseek_user_id`."""
    _deepseek_user_id.reset(token)


def _sanitize_user_id(raw: str) -> str:
    """Sanitize a user_id to match DeepSeek's allowed charset ``[a-zA-Z0-9\\-_]``."""
    sanitized = _USER_ID_RE.sub("_", raw)
    return sanitized[:512]


class DeepSeekProvider(OpenAIProvider):
    """OpenAI-compatible provider tuned for DeepSeek's V4 API."""

    name = "deepseek"
    supports_streaming = True
    supports_tools = True
    supports_embeddings = False

    DEFAULT_BASE_URL = "https://api.deepseek.com"
    DEFAULT_MODEL = "deepseek-v4-flash"

    THINKING_CAPABLE_MODELS = frozenset({
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    })

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

    def _merge_deepseek_settings(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Inject ``thinking`` / ``reasoning_effort`` from app settings.

        Explicit kwargs win over settings; per-request overrides via
        :data:`_reasoning_effort_override` win over everything.

        When no thinking type is configured explicitly, we default to
        ``enabled`` to match the V4 API's own default.
        """
        from leagent.config.settings import get_settings

        merged = dict(kwargs)
        llm = get_settings().llm

        if llm.deepseek_thinking_type:
            merged.setdefault("thinking", {"type": llm.deepseek_thinking_type})
        else:
            merged.setdefault("thinking", {"type": "enabled"})

        override = _reasoning_effort_override.get()
        if override:
            merged["reasoning_effort"] = override
        elif llm.deepseek_reasoning_effort:
            merged.setdefault("reasoning_effort", llm.deepseek_reasoning_effort)

        return merged

    def _is_thinking_enabled(self, kwargs: dict[str, Any]) -> bool:
        """Return True if the merged kwargs indicate thinking mode is active."""
        thinking = kwargs.get("thinking")
        return isinstance(thinking, dict) and thinking.get("type") == "enabled"

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
            messages, model, temperature, max_tokens, tools, tool_choice, stop, stream, **kwargs
        )

        for key in _DEEPSEEK_DEPRECATED_PARAMS:
            body.pop(key, None)

        if self._is_thinking_enabled(body):
            for key in _THINKING_MODE_SUPPRESSED_PARAMS:
                body.pop(key, None)

        uid = _deepseek_user_id.get()
        if uid:
            body.setdefault("user_id", _sanitize_user_id(uid))

        return body

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
        kwargs = self._merge_deepseek_settings(kwargs)
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
        kwargs = self._merge_deepseek_settings(kwargs)
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
                detail = raw_usage.get("completion_tokens_details") or {}
                usage = TokenUsage(
                    prompt_tokens=int(raw_usage.get("prompt_tokens", 0)),
                    completion_tokens=int(raw_usage.get("completion_tokens", 0)),
                    total_tokens=int(raw_usage.get("total_tokens", 0)),
                    reasoning_tokens=int(detail.get("reasoning_tokens", 0)),
                    prompt_cache_hit_tokens=int(raw_usage.get("prompt_cache_hit_tokens", 0) or 0),
                    prompt_cache_miss_tokens=int(raw_usage.get("prompt_cache_miss_tokens", 0) or 0),
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
            if "reasoning_content" in error_msg.lower():
                logger.error(
                    "deepseek_reasoning_content_passback_error",
                    extra={
                        "model": model,
                        "hint": (
                            "Tool-call turns require reasoning_content to be passed back "
                            "in the assistant message. Ensure ChatMessage.reasoning_content "
                            "is preserved on assistant messages that contain tool_calls."
                        ),
                    },
                )
        super()._handle_error(status_code, response_body, model)

    # ------------------------------------------------------------------
    # FIM (Fill-In-the-Middle) — beta endpoint
    # ------------------------------------------------------------------

    async def fim_complete(
        self,
        prompt: str,
        suffix: str,
        *,
        model: str = "deepseek-v4-pro",
        max_tokens: int = 128,
        temperature: float = 1.0,
    ) -> str:
        """Fill-In-the-Middle completion via the ``/beta/completions`` endpoint.

        Only ``deepseek-v4-pro`` supports FIM.

        Returns the generated infill text.
        """
        base = self.base_url.rstrip("/")
        url = f"{base}/beta/completions"

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "suffix": suffix,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        client = self._ensure_complete_client()
        response = await client.post(url, headers=self._get_headers(), json=body)

        if response.status_code != 200:
            try:
                error_body = response.json()
            except (json.JSONDecodeError, ValueError):
                error_body = response.text
            self._handle_error(response.status_code, error_body, model)

        data = response.json()
        choices = data.get("choices") or []
        return choices[0].get("text", "") if choices else ""

    # ------------------------------------------------------------------
    # Cache metrics observability
    # ------------------------------------------------------------------

    def _log_cache_metrics(self, usage: TokenUsage | None, model: str) -> None:
        """Emit structured log for DeepSeek context-cache hit/miss ratios."""
        if usage is None:
            return
        total_prompt = usage.prompt_cache_hit_tokens + usage.prompt_cache_miss_tokens
        if total_prompt <= 0:
            return
        hit_ratio = usage.prompt_cache_hit_tokens / total_prompt
        logger.debug(
            "deepseek_cache_metrics",
            extra={
                "model": model,
                "prompt_cache_hit_tokens": usage.prompt_cache_hit_tokens,
                "prompt_cache_miss_tokens": usage.prompt_cache_miss_tokens,
                "cache_hit_ratio": round(hit_ratio, 4),
            },
        )
