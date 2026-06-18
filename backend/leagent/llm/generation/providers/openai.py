"""OpenAI DALL-E image generation provider."""

from __future__ import annotations

from typing import Any

from leagent.llm.generation.providers.base import ImageGenResult


class OpenAIImageGenProvider:
    """Generate images via OpenAI Images API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "vivid",
        response_format: str = "b64_json",
        **kwargs: Any,
    ) -> ImageGenResult:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for image generation") from exc

        client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        response = await client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
            style=style,
            response_format=response_format,
        )
        image_data = response.data[0]
        result = ImageGenResult(model=model, provider="openai")
        result.revised_prompt = getattr(image_data, "revised_prompt", None)
        if response_format == "b64_json" and image_data.b64_json:
            result.b64_json = image_data.b64_json
        elif image_data.url:
            result.url = image_data.url
        return result

    async def aclose(self) -> None:
        return None
