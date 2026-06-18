"""Convert provider results to :class:`GenerationOutput` and legacy shims."""

from __future__ import annotations

import base64
from typing import Any

from leagent.llm.generation.base import GenerationOutput
from leagent.llm.generation.providers.base import ImageGenResult, ProviderResult


def provider_result_to_output(
    result: ProviderResult,
    *,
    kind: str,
    provider: str,
    model: str,
    filename: str = "image.png",
) -> GenerationOutput:
    """Map a vendor :class:`ProviderResult` into a :class:`GenerationOutput`."""
    data: bytes | None = None
    if result.b64_json:
        data = base64.b64decode(result.b64_json)
    meta: dict[str, Any] = dict(result.metadata or {})
    if result.url:
        meta.setdefault("url", result.url)
    if result.revised_prompt:
        meta["revised_prompt"] = result.revised_prompt
    resolved_model = model or result.model
    if data is None and result.url:
        return GenerationOutput(
            success=True,
            kind=kind,
            data=None,
            mime=result.mime or "image/png",
            filename=filename,
            provider=provider,
            model=resolved_model,
            meta=meta,
        )
    if data is None:
        return GenerationOutput.failure(kind, f"{provider} returned no image bytes")
    return GenerationOutput(
        success=True,
        kind=kind,
        data=data,
        mime=result.mime or "image/png",
        filename=filename,
        provider=provider,
        model=resolved_model,
        meta=meta,
    )


def generation_output_to_image_gen_result(out: GenerationOutput) -> ImageGenResult:
    """Map :class:`GenerationOutput` back to legacy :class:`ImageGenResult`."""
    b64: str | None = None
    if out.data:
        b64 = base64.b64encode(out.data).decode()
    url = out.meta.get("url") if out.meta else None
    return ImageGenResult(
        success=out.success,
        b64_json=b64,
        url=str(url) if url else None,
        mime=out.mime or "image/png",
        revised_prompt=out.meta.get("revised_prompt") if out.meta else None,
        model=out.model,
        provider=out.provider,
        metadata=dict(out.meta or {}),
    )


__all__ = [
    "generation_output_to_image_gen_result",
    "provider_result_to_output",
]
