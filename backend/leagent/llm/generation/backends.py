"""Concrete generation backends (strategies).

- :class:`OfflineGenerationBackend` — deterministic, dependency-free
  placeholder producer for every kind. Always available; the reliability
  floor that lets the whole pipeline run end-to-end without credentials.
- :class:`ImageProviderBackend` — wraps the existing image-gen providers
  (``OpenAIImageGenProvider`` / ``DashScopeWanxProvider``) for real
  text-to-image.
- :class:`HttpVideoBackend` / :class:`HttpMesh3DBackend` — env-gated
  hooks for real external video / image-to-3D services. They are only
  *available* when their base URL + key are configured; otherwise the
  service falls back to the offline backend.
"""

from __future__ import annotations

import base64
import os
from typing import Any

from leagent.utils.logging import get_logger

from .base import GenerationBackend, GenerationOutput
from .placeholders import (
    color_from_prompt,
    placeholder_mp4,
    solid_png,
    triangle_glb,
)

logger = get_logger(__name__)


def _parse_size(size: Any, default: tuple[int, int] = (512, 512)) -> tuple[int, int]:
    if isinstance(size, str):
        sep = "x" if "x" in size else ("*" if "*" in size else None)
        if sep:
            try:
                w, h = size.split(sep)
                return int(w), int(h)
            except (ValueError, TypeError):
                return default
    return default


class OfflineGenerationBackend:
    """Always-available placeholder backend for every media kind."""

    name = "offline"
    kinds = ("image", "video", "model3d")

    def available(self) -> bool:
        return True

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        rgb = color_from_prompt(prompt)
        if kind == "image":
            w, h = _parse_size(params.get("size") or params.get("width"))
            if "width" in params and "height" in params:
                w, h = int(params["width"]), int(params["height"])
            if camera := params.get("camera"):
                if isinstance(camera, dict):
                    seed = (
                        f"cam-{camera.get('azimuth', 0)}-{camera.get('elevation', 0)}"
                        f"-{camera.get('fov', 50)}"
                    )
                    rgb = color_from_prompt(f"{prompt}:{seed}")
            if control := params.get("controlnet"):
                if isinstance(control, dict):
                    strength = float(control.get("strength") or 0.8)
                    mode = str(control.get("mode") or "openpose")
                    tint = color_from_prompt(f"ctrl-{mode}")
                    rgb = tuple(
                        int(rgb[i] * (1.0 - strength * 0.35) + tint[i] * (strength * 0.35))
                        for i in range(3)
                    )
            data = solid_png(w, h, rgb)
            extra_meta: dict[str, Any] = {"width": w, "height": h, "rgb": list(rgb), "placeholder": True}
            if params.get("camera"):
                extra_meta["camera"] = params["camera"]
            if params.get("controlnet"):
                extra_meta["controlnet"] = params["controlnet"]
            return GenerationOutput(
                success=True, kind="image", data=data, mime="image/png",
                filename="image.png", provider=self.name, model="offline-solid",
                meta=extra_meta,
            )
        if kind == "video":
            data = placeholder_mp4(prompt)
            return GenerationOutput(
                success=True, kind="video", data=data, mime="video/mp4",
                filename="video.mp4", provider=self.name, model="offline-clip",
                meta={"placeholder": True, "duration_sec": params.get("duration", 2)},
            )
        if kind == "model3d":
            if camera := params.get("camera"):
                if isinstance(camera, dict):
                    seed = (
                        f"cam-{camera.get('azimuth', 0)}-{camera.get('elevation', 0)}"
                    )
                    rgb = color_from_prompt(f"{prompt}:{seed}")
            data = triangle_glb(rgb)
            mesh_meta: dict[str, Any] = {"placeholder": True, "rgb": list(rgb)}
            if params.get("camera"):
                mesh_meta["camera"] = params["camera"]
            if params.get("reference_mesh"):
                mesh_meta["reference_mesh"] = params["reference_mesh"]
            return GenerationOutput(
                success=True, kind="model3d", data=data, mime="model/gltf-binary",
                filename="model.glb", provider=self.name, model="offline-mesh",
                meta=mesh_meta,
            )
        return GenerationOutput.failure(kind, f"offline backend cannot produce '{kind}'")


