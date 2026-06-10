"""Self-hosted txt2img adapter (HuggingFace diffusers, SD/SDXL + LoRA).

Registers as ``image_gen.local`` so the workflow factory exposes it as the
``Model.image_gen.local`` palette node. Parameter choices (model / LoRA /
scheduler combos) are computed at registration time from local discovery.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from leagent.llm.domain_models.diffusion import manager as mgr
from leagent.llm.domain_registry import (
    DomainModelResult,
    DomainModelSpec,
    DomainParam,
)


def _build_spec() -> DomainModelSpec:
    models = tuple(mgr.discover_models())
    loras = tuple(mgr.discover_loras())
    schedulers = tuple(mgr.SCHEDULERS)
    return DomainModelSpec(
        task="image_gen",
        provider="local",
        model=models[0] if models else mgr.default_model(),
        display_name="Image Generation (Local Diffusion)",
        description=(
            "Generate an image in-process with a self-hosted Stable Diffusion / "
            "SDXL checkpoint (HuggingFace diffusers), with optional LoRA."
        ),
        params=(
            DomainParam(id="prompt", io_type="STRING", required=True, multiline=True,
                        tooltip="Image description prompt"),
            DomainParam(id="model", io_type="COMBO", choices=models,
                        default=models[0] if models else "",
                        tooltip="Checkpoint file or HuggingFace hub id"),
            DomainParam(id="negative_prompt", io_type="STRING", multiline=True,
                        default="", tooltip="What to avoid in the image"),
            DomainParam(id="width", io_type="INT", default=1024, min=64, max=4096,
                        tooltip="Output width in pixels"),
            DomainParam(id="height", io_type="INT", default=1024, min=64, max=4096,
                        tooltip="Output height in pixels"),
            DomainParam(id="steps", io_type="INT", default=25, min=1, max=150,
                        tooltip="Sampling steps"),
            DomainParam(id="cfg_scale", io_type="FLOAT", default=7.0, min=0.0, max=30.0,
                        tooltip="Classifier-free guidance scale"),
            DomainParam(id="seed", io_type="INT", default=-1,
                        tooltip="Random seed (-1 = random)"),
            DomainParam(id="scheduler", io_type="COMBO", choices=schedulers,
                        default=mgr.DEFAULT_SCHEDULER, tooltip="Sampler / scheduler"),
            DomainParam(id="lora", io_type="COMBO", choices=loras, default="none",
                        tooltip="LoRA adapter from the LoRA directory"),
            DomainParam(id="lora_scale", io_type="FLOAT", default=0.8, min=0.0, max=2.0,
                        tooltip="LoRA adapter weight"),
        ),
        output="image",
        supports_progress=True,
    )


class DiffusersTxt2ImgAdapter:
    """In-process text-to-image via the shared diffusion pipeline manager."""

    def __init__(self, manager: mgr.DiffusionPipelineManager | None = None) -> None:
        self.spec = _build_spec()
        self._manager = manager or mgr.get_pipeline_manager()

    async def invoke(self, **params: Any) -> DomainModelResult:
        prompt = str(params.get("prompt") or "").strip()
        if not prompt:
            return DomainModelResult(success=False, error="Missing 'prompt' parameter")

        model = str(params.get("model") or self.spec.model)
        if not model:
            return DomainModelResult(
                success=False,
                error=(
                    "No diffusion model configured. Put a checkpoint in "
                    f"{mgr.models_dir()} or set LEAGENT_DIFFUSION_DEFAULT_MODEL."
                ),
            )
        progress: Callable[[int, int], None] | None = params.get("_progress")

        result = await self._manager.generate(
            model=model,
            prompt=prompt,
            negative_prompt=str(params.get("negative_prompt") or ""),
            width=int(params.get("width") or 1024),
            height=int(params.get("height") or 1024),
            steps=int(params.get("steps") or 25),
            cfg_scale=float(params.get("cfg_scale") or 7.0),
            seed=int(params.get("seed") if params.get("seed") is not None else -1),
            scheduler=str(params.get("scheduler") or mgr.DEFAULT_SCHEDULER),
            lora=str(params.get("lora") or "none"),
            lora_scale=float(params.get("lora_scale") or 0.8),
            progress=progress,
        )
        return DomainModelResult(
            b64_data=result.png_b64,
            mime="image/png",
            model=result.model,
            provider="local",
            metadata={
                "seed": result.seed,
                "scheduler": result.scheduler,
                "lora": result.lora,
                **result.metadata,
            },
        )


__all__ = ["DiffusersTxt2ImgAdapter"]
