"""Generative UI tools — list components, emit validated trees and patches."""

from __future__ import annotations

import json
from typing import Any

import jsonschema

from leagent.services.gen_ui.schema import (
    list_component_catalog,
    validate_ui_patch,
    validate_ui_tree,
)
from leagent.tools.base import BaseTool, ToolCategory, ToolContext


def _tree_dict_from_parsed(parsed: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a parsed object to the gen UI tree envelope (root / schemaVersion)."""
    inner = parsed.get("tree")
    if isinstance(inner, dict) and set(parsed.keys()) <= {"tree", "canvas_id"}:
        return inner
    if "root" in parsed or "schemaVersion" in parsed:
        return parsed
    return None


def _try_parse_json_object(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object string, applying the same repair pipeline as tool-arg recovery."""
    from leagent.tools.executor import (
        _candidate_json_texts,
        _close_truncated_json_object,
        _loads_json_dict,
        _recover_emit_ui_tree_args,
        _try_json_dict_raw_decode_trailing_junk,
        _try_repair_superfluous_closing_delimiter,
    )

    text = raw.strip()
    if not text:
        return None

    if '"tree"' in text:
        recovered = _recover_emit_ui_tree_args(text)
        if recovered is not None:
            inner = recovered.get("tree")
            if isinstance(inner, dict):
                return inner

    parsers = (
        _loads_json_dict,
        _try_json_dict_raw_decode_trailing_junk,
        _try_repair_superfluous_closing_delimiter,
    )
    for candidate in _candidate_json_texts(text):
        try:
            obj, _ = json.JSONDecoder().raw_decode(candidate.strip())
            if isinstance(obj, dict):
                tree = _tree_dict_from_parsed(obj)
                if tree is not None:
                    return tree
        except json.JSONDecodeError:
            pass

        for max_del in (3, 8, 16):
            repaired = _try_repair_superfluous_closing_delimiter(
                candidate, max_deletions=max_del,
            )
            if isinstance(repaired, dict):
                tree = _tree_dict_from_parsed(repaired)
                if tree is not None:
                    return tree

        for parser in parsers:
            parsed = parser(candidate)
            if not isinstance(parsed, dict):
                continue
            tree = _tree_dict_from_parsed(parsed)
            if tree is not None:
                return tree

    if text.startswith("{") and ("schemaVersion" in text or '"root"' in text):
        for wrapped in (f'{{"tree":{text}}}', f'{{"tree": {text}}}'):
            recovered = _recover_emit_ui_tree_args(wrapped)
            if recovered is not None and isinstance(recovered.get("tree"), dict):
                return recovered["tree"]

        closed = _close_truncated_json_object(text)
        if closed is not None:
            parsed = _loads_json_dict(closed)
            if isinstance(parsed, dict):
                tree = _tree_dict_from_parsed(parsed)
                if tree is not None:
                    return tree

    return None


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
        "avoid unescaped ASCII \" inside values (use \\\" or Chinese book-title quotes 「」); "
        "prefer passing `tree` as a JSON object (not a quoted string) to avoid double-escaping. "
        f"Near: …{snippet}…\n{pointer}"
    )


class ListUiComponentsTool(BaseTool):
    """Return allowed generative UI component kinds and prop hints for the model."""

    name = "list_ui_components"
    description = (
        "Return the gen UI component catalog (kinds + prop hints). When `canvas_routing` warrants "
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
        "Scope is governed by **`canvas_routing`**: do not call for plain Q&A, onboarding, product "
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
        "`{type:'open_artifact', payload:{canvasId:'…'}}`); `actionId` alone remains supported for legacy controls. "
        "For 3D/Three.js scenes prefer **`ThreeJsFrame`** with structured props (`geometry`, `color`, "
        "`accentColor`, `particles`, `orbiters`, `quality`, optional `height`/`title`/`background`/"
        "`autoRotate`/`cameraZ`); for other arbitrary HTML/JS use **`HtmlFrame`** (`props.html`, optional "
        "`height`/`title`). HtmlFrame does not inherit the hosted canvas asset shell; scripts follow "
        "the GenUI JS toolbar (currently on by default, and user-disableable)."
    )
    category = ToolCategory.CANVAS
    is_read_only = True
    is_concurrency_safe = True

    def recover_raw_args(self, raw: str) -> dict[str, Any] | None:
        """Recover ``tree`` from malformed outer tool-call JSON (LLM nesting mistakes)."""
        from leagent.tools.executor import _recover_emit_ui_tree_args

        stripped = raw.strip()
        if not stripped:
            return None
        recovered = _recover_emit_ui_tree_args(stripped)
        if recovered is not None:
            return recovered
        tree = _try_parse_json_object(stripped)
        if tree is not None:
            return {"tree": tree}
        return None

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
            repaired = _try_parse_json_object(raw)
            if repaired is not None:
                tree = repaired
            else:
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
        "of re-emitting the whole tree when you want to refresh a few fields. "
        "Pass top-level `{patches, optional seq, optional canvas_id}` — do not "
        "nest under `payload` (that wrapper is only on the tool result). Omit "
        "`canvas_id` when unused; never pass null."
    )
    category = ToolCategory.CANVAS
    is_read_only = True
    is_concurrency_safe = True

    def recover_raw_args(self, raw: str) -> dict[str, Any] | None:
        """Recover ``patches`` from malformed outer tool-call JSON."""
        from leagent.tools.executor import _recover_emit_ui_patch_args

        stripped = raw.strip()
        if not stripped:
            return None
        recovered = _recover_emit_ui_patch_args(stripped)
        if recovered is not None:
            return recovered
        return None

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, str | None]:
        return super().validate_params(params)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["patches"],
            "additionalProperties": False,
            "properties": {
                "patches": {
                    "type": "array",
                    "minItems": 1,
                    "description": "JSON-Patch ops targeting /root/... paths.",
                },
                "canvas_id": {
                    "type": "string",
                    "description": "Optional existing canvas id; omit when unused.",
                },
                "seq": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Monotonic sequence number for ordering patches.",
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        validate_ui_patch(params)
        payload = {
            k: v
            for k, v in params.items()
            if k in ("patches", "canvas_id", "seq") and v is not None
        }
        return {"payload": payload}
