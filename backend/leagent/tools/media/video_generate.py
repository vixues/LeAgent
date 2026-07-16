"""VideoGenerateTool — text/image-to-video via the unified GenerationService.

Routes through the locally configured providers/presets (admin-managed) so
chat honours the active media-generation settings, with a deterministic
offline placeholder when no credentials are configured.
"""

from __future__ import annotations

from typing import Any

from leagent.tools.base import BaseTool, ToolCapability, ToolCategory, ToolContext
from leagent.tools.media.base import generate_media


class VideoGenerateTool(BaseTool):
    """Generate a short video clip from a text prompt."""

    name = "video_generate"
    description = (
        "Generate a short video clip from a text prompt using a configured video "
        "generation provider (e.g. Replicate) or a deterministic offline placeholder. "
        "Routes through locally configured providers/presets. Registers the clip for "
        "preview and returns `preview_path` (`/api/v1/files/{id}/preview`) for "
        "`emit_ui_tree` Video nodes. Use for animations, B-roll, motion clips."
    )
    category = ToolCategory.MEDIA
    version = "1.0.0"
    timeout_sec = 600
    aliases = ["generate_video", "text_to_video", "create_video"]
    search_hint = "video generate clip animation motion text-to-video"
    is_concurrency_safe = True
    is_read_only = False
    capabilities = (ToolCapability.NETWORK,)
    interrupt_behavior = "cancel"
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
                    "description": "Text description of the video to generate.",
                },
                "preset": {
                    "type": "string",
                    "description": "Configured media-gen preset id (backend + model + params).",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional generation provider override (e.g. replicate, offline).",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model id (provider default when blank).",
                },
                "duration": {
                    "type": "number",
                    "description": "Target clip duration in seconds (provider-dependent).",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Optional display filename (e.g. 'ocean_wave.mp4'). "
                        "When omitted, a short name is derived from the prompt "
                        "with a unique suffix to avoid collisions."
                    ),
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional path to save the generated video.",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating video from prompt"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return await generate_media(
            context,
            kind="video",
            prompt=params["prompt"],
            preset_id=params.get("preset"),
            provider=params.get("provider"),
            model=params.get("model"),
            filename=params.get("filename"),
            output_path=params.get("output_path"),
            extra_params={"duration": params.get("duration")},
        )