class ImageProviderBackend:
    """Wrap an ``llm.image_gen`` provider as an image generation strategy."""

    kinds = ("image",)

    def __init__(self, name: str) -> None:
        self.name = name

    def available(self) -> bool:
        if self.name == "openai":
            return bool(os.environ.get("OPENAI_API_KEY", "").strip())
        if self.name in ("dashscope", "qwen"):
            return bool(os.environ.get("DASHSCOPE_API_KEY", "").strip())
        return False

    def _make_provider(self) -> Any:
        if self.name == "openai":
            from leagent.llm.image_gen.openai import OpenAIImageGenProvider

            return OpenAIImageGenProvider(api_key=os.environ["OPENAI_API_KEY"].strip())
        from leagent.llm.image_gen.dashscope import DashScopeWanxProvider

        return DashScopeWanxProvider(api_key=os.environ["DASHSCOPE_API_KEY"].strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "image":
            return GenerationOutput.failure(kind, f"{self.name} produces only images")
        provider = self._make_provider()
        try:
            model = str(params.get("model") or ("dall-e-3" if self.name == "openai" else "wanx2.1-t2i-turbo"))
            gen_kwargs: dict[str, Any] = {}
            size = params.get("size")
            if size:
                gen_kwargs["size"] = size
            result = await provider.generate(model=model, prompt=prompt, **gen_kwargs)
            data: bytes | None = None
            if getattr(result, "b64_json", None):
                data = base64.b64decode(result.b64_json)
            if data is None and getattr(result, "url", None):
                return GenerationOutput(
                    success=True, kind="image", data=None, mime=result.mime,
                    filename="image.png", provider=self.name, model=result.model,
                    meta={"url": result.url, "revised_prompt": result.revised_prompt},
                )
            if data is None:
                return GenerationOutput.failure("image", f"{self.name} returned no image bytes")
            return GenerationOutput(
                success=True, kind="image", data=data, mime=result.mime or "image/png",
                filename="image.png", provider=self.name, model=result.model,
                meta={"revised_prompt": getattr(result, "revised_prompt", None)},
            )
        finally:
            aclose = getattr(provider, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:  # noqa: BLE001
                    logger.debug("image_provider_aclose_failed", provider=self.name)


class LocalDiffusionBackend:
    """Wrap the in-process diffusers pipeline as an image generation strategy.

    Bridges the ``image_gen.local`` domain adapter
    (:class:`leagent.llm.domain_models.diffusion.adapter.DiffusersTxt2ImgAdapter`)
    into the generation service so art nodes can select ``provider="local"``
    for self-hosted SDXL / SD checkpoints with LoRA.
    """

    name = "local"
    kinds = ("image",)

    #: Diffusion params forwarded verbatim to the adapter.
    _PASSTHROUGH = (
        "model", "negative_prompt", "width", "height", "steps",
        "cfg_scale", "seed", "scheduler", "lora", "lora_scale",
    )

    def available(self) -> bool:
        if os.environ.get("LEAGENT_DIFFUSION_ENABLED", "1").strip() == "0":
            return False
        try:
            from leagent.llm.domain_models.diffusion import diffusers_available

            return bool(diffusers_available())
        except Exception:  # noqa: BLE001 - optional extra
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
            w, h = _parse_size(params.get("size"))
            invoke_params.setdefault("width", w)
            invoke_params.setdefault("height", h)
        if "_progress" in params:
            invoke_params["_progress"] = params["_progress"]

        adapter = DiffusersTxt2ImgAdapter()
        result = await adapter.invoke(**invoke_params)
        if not getattr(result, "success", False):
            return GenerationOutput.failure("image", getattr(result, "error", None) or "local diffusion failed")
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


class HttpVideoBackend:
    """Env-gated hook for an external text/image-to-video service."""

    name = "http_video"
    kinds = ("video",)

    def available(self) -> bool:
        return bool(os.environ.get("LEAGENT_VIDEO_GEN_URL", "").strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        base_url = os.environ.get("LEAGENT_VIDEO_GEN_URL", "").strip()
        if not base_url:
            return GenerationOutput.failure("video", "video backend not configured")
        api_key = os.environ.get("LEAGENT_VIDEO_GEN_KEY", "").strip()
        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 300))))
        try:
            headers = transport.request_headers(
                {"Authorization": f"Bearer {api_key}"} if api_key else {}
            )
            client = transport.complete_client
            resp = await client.post(
                base_url,
                headers=headers,
                json={"prompt": prompt, "params": {k: v for k, v in params.items() if k != "timeout"}},
            )
            resp.raise_for_status()
            return GenerationOutput(
                success=True, kind="video", data=resp.content,
                mime=resp.headers.get("content-type", "video/mp4"),
                filename="video.mp4", provider=self.name, model=str(params.get("model") or ""),
            )
        finally:
            await transport.aclose()


class HttpMesh3DBackend:
    """Env-gated hook for an external image/text-to-3D service."""

    name = "http_mesh3d"
    kinds = ("model3d",)

    def available(self) -> bool:
        return bool(os.environ.get("LEAGENT_MESH3D_GEN_URL", "").strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        base_url = os.environ.get("LEAGENT_MESH3D_GEN_URL", "").strip()
        if not base_url:
            return GenerationOutput.failure("model3d", "3D backend not configured")
        api_key = os.environ.get("LEAGENT_MESH3D_GEN_KEY", "").strip()
        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 300))))
        try:
            headers = transport.request_headers(
                {"Authorization": f"Bearer {api_key}"} if api_key else {}
            )
            client = transport.complete_client
            resp = await client.post(
                base_url,
                headers=headers,
                json={"prompt": prompt, "image": params.get("image"),
                      "params": {k: v for k, v in params.items() if k not in ("timeout", "image")}},
            )
            resp.raise_for_status()
            return GenerationOutput(
                success=True, kind="model3d", data=resp.content,
                mime=resp.headers.get("content-type", "model/gltf-binary"),
                filename="model.glb", provider=self.name, model=str(params.get("model") or ""),
            )
        finally:
            await transport.aclose()


def _assert_backend(obj: GenerationBackend) -> GenerationBackend:
    return obj


__all__ = [
    "HttpMesh3DBackend",
    "HttpVideoBackend",
    "ImageProviderBackend",
    "LocalDiffusionBackend",
    "OfflineGenerationBackend",
]
