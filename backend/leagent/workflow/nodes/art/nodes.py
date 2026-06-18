"""First-class, composable game-art generation nodes.

Authored directly as :class:`WorkflowNode` subclasses (ComfyUI-style),
each declaring typed media sockets so they compose on the canvas:

    ImageGenNode -> (IMAGE) -> Mesh3DNode / VideoGenNode / UpscaleNode

They call the unified ``GenerationService`` through
:class:`BaseGenerationNode`; no adapter, no auto-generation factory.
"""

from __future__ import annotations

from typing import Any, ClassVar

from leagent.llm.capabilities import CapabilityContract, Modality, TaskType
from leagent.workflow.io import IO, HiddenHolder, MediaRef, NodeOutput, Schema
from leagent.workflow.nodes.art.base import BaseGenerationNode


class ImageGenNode(BaseGenerationNode):
    """Text-to-image concept / sprite generation."""

    NODE_ID = "Art.ImageGen"
    KIND = "image"
    MEDIA_OUTPUT_ID = "image"
    DISPLAY_TITLE = "Concept image"
    PROVIDERS: ClassVar[list[str]] = ["auto", "offline", "siliconflow", "openai", "dashscope"]

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Image Generation",
            category="art/generate",
            description="Generate a 2D image (concept art, sprite, texture) from a text prompt.",
            inputs=[
                *cls._base_inputs(),
                cls._preset_input(),
                IO.Image.Input(
                    id="image",
                    optional=True,
                    tooltip="Optional reference image (img2img / style reference).",
                ),
                IO.Object.Input(
                    id="camera",
                    optional=True,
                    tooltip="Camera rig from Art.CameraControl.",
                ),
                IO.Object.Input(
                    id="control",
                    optional=True,
                    tooltip="ControlNet conditioning from Art.PoseControl.",
                ),
                IO.Int.Input(id="width", optional=True, default=1024, min=64, max=2048, step=64),
                IO.Int.Input(id="height", optional=True, default=1024, min=64, max=2048, step=64),
                IO.Combo.Input(
                    id="style", optional=True, default="concept_art",
                    choices=["concept_art", "pixel_art", "isometric", "hand_painted", "realistic"],
                    tooltip="Art style hint blended into the prompt.",
                ),
            ],
            outputs=cls._base_outputs(),
            hidden=cls._base_hidden(),
            not_idempotent=True,
        )

    def input_media(self, inputs: dict[str, Any]) -> MediaRef | None:
        return MediaRef.from_dict(inputs.get("image"))

    def collect_params(self, inputs: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        w = inputs.get("width")
        h = inputs.get("height")
        if w and h:
            params["width"] = int(w)
            params["height"] = int(h)
            params["size"] = f"{int(w)}x{int(h)}"
        if inputs.get("style"):
            params["style"] = inputs["style"]
        return params


class UpscaleNode(BaseGenerationNode):
    """Image-to-image upscale / refine (composable post-process)."""

    NODE_ID = "Art.Upscale"
    KIND = "image"
    MEDIA_OUTPUT_ID = "image"
    DISPLAY_TITLE = "Upscaled image"
    PROVIDERS: ClassVar[list[str]] = ["auto", "offline", "http_upscale", "siliconflow", "openai", "dashscope"]
    REQUIRES: ClassVar[CapabilityContract] = CapabilityContract(
        task=TaskType.UPSCALE,
        inputs=frozenset({Modality.TEXT, Modality.IMAGE}),
        outputs=frozenset({Modality.IMAGE}),
    )

    @classmethod
    def _provider_input(cls) -> Any:
        return IO.Combo.Input(
            id="provider", choices=cls.provider_choices(), default="offline",
            optional=True,
            tooltip=(
                "Upscale backend (offline = credential-free demo; "
                "http_upscale = dedicated super-resolution API)."
            ),
        )

    def _resolve_preset(self, inputs: dict[str, Any], provider_arg: str | None) -> Any:
        """Only honour an *explicit* preset — never the workflow image-gen default."""
        if type(self).KIND != "image":
            return None
        pid = str(inputs.get("preset") or "").strip()
        if not pid or pid.lower() in ("auto", "none"):
            return None
        try:
            from leagent.llm.generation import get_image_gen_config

            return get_image_gen_config().get_preset(pid)
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Image Upscale / Refine",
            category="art/process",
            description="Upscale or refine an existing image asset to a higher resolution.",
            inputs=[
                IO.Image.Input(id="image", tooltip="Source image asset to upscale."),
                IO.String.Input(id="prompt", optional=True, multiline=True,
                                tooltip="Optional refinement prompt."),
                cls._provider_input(),
                cls._model_input(),
                cls._preset_input(),
                IO.Int.Input(id="scale", optional=True, default=2, min=1, max=4,
                             tooltip="Upscale factor."),
                IO.Int.Input(id="retry_count", optional=True, default=2, min=0, max=10),
                IO.String.Input(id="output", optional=True),
            ],
            outputs=cls._base_outputs(),
            hidden=cls._base_hidden(),
            not_idempotent=True,
        )

    def input_media(self, inputs: dict[str, Any]) -> MediaRef | None:
        return MediaRef.from_dict(inputs.get("image"))

    def collect_params(self, inputs: dict[str, Any]) -> dict[str, Any]:
        scale = int(inputs.get("scale") or 2)
        cond = self.input_media(inputs)
        base = 1024
        if cond is not None and cond.width:
            base = int(cond.width)
        target = min(base * scale, 2048)
        # ``scale`` lets a dedicated super-resolution backend (http_upscale /
        # Real-ESRGAN) enlarge the *source* asset; width/height drive the
        # offline floor + generative providers that re-render at higher res.
        return {
            "scale": scale,
            "width": target,
            "height": target,
            "size": f"{target}x{target}",
        }

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        if self.input_media(inputs) is None:
            return NodeOutput(
                error="Art.Upscale: missing source image — connect a generated image asset",
            )
        return await super().execute(hidden=hidden, **inputs)


