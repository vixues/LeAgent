"""In-process diffusers image generation backend."""

from __future__ import annotations

import base64
import os
from typing import Any

from leagent.llm.generation.backends._utils import parse_size
from leagent.llm.generation.base import GenerationOutput
from leagent.llm.generation.config import get_image_gen_config


class LocalDiffusionBackend:
    """Wrap the in-process diffusers pipeline as an image generation strategy."""

    name = "local"
    kinds = ("image",)

    _PASSTHROUGH = (
        "model", "negative_prompt", "width", "height", "steps",
        "cfg_scale", "seed", "scheduler", "lora", "lora_scale",
        "image", "strength", "controlnet", "control_image", "camera",
    )

    def available(self) -> bool:
        if not get_image_gen_config().local_config().get("enabled", True):
            return False
        if os.environ.get("LEAGENT_DIFFUSION_ENABLED", "1").strip() == "0":
            return False
        try:
            from leagent.llm.domain_models.diffusion import diffusers_available

            return bool(diffusers_available())
        except Exception:  # noqa: BLE001
            return False

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "image":
            return GenerationOutput.failure(kind, "local diffusion produces only images")
        from leagent.llm.domain_models.diffusion.adapter import DiffusersTxt2ImgAdapter

        invoke_params: dict[str, Any] = {"prompt": prompt}
        for key in self._PASSTHROUGH:
            if params.get(key) is not None:
                invoke_params[key] = params[key]
        if "width" not in invoke_params or "height" not in invoke_params:
            w, h = parse_size(params.get("size"))
            invoke_params.setdefault("width", w)
            invoke_params.setdefault("height", h)
        if "_progress" in params:
            invoke_params["_progress"] = params["_progress"]

        adapter = DiffusersTxt2ImgAdapter()
        result = await adapter.invoke(**invoke_params)
        if not getattr(result, "success", False):
            return GenerationOutput.failure(
                "image", getattr(result, "error", None) or "local diffusion failed",
            )
        data: bytes | None = None
        if getattr(result, "b64_data", None):
            data = base64.b64decode(result.b64_data)
        if data is None and getattr(result, "url", None):
            return GenerationOutput(
                success=True, kind="image", data=None, mime=result.mime or "image/png",
                filename="image.png", provider=self.name, model=result.model,
                meta={"url": result.url, **dict(result.metadata)},
            )
        if data is None:
            return GenerationOutput.failure("image", "local diffusion returned no image bytes")
        return GenerationOutput(
            success=True, kind="image", data=data, mime=result.mime or "image/png",
            filename="image.png", provider=self.name, model=result.model,
            meta=dict(result.metadata),
        )


__all__ = ["LocalDiffusionBackend"]
