"""vLLM LLM provider.

vLLM exposes an OpenAI-compatible server. This subclass extends
:class:`CustomOpenAIProvider` (tolerant tool-call parsing) and adds:

- ``structured_outputs`` extra body parameter for vLLM constrained decoding.
- Model auto-detection via ``/v1/models``.
- Optional ``tool_choice="auto"`` gated behind ``enable_auto_tool_choice``.
- Diagnostic logging for common vLLM 400 errors (tool-choice, message shape).

The ``name`` attribute stays ``"vllm"`` so the registry can route by provider type.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from leagent.llm.base import ChatMessage, LLMResponse, StreamChunk, ToolDefinition
from leagent.llm.providers.custom import CustomOpenAIProvider

logger = logging.getLogger(__name__)


class VLLMProvider(CustomOpenAIProvider):
    """OpenAI-compatible provider for vLLM self-hosted model serving."""

    name = "vllm"
    supports_streaming = True
    supports_tools = True
    supports_embeddings = True
    supports_structured_output = True

    DEFAULT_BASE_URL = "http://localhost:8000/v1"

    def __init__(
        self,
        api_key: str = "not-needed",
        base_url: str = DEFAULT_BASE_URL,
        default_model: str = "",
        timeout: float = 120.0,
        max_retries: int = 2,
        *,
        enable_auto_tool_choice: bool = False,
        parse_think_tags: bool = True,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            default_model=default_model,
            timeout=timeout,
            max_retries=max_retries,
            parse_think_tags=parse_think_tags,
        )
        self.enable_auto_tool_choice = enable_auto_tool_choice
        self._detected_model: str | None = None

    # ------------------------------------------------------------------
    # Request options
    # ------------------------------------------------------------------

    @staticmethod
    def _split_vllm_request_options(
        kwargs: dict[str, Any],
        *,
        default_enable_auto_tool_choice: bool,
    ) -> tuple[dict[str, Any], Any | None, bool]:
        """Pop vLLM-only kwargs before delegating to :class:`CustomOpenAIProvider`."""
        merged = dict(kwargs)
        structured_outputs = merged.pop("structured_outputs", None)
        enable_auto = merged.pop(
            "enable_auto_tool_choice",
            default_enable_auto_tool_choice,
        )
        return merged, structured_outputs, bool(enable_auto)

    def _resolve_tool_choice(
        self,
        tool_choice: Literal["auto", "none", "required"] | str | None,
        *,
        enable_auto_tool_choice: bool,
    ) -> Literal["auto", "none", "required"] | str | None:
        if not enable_auto_tool_choice and tool_choice == "auto":
            return None
        return tool_choice

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
        merged, structured_outputs, enable_auto = self._split_vllm_request_options(
            kwargs,
            default_enable_auto_tool_choice=self.enable_auto_tool_choice,
        )
        resolved_tool_choice = self._resolve_tool_choice(
            tool_choice,
            enable_auto_tool_choice=enable_auto,
        )

        body = super()._build_request_body(
            messages,
            model,
            temperature,
            max_tokens,
            tools,
            resolved_tool_choice,
            stop,
            stream,
            **merged,
        )

        if structured_outputs:
            body["structured_outputs"] = structured_outputs

        return body

    # ------------------------------------------------------------------
    # Model detection
    # ------------------------------------------------------------------

    def _needs_model_resolution(self, model: str | None) -> bool:
        if not model:
            return True
        return model == "default" and not self.default_model

    async def _resolve_model_for_request(self, requested_model: str | None) -> str:
        if not self._needs_model_resolution(requested_model):
            return requested_model  # type: ignore[return-value]

        detected = await self.detect_model()
        return detected or requested_model or "default"

    async def detect_model(self) -> str | None:
        """Auto-detect the served model via ``/v1/models`` (cached)."""
        if self._detected_model:
            return self._detected_model

        url = f"{self.base_url}/models"
        try:
            client = self._ensure_complete_client()
            response = await client.get(url, headers=self._get_headers())
            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                if models:
                    model_id = models[0].get("id", "")
                    if model_id:
                        self._detected_model = model_id
                        if not self.default_model:
                            self.default_model = model_id
                        return model_id
        except Exception:
            logger.debug("vllm_model_detection_failed", exc_info=True)
        return None

    async def resolve_test_model(
        self,
        preferred: str | None = None,
        configured: list[str] | None = None,
    ) -> str:
        for candidate in [preferred, *(configured or [])]:
            value = (candidate or "").strip()
            if value:
                return value
        return await self._resolve_model_for_request(None)

    def _get_default_model(self) -> str:
        return self.default_model or "default"

    # ------------------------------------------------------------------
    # Completion entry points
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
        resolved = await self._resolve_model_for_request(model)
        return await super().complete(
            messages,
            model=resolved,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            **kwargs,
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
        resolved = await self._resolve_model_for_request(model)
        async for chunk in super().stream(
            messages=messages,
            model=resolved,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            stop=stop,
            **kwargs,
        ):
            yield chunk

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
            if "tool" in lowered and ("choice" in lowered or "auto" in lowered):
                logger.error(
                    "vllm_tool_choice_error",
                    extra={
                        "model": model,
                        "enable_auto_tool_choice": self.enable_auto_tool_choice,
                        "hint": (
                            "vLLM rejected tool_choice. Start the server with "
                            "--enable-auto-tool-choice and --tool-call-parser, "
                            "or set metadata.enable_auto_tool_choice=false and omit "
                            "tool_choice='auto'."
                        ),
                    },
                )
        super()._handle_error(status_code, response_body, model)
