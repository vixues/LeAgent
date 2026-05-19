"""Pet speech bubble — short assistant reactions beside the chat mascot."""

from __future__ import annotations

from typing import Any

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

_PET_BUBBLE_TEXT_MAX = 120
_PET_BUBBLE_EMOJI_MAX = 16


class EmitPetBubbleTool(BaseTool):
    """Surface a short line + optional emoji in the assistant pet speech bubble (chat UI only)."""

    name = "emit_pet_bubble"
    description = (
        "Show a brief reaction in the assistant pet speech bubble next to the chat message "
        f"(max {_PET_BUBBLE_TEXT_MAX} characters). Optional emoji for emphasis. "
        "Use for light reactions or asides; keep main answers in normal assistant text."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 5
    is_read_only = True
    is_concurrency_safe = True
    search_hint = "pet mascot bubble reaction emoji chat sidebar"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["text"],
            "additionalProperties": False,
            "properties": {
                "text": {
                    "type": "string",
                    "description": f"Short line shown in the bubble (max {_PET_BUBBLE_TEXT_MAX} chars).",
                    "maxLength": _PET_BUBBLE_TEXT_MAX + 32,
                },
                "emoji": {
                    "type": "string",
                    "description": f"Optional emoji or short symbol (max {_PET_BUBBLE_EMOJI_MAX} chars).",
                    "maxLength": _PET_BUBBLE_EMOJI_MAX + 8,
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        raw_text = params.get("text")
        text = str(raw_text).strip() if raw_text is not None else ""
        if not text:
            return {"success": False, "error": "text is required"}
        if len(text) > _PET_BUBBLE_TEXT_MAX:
            text = text[:_PET_BUBBLE_TEXT_MAX]

        out: dict[str, Any] = {"success": True, "text": text}
        emoji_raw = params.get("emoji")
        if emoji_raw is not None and str(emoji_raw).strip():
            em = str(emoji_raw).strip()
            if len(em) > _PET_BUBBLE_EMOJI_MAX:
                em = em[:_PET_BUBBLE_EMOJI_MAX]
            out["emoji"] = em
        return out
