"""Image-generation domain adapter — delegates to :class:`GenerationService`.

.. deprecated::
    Prefer ``Art.ImageGen`` nodes or ``GenerationService.generate(kind="image")``.
"""

from __future__ import annotations

import warnings
from typing import Any

from leagent.llm.domain_registry import (
    DomainModelResult,
    DomainModelSpec,
    DomainParam,
)

_SIZES = ("1024*1024", "720*1280", "1280*720")


class DashScopeImageGenAdapter:
    """Text-to-image via the unified media generation plane."""

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
        self._api_key = api_key
        self._timeout = timeout

    async def invoke(self, **params: Any) -> DomainModelResult:
        warnings.warn(
            "DashScopeImageGenAdapter is deprecated; use GenerationService.generate(kind='image')",
            DeprecationWarning,
            stacklevel=2,
        )
        prompt = str(params.get("prompt") or "").strip()
        if not prompt:
            return DomainModelResult(success=False, error="Missing 'prompt' parameter")
        model = str(params.get("model") or self.spec.model)
        size = str(params.get("size") or "1024*1024")

        from leagent.llm.generation import get_generation_service

        out = await get_generation_service().generate(
            kind="image",
            prompt=prompt,
            provider="dashscope",
            model=model,
            size=size,
            timeout=self._timeout,
        )
        if not out.success:
            return DomainModelResult(success=False, error=out.error or "image generation failed")

        import base64

        b64_data: str | None = None
        if out.data:
            b64_data = base64.b64encode(out.data).decode()
        url = out.meta.get("url") if out.meta else None
        return DomainModelResult(
            success=bool(b64_data or url),
            b64_data=b64_data,
            url=str(url) if url else None,
            mime=out.mime or "image/png",
            model=out.model or model,
            provider=out.provider or "dashscope",
            metadata=dict(out.meta or {}),
        )

    async def aclose(self) -> None:
        return None
