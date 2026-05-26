"""Generative UI tools — list components, emit validated trees and patches."""

from __future__ import annotations

import json
from typing import Any

from leagent.services.gen_ui.schema import (
    list_component_catalog,
    validate_ui_patch,
    validate_ui_tree,
)
from leagent.tools.base import BaseTool, ToolCategory, ToolContext


def _tree_string_json_decode_hint(raw: str, exc: json.JSONDecodeError) -> str:
    """Human- and model-actionable detail when the nested ``tree`` JSON string breaks."""
    pos = exc.pos if isinstance(getattr(exc, "pos", None), int) else 0
    win = 56
    start = max(0, pos - win)
    end = min(len(raw), pos + win)
    snippet = raw[start:end].replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")
    caret = max(0, pos - start)
    pointer = " " * caret + "^"
    return (
        f"{exc.msg} at line {exc.lineno} column {exc.colno} (byte {pos}). "
        "Inside string fields use \\\" for quotes and \\n for line breaks; "
        "prefer passing `tree` as a JSON object (not a quoted string) to avoid double-escaping. "
        f"Near: …{snippet}…\n{pointer}"
    )


class ListUiComponentsTool(BaseTool):
    """Return allowed generative UI component kinds and prop hints for the model."""

    name = "list_ui_components"
    description = (
        "Return the gen UI component catalog (kinds + prop hints). When `canvas_design` warrants "
        "GenUI, call `get_genui_guide` first for layout/visual polish, then call this tool before "
        "authoring any non-trivial `emit_ui_tree` payload. Read-only, no side effects."
    )
    category = ToolCategory.CANVAS
    is_read_only = True
    is_concurrency_safe = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return {
            "node_shape": '{"kind": "...", "props": { ... }, "children": [ ... ]}',
            "rules": [
                "Every component prop goes inside `props`.",
                "`children` is only for nested nodes, never strings or props.",
                "Use `nodeId` only if you want a stable id; otherwise omit "
                "(server fills).",
            ],
            "components": list_component_catalog(),
        }


class EmitUiTreeTool(BaseTool):
    """Validate a declarative UI tree; the chat stream surfaces it as a ui_tree SSE event."""

    name = "emit_ui_tree"
    description = (
        "Default canvas tool: emit a validated gen UI tree (schemaVersion 1) that renders inline in the "
        "chat stream (ui_tree). Use it for cards, dashboards, tables, alerts, weather, KPIs, and other "
        "component-based layouts when the user does not want a hosted HTML page from `canvas_publish`. "
        "Scope is governed by **`canvas_design`**: do not call for plain Q&A, onboarding, product "
        "summaries, navigation/where-to-click guidance, or anything that belongs in assistant markdown "
        "(including bullet lists). Call when the reply needs genuine component UI—charts, KPI or "
        "dashboard layouts, slide/poster-style frames, dense interactive tables, image-led sections—or "
        "when the user explicitly requests GenUI, canvas, cards, slides, or dashboards. "
        "“Lists” here means List/ListItem-style UI nodes, not markdown bullets. "
        "Schema: every node is exactly `{kind, props, children}`; all component fields "
        "(title, value, padding, variant, headers, events, …) stay inside `props`; `children` holds only "
        "nested nodes. "
        "Before substantial trees (decks, posters, multi-card layouts), call `get_genui_guide` "
        "(payload **`wire_format_and_syntax`** + **`workflow_order`**), then **must call** "
        "`list_ui_components` for exact `kind`/prop names. "
        "Tool arguments must be strict JSON—escape double quotes as \\\" and newlines as \\n inside string "
        "values. Accepts `{schemaVersion:'1', root:{...}}`, `{root:{...}}`, or a bare root object. "
        "Keep payloads compact; prefer `emit_ui_patch` for incremental updates instead of re-emitting. "
        "Pass `tree` as a JSON object when possible; a string containing the same JSON is accepted—on "
        "parse failure, fix escaping at the reported byte offset or pass an object. "
        "Actions: set `props.action` to `{type, payload}` with snake_case `type` "
        "(e.g. `{type:'send_message', payload:{content:'Summarize'}}`, "
        "`{type:'navigate', payload:{route:'/settings'}}`, "
        "`{type:'open_artifact', payload:{canvasId:'…'}}`); `actionId` alone remains supported for legacy controls."
    )
    category = ToolCategory.CANVAS
    is_read_only = True
    is_concurrency_safe = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["tree"],
            "additionalProperties": False,
            "properties": {
                "tree": {
                    "oneOf": [
                        {
                            "type": "object",
                            "description": "Preferred: parsed gen UI tree object.",
                        },
                        {
                            "type": "string",
                            "description": (
                                "Some model providers pass nested JSON as a string; "
                                "must be valid JSON for the same object shape as above."
                            ),
                        },
                    ],
                    "description": (
                        "Generative UI tree as {schemaVersion:'1', root:{...}}, {root:{...}}, "
                        "or a bare root node — as object, or as a JSON string of that object."
                    ),
                },
                "canvas_id": {"type": "string", "description": "Optional existing canvas id."},
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        tree = params.get("tree")
        if isinstance(tree, str):
            raw = tree.strip()
            if not raw:
                raise ValueError("tree string is empty")
            try:
                tree = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"tree is not valid JSON: {_tree_string_json_decode_hint(raw, exc)}"
                ) from exc
            params["tree"] = tree
        if not isinstance(tree, dict):
            raise ValueError("tree must be an object (or a JSON string of an object)")
        from leagent.tools.canvas import get_canvas_settings

        settings = get_canvas_settings()
        normalized = validate_ui_tree(
            tree,
            max_depth=settings["max_tree_depth"],
            max_nodes=settings["max_nodes_per_tree"],
        )
        return {"payload": {"tree": normalized, "canvas_id": params.get("canvas_id")}}


class EmitUiPatchTool(BaseTool):
    """Validate incremental UI patches for the ui_patch SSE event."""

    name = "emit_ui_patch"
    description = (
        "Apply incremental JSON-Patch updates (add/replace/remove) to an "
        "already-emitted gen UI tree, validated server-side. Use this instead "
        "of re-emitting the whole tree when you want to refresh a few fields."
    )
    category = ToolCategory.CANVAS
    is_read_only = True
    is_concurrency_safe = True

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["patches"],
            "properties": {
                "patches": {"type": "array"},
                "canvas_id": {"type": "string"},
                "seq": {"type": "integer"},
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        patches = params.get("patches")
        if not isinstance(patches, list):
            raise ValueError("patches must be an array")
        payload = {
            "patches": patches,
            "canvas_id": params.get("canvas_id"),
            "seq": params.get("seq"),
        }
        validate_ui_patch(payload)
        return {"payload": payload}
