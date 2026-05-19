"""ImageGenerateTool — model-driven image synthesis via provider abstraction.

Wraps OpenAI DALL-E (and extensible to other providers) for generating images
from text prompts. Returns base64 image data and optionally saves to disk.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

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
                    "description": "Model to use (default from settings, typically 'dall-e-3').",
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

        model = params.get("model") or self._get_default_model()
        provider = self._get_provider()

        start = time.perf_counter()

        if provider == "openai":
            result = await self._generate_openai(
                prompt=prompt,
                model=model,
                style=style,
                size=size,
                quality=quality,
                response_format=response_format,
            )
        else:
            raise ValueError(f"Unsupported image generation provider: {provider}")

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        user_owned_file = bool(write_path)

        if not write_path and context.session_id and result.get("b64_json"):
            from leagent.config.settings import get_settings

            from leagent.services.session.paths import get_session_path_registry

            sid = str(context.session_id).strip()
            dest_dir = get_session_path_registry(get_settings()).ensure_uploads_dir(sid)
            write_path = str(dest_dir / f"_genimg_{uuid4().hex}.png")

        if write_path and result.get("b64_json"):
            out = Path(write_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(base64.b64decode(result["b64_json"]))
            result["saved_path"] = str(out)
            result["output_path"] = str(out)
            result["file_size_bytes"] = out.stat().st_size

        if (
            context.session_id
            and write_path
            and Path(write_path).is_file()
            and result.get("success")
            and result.get("b64_json")
        ):
            try:
                from leagent.main import get_service_manager

                sm = get_service_manager()
                mgr = sm.session_manager if sm else None
                if mgr is not None:
                    session_uuid = UUID(str(context.session_id))
                    user_uuid = UUID(str(context.user_id)) if context.user_id else None
                    wp = Path(write_path)
                    reg = await mgr.register_external_file(
                        session_uuid,
                        user_uuid,
                        str(wp),
                        display_name=wp.name,
                    )
                    if reg:
                        fid = str(reg.get("id") or "")
                        result["file_id"] = fid
                        result["preview_path"] = f"/api/v1/files/{fid}/preview"
                        result["preview_url"] = reg.get("preview_url")
                        result["download_url"] = reg.get("download_url")
                        if not user_owned_file:
                            wp.unlink(missing_ok=True)
                        # Avoid duplicate attachment ingest via controller path hooks.
                        result.pop("saved_path", None)
                        result.pop("output_path", None)
            except (ValueError, TypeError, RuntimeError):
                logger.warning("image_generate_session_register_failed", exc_info=True)

        result["elapsed_ms"] = elapsed_ms
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

    async def _generate_openai(
        self,
        *,
        prompt: str,
        model: str,
        style: str,
        size: str,
        quality: str,
        response_format: str,
    ) -> dict[str, Any]:
        """Call OpenAI Images API."""
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise RuntimeError("openai package is required for image generation") from e

        api_key = self._get_api_key("openai")
        client = AsyncOpenAI(api_key=api_key)

        response = await client.images.generate(
            model=model,
            prompt=prompt,
            n=1,
            size=size,
            quality=quality,
            style=style,
            response_format=response_format,
        )

        image_data = response.data[0]
        result: dict[str, Any] = {
            "success": True,
            "revised_prompt": getattr(image_data, "revised_prompt", None),
        }

        if response_format == "b64_json" and image_data.b64_json:
            result["b64_json"] = image_data.b64_json
            result["mime"] = "image/png"
        elif image_data.url:
            result["url"] = image_data.url

        return result

    def _get_provider(self) -> str:
        try:
            from leagent.config.settings import get_settings
            s = get_settings()
            if hasattr(s, "image") and hasattr(s.image, "provider"):
                return s.image.provider
        except Exception:
            pass
        return "openai"

    def _get_default_model(self) -> str:
        try:
            from leagent.config.settings import get_settings
            s = get_settings()
            if hasattr(s, "image") and hasattr(s.image, "default_model"):
                return s.image.default_model
        except Exception:
            pass
        return "dall-e-3"

    def _get_api_key(self, provider: str) -> str | None:
        key = os.environ.get("OPENAI_API_KEY")
        if key:
            return key
        try:
            from leagent.config.settings import get_settings
            s = get_settings()
            if hasattr(s, "llm") and hasattr(s.llm, "openai_api_key"):
                return s.llm.openai_api_key
        except Exception:
            pass
        return None
