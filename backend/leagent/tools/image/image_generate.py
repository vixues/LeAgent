"""ImageGenerateTool — model-driven image synthesis via provider abstraction.

Wraps OpenAI DALL-E (and extensible to other providers) for generating images
from text prompts. Returns base64 image data and optionally saves to disk.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from leagent.tools.base import BaseTool, ToolCapability, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class ImageGenerateTool(BaseTool):
    """Generate images from text prompts using AI image models.

    Supports OpenAI DALL-E 3 out of the box with a provider-abstraction layer
    for future backends (Stable Diffusion, Midjourney API, etc.).
    """

    name = "image_generate"
    description = (
        "Generate an image from a text prompt using an AI image model (DALL-E 3 by default). "
        "Returns base64-encoded image data and optionally saves to a file. "
        "In chat sessions, also registers the image for preview and returns "
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
                    "description": "Image model to use (default from routing.tasks.image_gen).",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional image generation provider override.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional path to save the generated image.",
                },
                "response_format": {
                    "type": "string",
                    "enum": ["b64_json", "url"],
                    "description": "Response format (default b64_json for embedding).",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating image from prompt"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        prompt = params["prompt"]
        style = params.get("style", "vivid")
        size = params.get("size", "1024x1024")
        quality = params.get("quality", "standard")
        response_format = params.get("response_format", "b64_json")
        output_path = params.get("output_path")
        write_path: str | None = output_path if isinstance(output_path, str) and output_path.strip() else None

        model = params.get("model")
        provider = params.get("provider")

        start = time.perf_counter()

        from leagent.main import get_service_manager

        sm = get_service_manager()
        llm = sm.llm_service if sm else None
        if llm is None:
            raise RuntimeError("LLM service is required for image generation")

        image_result = await llm.generate_image(
            prompt,
            provider=provider if isinstance(provider, str) and provider.strip() else None,
            model=model if isinstance(model, str) and model.strip() else None,
            size=size,
            quality=quality,
            style=style,
            response_format=response_format,
        )
        result: dict[str, Any] = {
            "success": image_result.success,
            "revised_prompt": image_result.revised_prompt,
            "model": image_result.model,
            "provider": image_result.provider,
            "mime": image_result.mime,
        }
        if image_result.b64_json:
            result["b64_json"] = image_result.b64_json
        if image_result.url:
            result["url"] = image_result.url

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        if result.get("success") and result.get("b64_json"):
            image_bytes = base64.b64decode(result["b64_json"])
            display_name = Path(write_path).name if write_path else f"image_{uuid4().hex[:8]}.png"
            try:
                from leagent.file.tool_output import register_tool_artifact

                reg = await register_tool_artifact(
                    image_bytes,
                    filename=display_name,
                    content_type=result.get("mime") or "image/png",
                    session_id=context.session_id,
                    user_id=context.user_id,
                )
            except Exception:  # noqa: BLE001
                logger.warning("image_generate_register_failed", exc_info=True)
                reg = None

            if reg:
                fid = str(reg.get("id") or "")
                result["file_id"] = fid
                result["file_size_bytes"] = reg.get("size")
                if fid:
                    result["preview_path"] = f"/api/v1/files/{fid}/preview"
                result["preview_url"] = reg.get("preview_url")
                result["download_url"] = reg.get("download_url")
                # Path scraping skips entries that already carry a file_id.
                result["output_path"] = reg.get("storage_path")

        result["elapsed_ms"] = elapsed_ms
        model = str(result.get("model") or model or "")
        provider = str(result.get("provider") or provider or "")
        result["model"] = model
        result["provider"] = provider

        logger.info(
            "image_generated",
            model=model,
            size=size,
            elapsed_ms=elapsed_ms,
            has_saved_file=bool(write_path),
        )

        return result
