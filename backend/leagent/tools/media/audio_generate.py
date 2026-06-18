"""AudioGenerateTool — text-to-speech / audio via the unified GenerationService.

Routes through the locally configured providers/presets (admin-managed) so
chat honours the active media-generation settings, with a deterministic
silent-WAV placeholder when no credentials are configured.
"""

from __future__ import annotations

from typing import Any

from leagent.tools.base import BaseTool, ToolCapability, ToolCategory, ToolContext
from leagent.tools.media.base import generate_media


class AudioGenerateTool(BaseTool):
    """Generate speech / audio from a text prompt."""

    name = "audio_generate"
    description = (
        "Generate speech or audio from a text prompt using a configured audio "
        "generation provider (e.g. ElevenLabs / OpenAI-compatible TTS) or a "
        "deterministic offline placeholder. Routes through locally configured "
        "providers/presets. Registers the audio for preview and returns "
        "`preview_path` (`/api/v1/files/{id}/preview`) for `emit_ui_tree` Audio "
        "nodes. Use for voiceovers, narration, sound, or spoken responses."
    )
    category = ToolCategory.MEDIA
    version = "1.0.0"
    timeout_sec = 180
    aliases = ["generate_audio", "text_to_speech", "tts", "create_audio"]
    search_hint = "audio generate speech voice tts narration sound"
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
                    "maxLength": 8000,
                    "description": "Text to synthesise into speech / audio.",
                },
                "preset": {
                    "type": "string",
                    "description": "Configured media-gen preset id (backend + model + params).",
                },
                "provider": {
                    "type": "string",
                    "description": "Optional generation provider override (e.g. elevenlabs, offline).",
                },
                "model": {
                    "type": "string",
                    "description": "Optional model id (provider default when blank).",
                },
                "voice": {
                    "type": "string",
                    "description": "Optional voice id / name (provider-dependent).",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional path to save the generated audio.",
                },
            },
            "required": ["prompt"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating audio from prompt"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return await generate_media(
            context,
            kind="audio",
            prompt=params["prompt"],
            preset_id=params.get("preset"),
            provider=params.get("provider"),
            model=params.get("model"),
            output_path=params.get("output_path"),
            extra_params={"voice": params.get("voice")},
        )
