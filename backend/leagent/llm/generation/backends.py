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

import asyncio
import base64
import os
from typing import Any

from leagent.utils.logging import get_logger

from .base import GenerationBackend, GenerationOutput
from .config import CustomProvider, get_image_gen_config
from .placeholders import (
    color_from_prompt,
    placeholder_mp4,
    silent_wav,
    solid_png,
    sprite_sheet_png,
    triangle_glb,
)

logger = get_logger(__name__)


def _http_creds(name: str) -> tuple[str, str]:
    """Resolved ``(url, key)`` for an external HTTP generation backend."""
    creds = get_image_gen_config().backend_credentials(name)
    return creds.get("url", "").strip(), creds.get("key", "").strip()


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


def _blend(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    """Linearly interpolate two RGB colours by ``t`` in ``[0, 1]``."""
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] * (1.0 - t) + b[i] * t) for i in range(3))  # type: ignore[return-value]


class OfflineGenerationBackend:
    """Always-available placeholder backend for every media kind."""

    name = "offline"
    kinds = ("image", "video", "model3d", "vfx", "audio")

    def available(self) -> bool:
        return True

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        node_tag = str(params.get("node_id") or "").strip()
        refine = params.get("refine_iteration")
        seed = f"{prompt}:{node_tag}" if node_tag else prompt
        if refine is not None:
            seed = f"{seed}:iter{refine}"
        rgb = color_from_prompt(seed)
        if kind == "image":
            w, h = _parse_size(params.get("size") or params.get("width"))
            if "width" in params and "height" in params:
                w, h = int(params["width"]), int(params["height"])
            # img2img / style-reference conditioning: blend the seed colour
            # with one derived from the reference asset so the output visibly
            # tracks its input (deterministic, testable offline behaviour).
            if (ref := params.get("image")) and isinstance(ref, dict):
                ref_seed = str(ref.get("file_id") or ref.get("src") or "ref")
                rgb = _blend(rgb, color_from_prompt(f"img2img:{ref_seed}"), 0.4)
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
                    rgb = _blend(rgb, tint, strength * 0.35)
            data = solid_png(w, h, rgb)
            extra_meta: dict[str, Any] = {"width": w, "height": h, "rgb": list(rgb), "placeholder": True}
            if params.get("camera"):
                extra_meta["camera"] = params["camera"]
            if params.get("controlnet"):
                extra_meta["controlnet"] = params["controlnet"]
            if params.get("image"):
                extra_meta["img2img"] = True
            return GenerationOutput(
                success=True, kind="image", data=data, mime="image/png",
                filename="image.png", provider=self.name, model="offline-solid",
                meta=extra_meta,
            )
        if kind == "vfx":
            frames = int(params.get("frames") or 8)
            cols = int(params.get("cols") or min(4, frames))
            fps = int(params.get("fps") or 12)
            data = sprite_sheet_png(prompt, frames=frames, cols=cols)
            rows = (frames + cols - 1) // cols
            return GenerationOutput(
                success=True, kind="vfx", data=data, mime="image/png",
                filename="vfx_sheet.png", provider=self.name, model="offline-vfx",
                meta={
                    "placeholder": True,
                    "animation": {
                        "type": "sprite_sheet",
                        "frames": frames,
                        "cols": cols,
                        "rows": rows,
                        "fps": fps,
                    },
                },
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
        if kind == "audio":
            duration = float(params.get("duration") or params.get("duration_sec") or 1.0)
            data = silent_wav(prompt, duration_sec=duration)
            return GenerationOutput(
                success=True, kind="audio", data=data, mime="audio/wav",
                filename="audio.wav", provider=self.name, model="offline-tts",
                meta={"placeholder": True, "duration_sec": duration},
            )
        return GenerationOutput.failure(kind, f"offline backend cannot produce '{kind}'")


class ImageProviderBackend:
    """Wrap an ``llm.image_gen`` provider as an image generation strategy."""

    kinds = ("image",)

    def __init__(self, name: str) -> None:
        self.name = name

    def _api_key(self) -> str:
        """Resolve the API key from the image-gen config (env-ref aware)."""
        cfg_name = "dashscope" if self.name in ("dashscope", "qwen") else self.name
        creds = get_image_gen_config().backend_credentials(cfg_name)
        return creds.get("api_key", "").strip()

    def _base_url(self) -> str:
        cfg_name = "dashscope" if self.name in ("dashscope", "qwen") else self.name
        return get_image_gen_config().backend_credentials(cfg_name).get("base_url", "").strip()

    def available(self) -> bool:
        if self.name in ("openai", "dashscope", "qwen"):
            return bool(self._api_key())
        return False

    def _make_provider(self) -> Any:
        api_key = self._api_key()
        base_url = self._base_url()
        if self.name == "openai":
            from leagent.llm.image_gen.openai import OpenAIImageGenProvider

            kwargs: dict[str, Any] = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            return OpenAIImageGenProvider(**kwargs)
        from leagent.llm.image_gen.dashscope import DashScopeWanxProvider

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return DashScopeWanxProvider(**kwargs)

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

    #: Diffusion params forwarded verbatim to the adapter. Includes img2img /
    #: ControlNet conditioning so ``Art.CameraControl`` / ``Art.PoseControl``
    #: and an upstream reference image reach the actual pipeline call.
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
        return bool(_http_creds(self.name)[0])

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        base_url, api_key = _http_creds(self.name)
        if not base_url:
            return GenerationOutput.failure("video", "video backend not configured")
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
        return bool(_http_creds(self.name)[0])

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        base_url, api_key = _http_creds(self.name)
        if not base_url:
            return GenerationOutput.failure("model3d", "3D backend not configured")
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


class HttpVfxBackend:
    """Env-gated hook for an external text-to-VFX (flipbook/particle) service."""

    name = "http_vfx"
    kinds = ("vfx",)

    def available(self) -> bool:
        return bool(_http_creds(self.name)[0])

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        base_url, api_key = _http_creds(self.name)
        if not base_url:
            return GenerationOutput.failure("vfx", "vfx backend not configured")
        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 180))))
        try:
            headers = transport.request_headers(
                {"Authorization": f"Bearer {api_key}"} if api_key else {}
            )
            resp = await transport.complete_client.post(
                base_url,
                headers=headers,
                json={"prompt": prompt, "params": {k: v for k, v in params.items() if k != "timeout"}},
            )
            resp.raise_for_status()
            frames = int(params.get("frames") or 8)
            cols = int(params.get("cols") or min(4, frames))
            return GenerationOutput(
                success=True, kind="vfx", data=resp.content,
                mime=resp.headers.get("content-type", "image/png"),
                filename="vfx_sheet.png", provider=self.name, model=str(params.get("model") or ""),
                meta={"animation": {"type": "sprite_sheet", "frames": frames, "cols": cols,
                                     "fps": int(params.get("fps") or 12)}},
            )
        finally:
            await transport.aclose()


