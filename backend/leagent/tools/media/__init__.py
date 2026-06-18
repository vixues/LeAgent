"""Media-generation tools (video / audio) routed through GenerationService.

These chat-callable tools share the preset/provider resolution + artifact
persistence helpers in :mod:`leagent.tools.media.base`, so chat honours the
locally configured (admin-managed) media-generation providers and presets.
"""

from __future__ import annotations

from .audio_generate import AudioGenerateTool
from .video_generate import VideoGenerateTool

__all__ = ["AudioGenerateTool", "VideoGenerateTool"]
