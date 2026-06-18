"""In-process diffusion pipeline manager (SD / SDXL checkpoints + LoRA).

Owns the heavy lifecycle around HuggingFace ``diffusers`` so the adapter
stays thin:

* **Device/dtype resolution** — cuda (fp16) → mps → cpu, overridable via
  ``LEAGENT_DIFFUSION_DEVICE``.
* **Model discovery** — local ``.safetensors``/``.ckpt`` checkpoints under
  ``LEAGENT_DIFFUSION_MODELS_DIR`` plus HuggingFace hub ids (seeded by
  ``LEAGENT_DIFFUSION_DEFAULT_MODEL``).
* **LoRA discovery** — ``.safetensors`` adapters under
  ``LEAGENT_DIFFUSION_LORA_DIR``.
* **Pipeline cache** — the last loaded pipeline is kept resident (keyed by
  model id); switching models unloads the previous one and frees VRAM.
* **Serialised generation** — a process-wide lock guards the GPU; the sync
  pipeline runs under ``asyncio.to_thread`` with a per-step callback for
  live progress.

Everything ``torch``/``diffusers`` is imported lazily inside methods so the
module can be imported (for specs, discovery, tests) without the optional
``diffusion`` dependency group installed.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from leagent.utils.logging import get_logger

logger = get_logger(__name__)

_CHECKPOINT_SUFFIXES = (".safetensors", ".ckpt")

#: Scheduler key → (module attr in ``diffusers``, extra config kwargs).
SCHEDULERS: dict[str, tuple[str, dict[str, Any]]] = {
    "euler_a": ("EulerAncestralDiscreteScheduler", {}),
    "euler": ("EulerDiscreteScheduler", {}),
    "dpmpp_2m": ("DPMSolverMultistepScheduler", {}),
    "dpmpp_2m_karras": ("DPMSolverMultistepScheduler", {"use_karras_sigmas": True}),
    "ddim": ("DDIMScheduler", {}),
    "unipc": ("UniPCMultistepScheduler", {}),
}

DEFAULT_SCHEDULER = "euler_a"


def _local_cfg() -> dict[str, Any]:
    """Admin-managed local-diffusion config (``image_gen.local`` in YAML)."""
    try:
        from leagent.llm.generation.config import get_image_gen_config

        return get_image_gen_config().local_config()
    except Exception:  # noqa: BLE001 - config is best-effort here
        return {}


def models_dir() -> Path:
    configured = str(_local_cfg().get("models_dir") or "").strip()
    if configured:
        return Path(configured).expanduser()
    raw = os.environ.get("LEAGENT_DIFFUSION_MODELS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".leagent" / "models" / "diffusion"


def lora_dir() -> Path:
    configured = str(_local_cfg().get("lora_dir") or "").strip()
    if configured:
        return Path(configured).expanduser()
    raw = os.environ.get("LEAGENT_DIFFUSION_LORA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".leagent" / "models" / "lora"


def default_model() -> str:
    configured = str(_local_cfg().get("default_model") or "").strip()
    if configured:
        return configured
    return os.environ.get(
        "LEAGENT_DIFFUSION_DEFAULT_MODEL", "stabilityai/stable-diffusion-xl-base-1.0"
    ).strip()


def discover_models() -> list[str]:
    """Return selectable model ids: local checkpoints first, then the default hub id."""
    found: list[str] = []
    root = models_dir()
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() in _CHECKPOINT_SUFFIXES and path.is_file():
                found.append(str(path.relative_to(root)))
    fallback = default_model()
    if fallback and fallback not in found:
        found.append(fallback)
    return found


def discover_loras() -> list[str]:
    """Return selectable LoRA adapter names (relative paths), ``none`` first."""
    found: list[str] = ["none"]
    root = lora_dir()
    if root.is_dir():
        for path in sorted(root.rglob("*.safetensors")):
            if path.is_file():
                found.append(str(path.relative_to(root)))
    return found


@dataclass
class GenerationResult:
    """One generated image plus the effective sampling parameters."""

    png_b64: str
    seed: int
    model: str
    scheduler: str
    lora: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _looks_like_sdxl(model_id: str) -> bool:
    lowered = model_id.lower()
    return "xl" in lowered or "sdxl" in lowered


class DiffusionPipelineManager:
    """Loads, caches, and drives diffusers pipelines (one resident at a time)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pipeline: Any = None
        self._pipeline_key: str | None = None
        self._loaded_lora: str | None = None

    # ------------------------------------------------------------------
    # Device / dtype
    # ------------------------------------------------------------------

    def resolve_device(self) -> tuple[str, Any]:
        """Return ``(device, torch_dtype)`` for pipeline placement."""
        import torch

        override = os.environ.get("LEAGENT_DIFFUSION_DEVICE", "").strip().lower()
        if override:
            device = override
        elif torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        return device, dtype

    # ------------------------------------------------------------------
    # Pipeline loading
    # ------------------------------------------------------------------

    def _load_pipeline(self, model_id: str) -> Any:
        """Load (or return the cached) pipeline for ``model_id``."""
        if self._pipeline is not None and self._pipeline_key == model_id:
            return self._pipeline

        self._unload_pipeline()

        import diffusers

        device, dtype = self.resolve_device()
        local_path = models_dir() / model_id
        is_sdxl = _looks_like_sdxl(model_id)
        cls = (
            diffusers.StableDiffusionXLPipeline
            if is_sdxl
            else diffusers.StableDiffusionPipeline
        )

        logger.info(
            "diffusion_pipeline_loading",
            model=model_id,
            device=device,
            sdxl=is_sdxl,
        )
        if local_path.is_file():
            pipe = cls.from_single_file(str(local_path), torch_dtype=dtype)
        else:
            # Hub id (or a local diffusers directory layout).
            source = str(local_path) if local_path.is_dir() else model_id
            pipe = cls.from_pretrained(source, torch_dtype=dtype)

        pipe = pipe.to(device)
        if hasattr(pipe, "safety_checker"):
            pipe.safety_checker = None  # local generation; avoid extra VRAM
        self._pipeline = pipe
        self._pipeline_key = model_id
        self._loaded_lora = None
        return pipe

    def _unload_pipeline(self) -> None:
        if self._pipeline is None:
            return
        logger.info("diffusion_pipeline_unloading", model=self._pipeline_key)
        self._pipeline = None
        self._pipeline_key = None
        self._loaded_lora = None
        try:
            import gc

            import torch

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - best-effort VRAM cleanup
            pass

    def _apply_scheduler(self, pipe: Any, scheduler: str) -> str:
        import diffusers

        key = scheduler if scheduler in SCHEDULERS else DEFAULT_SCHEDULER
        attr, extra = SCHEDULERS[key]
        cls = getattr(diffusers, attr, None)
        if cls is None:
            return key
        pipe.scheduler = cls.from_config(pipe.scheduler.config, **extra)
        return key

    def _apply_lora(self, pipe: Any, lora: str | None, scale: float) -> str | None:
        """Load/unload the requested LoRA on the resident pipeline."""
        wanted = None if not lora or lora == "none" else lora
        if wanted == self._loaded_lora:
            if wanted is not None:
                pipe.set_adapters(["active"], adapter_weights=[scale])
            return wanted

        if self._loaded_lora is not None:
            try:
                pipe.unload_lora_weights()
            except Exception:  # noqa: BLE001
                logger.warning("diffusion_lora_unload_failed", exc_info=True)
            self._loaded_lora = None

        if wanted is None:
            return None

        path = lora_dir() / wanted
        source = str(path) if path.is_file() else wanted
        pipe.load_lora_weights(source, adapter_name="active")
        pipe.set_adapters(["active"], adapter_weights=[scale])
        self._loaded_lora = wanted
        return wanted

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def _generate_sync(
        self,
        *,
        model: str,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        steps: int = 25,
        cfg_scale: float = 7.0,
        seed: int = -1,
        scheduler: str = DEFAULT_SCHEDULER,
        lora: str | None = None,
        lora_scale: float = 0.8,
        progress: Callable[[int, int], None] | None = None,
    ) -> GenerationResult:
        import torch

        with self._lock:
            pipe = self._load_pipeline(model)
            effective_scheduler = self._apply_scheduler(pipe, scheduler)
            effective_lora = self._apply_lora(pipe, lora, lora_scale)

            device, _ = self.resolve_device()
            if seed is None or int(seed) < 0:
                seed = int(torch.seed() % (2**32))
            generator = torch.Generator(device="cpu").manual_seed(int(seed))

            def _step_cb(_pipe: Any, step: int, _timestep: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
                if progress is not None:
                    with contextlib.suppress(Exception):  # progress is best-effort
                        progress(step + 1, steps)
                return kwargs

            call_kwargs: dict[str, Any] = {
                "prompt": prompt,
                "negative_prompt": negative_prompt or None,
                "width": int(width),
                "height": int(height),
                "num_inference_steps": int(steps),
                "guidance_scale": float(cfg_scale),
                "generator": generator,
                "callback_on_step_end": _step_cb,
            }

            output = pipe(**call_kwargs)
            image = output.images[0]

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return GenerationResult(
            png_b64=base64.b64encode(buf.getvalue()).decode(),
            seed=int(seed),
            model=model,
            scheduler=effective_scheduler,
            lora=effective_lora,
            metadata={
                "width": int(width),
                "height": int(height),
                "steps": int(steps),
                "cfg_scale": float(cfg_scale),
                "device": device,
            },
        )

    async def generate(self, **kwargs: Any) -> GenerationResult:
        """Async facade: run the GPU-bound pipeline in a worker thread."""
        return await asyncio.to_thread(self._generate_sync, **kwargs)


_MANAGER: DiffusionPipelineManager | None = None


def get_pipeline_manager() -> DiffusionPipelineManager:
    """Return the process-wide pipeline manager (lazily created)."""
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = DiffusionPipelineManager()
    return _MANAGER


__all__ = [
    "DEFAULT_SCHEDULER",
    "SCHEDULERS",
    "DiffusionPipelineManager",
    "GenerationResult",
    "default_model",
    "discover_loras",
    "discover_models",
    "get_pipeline_manager",
    "lora_dir",
    "models_dir",
]