class HttpUpscaleBackend:
    """Env-gated hook for a dedicated super-resolution service (e.g. Real-ESRGAN).

    Unlike re-generating at a higher resolution, this *super-resolves* an
    upstream image: the source asset is posted to the configured endpoint and
    the enlarged bytes are returned. Available only when its URL is set, so the
    offline floor keeps working credential-free.
    """

    name = "http_upscale"
    kinds = ("image",)

    def available(self) -> bool:
        return bool(_http_creds(self.name)[0])

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "image":
            return GenerationOutput.failure(kind, "upscale backend produces only images")
        base_url, api_key = _http_creds(self.name)
        if not base_url:
            return GenerationOutput.failure("image", "upscale backend not configured")
        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 180))))
        try:
            headers = transport.request_headers(
                {"Authorization": f"Bearer {api_key}"} if api_key else {}
            )
            resp = await transport.complete_client.post(
                base_url,
                headers=headers,
                json={
                    "image": params.get("image"),
                    "scale": params.get("scale") or 2,
                    "model": params.get("model") or "",
                },
            )
            resp.raise_for_status()
            return GenerationOutput(
                success=True, kind="image", data=resp.content,
                mime=resp.headers.get("content-type", "image/png"),
                filename="upscaled.png", provider=self.name, model=str(params.get("model") or ""),
                meta={"upscaled": True, "scale": params.get("scale") or 2},
            )
        finally:
            await transport.aclose()