class VideoGenNode(BaseGenerationNode):
    """Text/image-to-video (e.g. turntable, idle loop) generation."""

    NODE_ID = "Art.VideoGen"
    KIND = "video"
    MEDIA_OUTPUT_ID = "video"
    DISPLAY_TITLE = "Generated clip"
    PROVIDERS: ClassVar[list[str]] = ["auto", "offline", "http_video"]

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Video Generation",
            category="art/generate",
            description="Generate a short video clip (turntable / idle loop) from a prompt or image.",
            inputs=[
                *cls._base_inputs(),
                IO.Image.Input(id="image", optional=True,
                               tooltip="Optional source image for image-to-video."),
                IO.Object.Input(
                    id="camera",
                    optional=True,
                    tooltip="Camera rig from Art.CameraControl (turntable angle).",
                ),
                IO.Int.Input(id="duration", optional=True, default=3, min=1, max=15,
                             tooltip="Clip length in seconds."),
                IO.Int.Input(id="fps", optional=True, default=24, min=8, max=60),
            ],
            outputs=cls._base_outputs(),
            hidden=cls._base_hidden(),
            not_idempotent=True,
        )

    def input_media(self, inputs: dict[str, Any]) -> MediaRef | None:
        return MediaRef.from_dict(inputs.get("image"))

    def collect_params(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "duration": int(inputs.get("duration") or 3),
            "fps": int(inputs.get("fps") or 24),
        }


