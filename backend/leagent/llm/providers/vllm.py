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
from typing import Any, Literal

import httpx

from leagent.llm.base import ChatMessage, LLMResponse, StreamChunk, ToolDefinition
from leagent.llm.providers.openai import OpenAIProvider
from leagent.utils.httpx_proxy import httpx_trust_env
from leagent.exceptions.llm import LLMServiceError

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
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            default_model=default_model,
            timeout=timeout,
            max_retries=max_retries,
        )

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

    async def detect_model(self) -> str | None:
        """Auto-detect the served model via ``/v1/models``.

        Returns the first model ID or None if detection fails.
        """
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
                        self.default_model = model_id
                        return model_id
        except Exception:
            logger.debug("vllm_model_detection_failed", exc_info=True)
        return None

    def _get_default_model(self) -> str:
        return self.default_model or "default"