class SiliconFlowImageBackend:
    """Credential-gated text-to-image backend for SiliconFlow.

    Calls SiliconFlow's OpenAI-style image endpoint
    (``/v1/images/generations``) with the Kolors / FLUX family of models.
    The endpoint returns image *URLs* (not inline bytes), so the produced
    URL is downloaded into managed bytes — the export step needs real
    bytes and SiliconFlow URLs are short-lived. Available only when
    ``SILICONFLOW_API_KEY`` is set, keeping the offline floor working
    credential-free.
    """

    name = "siliconflow"
    kinds = ("image",)

    #: Default model; override per-call via the ``model`` param.
    _DEFAULT_MODEL = "Kwai-Kolors/Kolors"
    _DEFAULT_URL = "https://api.siliconflow.cn/v1/images/generations"

    def _credentials(self) -> dict[str, str]:
        return get_image_gen_config().backend_credentials("siliconflow")

    def available(self) -> bool:
        return bool(self._credentials().get("api_key", "").strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "image":
            return GenerationOutput.failure(kind, "siliconflow produces only images")
        creds = self._credentials()
        api_key = creds.get("api_key", "").strip()
        if not api_key:
            return GenerationOutput.failure("image", "SiliconFlow API key is not configured")
        base_url = (
            creds.get("base_url", "").strip()
            or os.environ.get("SILICONFLOW_API_URL", "").strip()
            or self._DEFAULT_URL
        )
        model = str(params.get("model") or self._DEFAULT_MODEL)

        w, h = _parse_size(params.get("size") or params.get("width"), default=(1024, 1024))
        if params.get("width") and params.get("height"):
            w, h = int(params["width"]), int(params["height"])
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "image_size": f"{w}x{h}",
            "batch_size": 1,
            "num_inference_steps": int(params.get("num_inference_steps") or params.get("steps") or 20),
            "guidance_scale": float(params.get("guidance_scale") or params.get("cfg_scale") or 7.5),
        }
        if (negative := params.get("negative_prompt")):
            payload["negative_prompt"] = str(negative)
        if (seed := params.get("seed")) is not None:
            try:
                payload["seed"] = int(seed)
            except (TypeError, ValueError):
                pass
        if (ref := params.get("image")) and isinstance(ref, dict):
            ref_url = ref.get("preview_url") or ref.get("src") or ref.get("url")
            if ref_url:
                payload["image"] = str(ref_url)

        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 300))))
        try:
            headers = transport.request_headers({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            })
            client = transport.complete_client
            with transport.request_span("image_generate", model=model, provider=self.name):
                resp = await client.post(base_url, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()
            images = body.get("images") or body.get("data") or []
            url = ""
            if images and isinstance(images[0], dict):
                url = images[0].get("url") or images[0].get("b64_json") or ""
            if not url:
                return GenerationOutput.failure("image", f"siliconflow returned no image: {body}")

            meta: dict[str, Any] = {
                "url": url, "width": w, "height": h, "seed": body.get("seed"),
            }
            try:
                img_resp = await self._download_image(client, url)
                return GenerationOutput(
                    success=True, kind="image", data=img_resp.content,
                    mime=img_resp.headers.get("content-type", "image/png"),
                    filename="image.png", provider=self.name, model=model, meta=meta,
                )
            except Exception as exc:  # noqa: BLE001 - fall back to URL-by-reference
                logger.warning("siliconflow_image_download_failed", url=url, error=str(exc))
                return GenerationOutput(
                    success=True, kind="image", data=None, mime="image/png",
                    filename="image.png", provider=self.name, model=model, meta=meta,
                )
        finally:
            await transport.aclose()

    async def _download_image(self, client: Any, url: str, *, attempts: int = 3) -> Any:
        """Download a SiliconFlow temporary URL with bounded retries."""
        last_exc: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise last_exc or RuntimeError("siliconflow image download failed")


class ReplicateBackend:
    """Credential-gated image+video backend for Replicate.

    Uses the model-scoped predictions API
    (``POST /models/{owner}/{model}/predictions``) with a synchronous
    ``Prefer: wait`` hint, falling back to polling ``GET /predictions/{id}``.
    Outputs are URLs, which are downloaded into managed bytes. Available only
    when a Replicate token is configured.
    """

    name = "replicate"
    kinds = ("image", "video")

    _DEFAULT_URL = "https://api.replicate.com/v1"
    _DEFAULT_IMAGE_MODEL = "black-forest-labs/flux-schnell"
    _DEFAULT_VIDEO_MODEL = "minimax/video-01"

    def _credentials(self) -> dict[str, str]:
        return get_image_gen_config().backend_credentials("replicate")

    def available(self) -> bool:
        return bool(self._credentials().get("api_key", "").strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind not in self.kinds:
            return GenerationOutput.failure(kind, f"replicate cannot produce '{kind}'")
        creds = self._credentials()
        api_key = creds.get("api_key", "").strip()
        if not api_key:
            return GenerationOutput.failure(kind, "Replicate API token is not configured")
        base_url = (creds.get("base_url", "").strip() or self._DEFAULT_URL).rstrip("/")
        default_model = self._DEFAULT_IMAGE_MODEL if kind == "image" else self._DEFAULT_VIDEO_MODEL
        model = str(params.get("model") or default_model)

        gen_input: dict[str, Any] = {"prompt": prompt}
        if kind == "image":
            w, h = _parse_size(params.get("size") or params.get("width"), default=(1024, 1024))
            if params.get("width") and params.get("height"):
                w, h = int(params["width"]), int(params["height"])
            gen_input["aspect_ratio"] = params.get("aspect_ratio") or "1:1"
            gen_input.setdefault("width", w)
            gen_input.setdefault("height", h)
        if (ref := params.get("image")) and isinstance(ref, dict):
            ref_url = ref.get("preview_url") or ref.get("src") or ref.get("url")
            if ref_url:
                gen_input["image"] = str(ref_url)

        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 600))))
        try:
            headers = transport.request_headers({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            })
            client = transport.complete_client
            create_url = f"{base_url}/models/{model}/predictions"
            with transport.request_span(f"{kind}_generate", model=model, provider=self.name):
                resp = await client.post(create_url, headers=headers, json={"input": gen_input})
            resp.raise_for_status()
            body = resp.json()

            status = body.get("status")
            poll_url = (body.get("urls") or {}).get("get")
            attempts = 0
            while status in ("starting", "processing") and poll_url and attempts < 120:
                await asyncio.sleep(2.0)
                poll = await client.get(poll_url, headers=headers)
                poll.raise_for_status()
                body = poll.json()
                status = body.get("status")
                attempts += 1

            if status != "succeeded":
                return GenerationOutput.failure(kind, f"replicate prediction {status}: {body.get('error')}")

            output = body.get("output")
            url = ""
            if isinstance(output, list) and output:
                url = str(output[0])
            elif isinstance(output, str):
                url = output
            if not url:
                return GenerationOutput.failure(kind, f"replicate returned no output: {output}")

            mime = "image/png" if kind == "image" else "video/mp4"
            filename = "image.png" if kind == "image" else "video.mp4"
            try:
                asset = await client.get(url, follow_redirects=True)
                asset.raise_for_status()
                return GenerationOutput(
                    success=True, kind=kind, data=asset.content,
                    mime=asset.headers.get("content-type", mime),
                    filename=filename, provider=self.name, model=model,
                    meta={"url": url},
                )
            except Exception as exc:  # noqa: BLE001 - fall back to URL-by-reference
                logger.warning("replicate_download_failed", url=url, error=str(exc))
                return GenerationOutput(
                    success=True, kind=kind, data=None, mime=mime,
                    filename=filename, provider=self.name, model=model, meta={"url": url},
                )
        finally:
            await transport.aclose()


