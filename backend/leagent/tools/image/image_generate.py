"""ImageGenerateTool — model-driven image synthesis via GenerationService.

Routes through the unified
:class:`~leagent.llm.generation.GenerationService` so chat honours the
locally configured (admin-managed) providers/presets, with a deterministic
offline placeholder when no credentials are configured.
"""

from __future__ import annotations

from typing import Any

from leagent.tools.base import BaseTool, ToolCapability, ToolCategory, ToolContext
from leagent.tools.media.base import generate_media
from leagent.utils.logging import get_logger

logger = get_logger(__name__)


class ImageGenerateTool(BaseTool):
    """Generate images from text prompts using configured image models.

    Routes through the unified ``GenerationService``: a configured preset or
    provider (SiliconFlow / OpenAI / DashScope / local diffusion / custom) is
    selected, falling back to deterministic offline generation.
    """

    name = "image_generate"
    description = (
        "Generate an image from a text prompt using a configured image model. "
        "Routes through locally configured providers/presets (admin-managed). "
        "In chat sessions, registers the image for preview and returns "
        "`preview_path` (`/api/v1/files/{id}/preview`) for `emit_ui_tree` Image nodes. "
        "Use for creating illustrations, diagrams, icons, photos, artwork, "
        "or any visual content described in natural language."
    )
    category = ToolCategory.IMAGE
    version = "1.0.0"
    timeout_sec = 120
    aliases = ["generate_image", "dall_e", "text_to_image", "create_image"]
    search_hint = "image generate DALL-E create picture illustration artwork photo"
    is_concurrency_safe = True
    is_read_only = False
    capabilities = (ToolCapability.NETWORK,)
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4000,
                    "description": "Text description of the image to generate.",
                },
                "style": {
                    "type": "string",
                    "enum": ["natural", "vivid"],
                    "description": "Image style: 'natural' for realistic, 'vivid' for hyper-real/dramatic.",
                },
                "size": {
                    "type": "string",
                    "enum": ["1024x1024", "1024x1792", "1792x1024"],
                    "description": "Image dimensions (default 1024x1024).",
                },
                "quality": {
                    "type": "string",
                    "enum": ["standard", "hd"],
                    "description": "Quality level (hd uses more detail, slower).",
                },
                "model": {
                    "type": "string",
                    "description": "Image model to use (provider default when blank).",
                },
                "preset": {
                    "type": "string",
                    "description": "Configured image-gen preset id (backend + model + params).",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional image generation provider override (e.g. siliconflow, offline).",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional path to save the generated image.",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating image from prompt"

    @staticmethod
    def _size_to_wh(size: str) -> dict[str, int]:
        try:
            w, h = size.lower().split("x")
            return {"width": int(w), "height": int(h)}
        except (ValueError, AttributeError):
            return {"width": 1024, "height": 1024}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        size = params.get("size", "1024x1024")
        extra: dict[str, Any] = self._size_to_wh(size)
        extra["size"] = size
        if params.get("style"):
            extra["style"] = params["style"]
        if params.get("quality"):
            extra["quality"] = params["quality"]

        return await generate_media(
            context,
            kind="image",
            prompt=params["prompt"],
            preset_id=params.get("preset"),
            provider=params.get("provider"),
            model=params.get("model"),
            output_path=params.get("output_path"),
            extra_params=extra,
        )
