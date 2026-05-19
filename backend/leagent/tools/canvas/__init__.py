"""Canvas tools — publish hosted canvas revisions and emit generative UI.

Helpers shared across canvas tool modules live here to avoid duplication.
"""

from __future__ import annotations

from typing import Any

from leagent.tools.canvas.canvas_publish import CanvasPublishTool
from leagent.tools.canvas.genui_guide import GetGenuiGuideTool
from leagent.tools.canvas.html_guide import GetHtmlCanvasGuideTool
from leagent.tools.canvas.ui_components import (
    EmitUiPatchTool,
    EmitUiTreeTool,
    ListUiComponentsTool,
)

__all__ = [
    "CanvasPublishTool",
    "EmitUiPatchTool",
    "EmitUiTreeTool",
    "GetGenuiGuideTool",
    "GetHtmlCanvasGuideTool",
    "ListUiComponentsTool",
    "get_canvas_settings",
]


def get_canvas_settings() -> dict[str, Any]:
    """Resolve canvas limits from the service manager, with safe defaults."""
    try:
        from leagent.main import get_service_manager

        sm = get_service_manager()
        if sm and sm.settings and sm.settings.canvas:
            return {
                "max_tree_depth": sm.settings.canvas.max_tree_depth,
                "max_nodes_per_tree": sm.settings.canvas.max_nodes_per_tree,
            }
    except Exception:  # noqa: BLE001
        pass
    return {"max_tree_depth": 48, "max_nodes_per_tree": 500}
