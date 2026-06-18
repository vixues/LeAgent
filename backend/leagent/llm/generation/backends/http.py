"""Env-gated HTTP generation backends (video, mesh3d, vfx, upscale)."""

from __future__ import annotations

from typing import Any

from leagent.llm.generation.backends._utils import http_creds
from leagent.llm.generation.base import GenerationOutput


class HttpVideoBackend:
    """Env-gated hook for an external text/image-to-video service."""

    name = "http_video"
    kinds = ("video",)

    def available(self) -> bool:
        return bool(http_creds(self.name)[0])

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        base_url, api_key = http_creds(self.name)
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
        return bool(http_creds(self.name)[0])

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        base_url, api_key = http_creds(self.name)
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
    """Env-gated hook for an external text-to-VFX service."""

    name = "http_vfx"
    kinds = ("vfx",)

    def available(self) -> bool:
        return bool(http_creds(self.name)[0])

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        base_url, api_key = http_creds(self.name)
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
    """Env-gated hook for a dedicated super-resolution service."""

    name = "http_upscale"
    kinds = ("image",)

    def available(self) -> bool:
        return bool(http_creds(self.name)[0])

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "image":
            return GenerationOutput.failure(kind, "upscale backend produces only images")
        base_url, api_key = http_creds(self.name)
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


__all__ = [
    "HttpMesh3DBackend",
    "HttpUpscaleBackend",
    "HttpVfxBackend",
    "HttpVideoBackend",
]