class ElevenLabsBackend:
    """Credential-gated text-to-speech (audio) backend for ElevenLabs.

    Calls ``POST /text-to-speech/{voice_id}`` and returns mp3 bytes. Available
    only when an ElevenLabs API key is configured.
    """

    name = "elevenlabs"
    kinds = ("audio",)

    _DEFAULT_URL = "https://api.elevenlabs.io/v1"
    _DEFAULT_MODEL = "eleven_multilingual_v2"
    _DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"  # Rachel (public preset voice)

    def _credentials(self) -> dict[str, str]:
        return get_image_gen_config().backend_credentials("elevenlabs")

    def available(self) -> bool:
        return bool(self._credentials().get("api_key", "").strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "audio":
            return GenerationOutput.failure(kind, "elevenlabs produces only audio")
        creds = self._credentials()
        api_key = creds.get("api_key", "").strip()
        if not api_key:
            return GenerationOutput.failure("audio", "ElevenLabs API key is not configured")
        base_url = (creds.get("base_url", "").strip() or self._DEFAULT_URL).rstrip("/")
        model = str(params.get("model") or self._DEFAULT_MODEL)
        voice = str(params.get("voice") or params.get("voice_id") or self._DEFAULT_VOICE)

        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 180))))
        try:
            headers = transport.request_headers({
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            })
            payload: dict[str, Any] = {"text": prompt, "model_id": model}
            if isinstance(params.get("voice_settings"), dict):
                payload["voice_settings"] = params["voice_settings"]
            with transport.request_span("audio_generate", model=model, provider=self.name):
                resp = await transport.complete_client.post(
                    f"{base_url}/text-to-speech/{voice}", headers=headers, json=payload,
                )
            resp.raise_for_status()
            return GenerationOutput(
                success=True, kind="audio", data=resp.content,
                mime=resp.headers.get("content-type", "audio/mpeg"),
                filename="audio.mp3", provider=self.name, model=model,
                meta={"voice": voice},
            )
        finally:
            await transport.aclose()