class Mesh3DNode(BaseGenerationNode):
    """Image/text-to-3D mesh generation (engine-ready GLB)."""

    NODE_ID = "Art.Mesh3D"
    KIND = "model3d"
    MEDIA_OUTPUT_ID = "mesh"
    DISPLAY_TITLE = "3D model"
    PROVIDERS: ClassVar[list[str]] = ["auto", "offline", "http_mesh3d"]

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="3D Model Generation",
            category="art/generate",
            description="Generate a 3D mesh (GLB) from a concept image or text prompt.",
            inputs=[
                *cls._base_inputs(),
                IO.Image.Input(id="image", optional=True,
                               tooltip="Optional concept image for image-to-3D."),
                IO.Mesh3D.Input(
                    id="mesh",
                    optional=True,
                    tooltip="Optional reference mesh for retopology / viewpoint.",
                ),
                IO.Object.Input(
                    id="camera",
                    optional=True,
                    tooltip="Camera rig from Art.CameraControl.",
                ),
                IO.Combo.Input(id="format", optional=True, default="glb",
                               choices=["glb", "gltf", "obj"],
                               tooltip="Output mesh format."),
            ],
            outputs=cls._base_outputs(),
            hidden=cls._base_hidden(),
            not_idempotent=True,
        )

    def input_media(self, inputs: dict[str, Any]) -> MediaRef | None:
        return MediaRef.from_dict(inputs.get("image"))

    def collect_params(self, inputs: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {"format": inputs.get("format") or "glb"}
        mesh = MediaRef.from_dict(inputs.get("mesh"))
        if mesh is not None:
            params["reference_mesh"] = mesh.to_dict()
        return params


class VFXGenNode(BaseGenerationNode):
    """Text-to-VFX flipbook / sprite-sheet generation (particles, FX sequences).

    Produces a single sprite-sheet image laid out as a ``cols × rows`` grid of
    animation frames, plus animation metadata (frame count, grid, fps) that an
    engine importer can use to slice and play the sequence.
    """

    NODE_ID = "Art.VFXGen"
    KIND = "vfx"
    MEDIA_OUTPUT_ID = "vfx"
    DISPLAY_TITLE = "VFX flipbook"
    PROVIDERS: ClassVar[list[str]] = ["auto", "offline", "http_vfx"]

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="VFX Generation",
            category="art/generate",
            description=(
                "Generate a VFX flipbook / sprite-sheet (particles, explosion, "
                "glow ramp) with engine-ready frame timing metadata."
            ),
            inputs=[
                *cls._base_inputs(),
                IO.Image.Input(
                    id="image",
                    optional=True,
                    tooltip="Optional reference image (style / silhouette).",
                ),
                IO.Int.Input(id="frames", optional=True, default=8, min=1, max=64,
                             tooltip="Number of animation frames."),
                IO.Int.Input(id="cols", optional=True, default=4, min=1, max=16,
                             tooltip="Columns in the sprite-sheet grid."),
                IO.Int.Input(id="fps", optional=True, default=12, min=1, max=60,
                             tooltip="Playback frames per second."),
                IO.Combo.Input(
                    id="fx_type", optional=True, default="particles",
                    choices=["particles", "explosion", "smoke", "magic", "glow"],
                    tooltip="VFX archetype hint blended into the prompt.",
                ),
            ],
            outputs=cls._base_outputs(),
            hidden=cls._base_hidden(),
            not_idempotent=True,
        )

    def input_media(self, inputs: dict[str, Any]) -> MediaRef | None:
        return MediaRef.from_dict(inputs.get("image"))

    def collect_params(self, inputs: dict[str, Any]) -> dict[str, Any]:
        frames = int(inputs.get("frames") or 8)
        cols = min(int(inputs.get("cols") or 4), frames)
        params: dict[str, Any] = {
            "frames": frames,
            "cols": cols,
            "fps": int(inputs.get("fps") or 12),
        }
        if inputs.get("fx_type"):
            params["fx_type"] = inputs["fx_type"]
        return params


ART_GENERATION_NODES: list[type[BaseGenerationNode]] = [
    ImageGenNode,
    UpscaleNode,
    VideoGenNode,
    Mesh3DNode,
    VFXGenNode,
]

__all__ = [
    "ART_GENERATION_NODES",
    "ImageGenNode",
    "Mesh3DNode",
    "UpscaleNode",
    "VFXGenNode",
    "VideoGenNode",
]
