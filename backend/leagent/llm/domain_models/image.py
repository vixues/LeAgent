"""Image-generation domain adapter wrapping the existing Wanx provider."""

from __future__ import annotations

from typing import Any

from leagent.llm.domain_registry import (
    DomainModelResult,
    DomainModelSpec,
    DomainParam,
)

_SIZES = ("1024*1024", "720*1280", "1280*720")


class DashScopeImageGenAdapter:
    """Text-to-image via DashScope Wanx (delegates to the image_gen provider)."""

    spec = DomainModelSpec(
        task="image_gen",
        provider="dashscope",
        model="wanx2.1-t2i-turbo",
        display_name="Image Generation (DashScope Wanx)",
        description="Generate an image from a text prompt via DashScope Wanx.",
        params=(
            DomainParam(id="prompt", io_type="STRING", required=True, multiline=True,
                        tooltip="Image description prompt"),
            DomainParam(id="size", io_type="COMBO", choices=_SIZES,
                        default="1024*1024", tooltip="Output resolution"),
            DomainParam(id="model", io_type="STRING", default="wanx2.1-t2i-turbo",
                        tooltip="Wanx model name"),
        ),
        output="image",
    )

    def __init__(self, *, api_key: str, timeout: float = 180.0) -> None:
        from leagent.llm.image_gen.dashscope import DashScopeWanxProvider

        self._provider = DashScopeWanxProvider(api_key=api_key, timeout=timeout)

    async def invoke(self, **params: Any) -> DomainModelResult:
        prompt = str(params.get("prompt") or "").strip()
        if not prompt:
            return DomainModelResult(success=False, error="Missing 'prompt' parameter")
        model = str(params.get("model") or self.spec.model)
        size = str(params.get("size") or "1024*1024")

        gen = await self._provider.generate(model=model, prompt=prompt, size=size)
        return DomainModelResult(
            success=gen.b64_json is not None or gen.url is not None,
            b64_data=gen.b64_json,
            url=gen.url,
            mime=gen.mime,
            model=gen.model,
            provider=gen.provider,
            metadata={**gen.metadata, "revised_prompt": gen.revised_prompt},
        )

    async def aclose(self) -> None:
        await self._provider.aclose()