class ConfiguredGenerationBackend:
    """Generic, admin-registered backend driven by a :class:`CustomProvider`.

    Speaks either an OpenAI-compatible protocol (``/images/generations`` for
    image, ``/audio/speech`` for audio) or the generic LeAgent ``http_*`` JSON
    contract (POST ``{prompt, params}`` → raw media bytes), per the provider's
    declared ``protocol`` and ``kinds``.
    """

    def __init__(self, provider: CustomProvider) -> None:
        self._provider = provider
        self.name = provider.name
        self.kinds = tuple(provider.kinds)

    def _provider_config(self) -> CustomProvider:
        # Re-read so credential edits apply without rebuilding the backend.
        return get_image_gen_config().get_custom_provider(self.name) or self._provider

    def available(self) -> bool:
        provider = self._provider_config()
        if not provider.enabled:
            return False
        if not provider.resolved_base_url():
            return False
        if provider.protocol == "openai":
            return bool(provider.resolved_api_key())
        return True

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        provider = self._provider_config()
        if kind not in provider.kinds:
            return GenerationOutput.failure(kind, f"{self.name} cannot produce '{kind}'")
        base_url = provider.resolved_base_url().rstrip("/")
        if not base_url:
            return GenerationOutput.failure(kind, f"{self.name} has no base URL configured")
        api_key = provider.resolved_api_key()
        model = str(params.get("model") or (provider.models[0] if provider.models else ""))

        if provider.protocol == "openai":
            return await self._generate_openai(kind, prompt, base_url, api_key, model, params)
        return await self._generate_http(kind, prompt, base_url, api_key, model, params)

    async def _generate_openai(
        self, kind: str, prompt: str, base_url: str, api_key: str, model: str, params: dict[str, Any]
    ) -> GenerationOutput:
        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 300))))
        try:
            headers = transport.request_headers({
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json",
            })
            client = transport.complete_client
            if kind == "image":
                w, h = _parse_size(params.get("size") or params.get("width"), default=(1024, 1024))
                if params.get("width") and params.get("height"):
                    w, h = int(params["width"]), int(params["height"])
                payload: dict[str, Any] = {
                    "model": model or "dall-e-3",
                    "prompt": prompt,
                    "size": params.get("size") or f"{w}x{h}",
                    "n": 1,
                }
                resp = await client.post(f"{base_url}/images/generations", headers=headers, json=payload)
                resp.raise_for_status()
                body = resp.json()
                items = body.get("data") or []
                if items and isinstance(items[0], dict):
                    if items[0].get("b64_json"):
                        return GenerationOutput(
                            success=True, kind="image", data=base64.b64decode(items[0]["b64_json"]),
                            mime="image/png", filename="image.png", provider=self.name, model=model,
                        )
                    if items[0].get("url"):
                        url = str(items[0]["url"])
                        try:
                            asset = await client.get(url, follow_redirects=True)
                            asset.raise_for_status()
                            return GenerationOutput(
                                success=True, kind="image", data=asset.content,
                                mime=asset.headers.get("content-type", "image/png"),
                                filename="image.png", provider=self.name, model=model, meta={"url": url},
                            )
                        except Exception:  # noqa: BLE001
                            return GenerationOutput(
                                success=True, kind="image", data=None, mime="image/png",
                                filename="image.png", provider=self.name, model=model, meta={"url": url},
                            )
                return GenerationOutput.failure("image", f"{self.name} returned no image: {body}")
            if kind == "audio":
                payload = {
                    "model": model or "tts-1",
                    "input": prompt,
                    "voice": params.get("voice") or "alloy",
                }
                if params.get("response_format"):
                    payload["response_format"] = params["response_format"]
                resp = await client.post(f"{base_url}/audio/speech", headers=headers, json=payload)
                resp.raise_for_status()
                return GenerationOutput(
                    success=True, kind="audio", data=resp.content,
                    mime=resp.headers.get("content-type", "audio/mpeg"),
                    filename="audio.mp3", provider=self.name, model=model,
                )
            return GenerationOutput.failure(kind, f"{self.name} openai protocol cannot produce '{kind}'")
        finally:
            await transport.aclose()

    async def _generate_http(
        self, kind: str, prompt: str, base_url: str, api_key: str, model: str, params: dict[str, Any]
    ) -> GenerationOutput:
        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 300))))
        try:
            headers = transport.request_headers(
                {"Authorization": f"Bearer {api_key}"} if api_key else {}
            )
            resp = await transport.complete_client.post(
                base_url,
                headers=headers,
                json={
                    "kind": kind,
                    "prompt": prompt,
                    "model": model,
                    "params": {k: v for k, v in params.items() if k != "timeout"},
                },
            )
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "application/octet-stream")
            ext = {"image": "png", "video": "mp4", "audio": "mp3", "model3d": "glb", "vfx": "png"}.get(kind, "bin")
            return GenerationOutput(
                success=True, kind=kind, data=resp.content, mime=mime,
                filename=f"{kind}.{ext}", provider=self.name, model=model,
            )
        finally:
            await transport.aclose()


def _assert_backend(obj: GenerationBackend) -> GenerationBackend:
    return obj


__all__ = [
    "ConfiguredGenerationBackend",
    "ElevenLabsBackend",
    "HttpMesh3DBackend",
    "HttpUpscaleBackend",
    "HttpVfxBackend",
    "HttpVideoBackend",
    "ImageProviderBackend",
    "LocalDiffusionBackend",
    "OfflineGenerationBackend",
    "ReplicateBackend",
    "SiliconFlowImageBackend",
]
