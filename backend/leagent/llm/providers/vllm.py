"""vLLM LLM provider.

vLLM exposes an OpenAI-compatible server, so most of the work is handled by
:class:`OpenAIProvider`. This subclass adds:

- ``structured_outputs`` extra body parameter for vLLM's constrained decoding
  (``choice``, ``regex``, ``json``, ``grammar``, ``structural_tag``).
- Model auto-detection via ``/v1/models``.
- Default base URL and model handling for self-hosted deployments.

The ``name`` attribute stays ``"vllm"`` so the registry can route by
provider type.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any, Literal

from leagent.llm.base import ChatMessage, LLMResponse, StreamChunk, ToolDefinition

from leagent.llm.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class VLLMProvider(OpenAIProvider):
    """OpenAI-compatible provider for vLLM self-hosted model serving.

    Supports all OpenAI-compatible features plus vLLM-specific structured
    output via the ``structured_outputs`` extra body parameter.
    """

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
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            default_model=default_model,
            timeout=timeout,
            max_retries=max_retries,
        )
        # When True, send tool_choice="auto" (requires vLLM started with
        # --enable-auto-tool-choice and --tool-call-parser).
        self.enable_auto_tool_choice = enable_auto_tool_choice

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
        # Extract vLLM-specific structured_outputs before passing to super
        structured_outputs = kwargs.pop("structured_outputs", None)

        enable_auto = kwargs.pop(
            "enable_auto_tool_choice",
            self.enable_auto_tool_choice,
        )
        if not enable_auto and tool_choice == "auto":
            # vLLM returns 400 unless the server was started with
            # --enable-auto-tool-choice and --tool-call-parser.
            tool_choice = None

        body = super()._build_request_body(
            messages, model, temperature, max_tokens, tools, tool_choice, stop, stream, **kwargs
        )

        # Inject vLLM structured outputs as extra body parameter
        if structured_outputs:
            body["structured_outputs"] = structured_outputs

        return body

    # ------------------------------------------------------------------
    # Model detection
    # ------------------------------------------------------------------

    def _needs_model_resolution(self, model: str | None) -> bool:
        """True when the caller-supplied model is blank or a placeholder."""
        if not model:
            return True
        return model == "default" and not self.default_model

    async def _resolve_model_for_request(self, requested_model: str | None) -> str:
        """Resolve a blank/placeholder model against the running vLLM server."""
        if not self._needs_model_resolution(requested_model):
            return requested_model  # type: ignore[return-value]

        detected = await self.detect_model()
        return detected or requested_model or "default"

    _detected_model: str | None = None

    async def detect_model(self) -> str | None:
        """Auto-detect the served model via ``/v1/models``.

        Returns the first model ID or None if detection fails.
        Caches the result in ``_detected_model`` so subsequent calls
        do not hit the server again.
        """
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
        """Pick a model for health checks, preferring config then discovery."""
        for candidate in [preferred, *(configured or [])]:
            value = (candidate or "").strip()
            if value:
                return value
        return await self._resolve_model_for_request(None)

    def _get_default_model(self) -> str:
        return self.default_model or "default"

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        **kwargs: Any,
    ) -> LLMResponse:
        resolved = await self._resolve_model_for_request(model)
        return await super().complete(messages=messages, model=resolved, **kwargs)

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        model: str,
        **kwargs: Any,
    ) -> AsyncIterator[StreamChunk]:
        resolved = await self._resolve_model_for_request(model)
        async for chunk in super().stream(messages=messages, model=resolved, **kwargs):
            yield chunk
