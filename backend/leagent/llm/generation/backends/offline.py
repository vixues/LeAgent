"""Deterministic offline generation floor."""

from __future__ import annotations

from typing import Any

from leagent.llm.generation.backends._utils import blend, parse_size
from leagent.llm.generation.base import GenerationOutput
from leagent.llm.generation.placeholders import (
    color_from_prompt,
    placeholder_mp4,
    silent_wav,
    solid_png,
    sprite_sheet_png,
    triangle_glb,
)


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
            w, h = parse_size(params.get("size") or params.get("width"))
            if "width" in params and "height" in params:
                w, h = int(params["width"]), int(params["height"])
            if (ref := params.get("image")) and isinstance(ref, dict):
                ref_seed = str(ref.get("file_id") or ref.get("src") or "ref")
                rgb = blend(rgb, color_from_prompt(f"img2img:{ref_seed}"), 0.4)
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
                    rgb = blend(rgb, tint, strength * 0.35)
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


__all__ = ["OfflineGenerationBackend"]
