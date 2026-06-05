"""JSON Schema for declarative generative UI trees (SSE ui_tree / ui_patch)."""

from __future__ import annotations

import copy
import json
import uuid
from typing import Any

import jsonschema
from jsonschema.exceptions import ValidationError

# ---------------------------------------------------------------------------
# JSON Schema — versioned; bump schemaVersion when this contract changes.
# ---------------------------------------------------------------------------

UI_NODE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["nodeId", "kind"],
    "additionalProperties": False,
    "properties": {
        "nodeId": {"type": "string", "minLength": 1, "maxLength": 128},
        "kind": {"type": "string", "minLength": 1, "maxLength": 64},
        "props": {"type": "object"},
        "children": {"type": "array"},
    },
}

UI_TREE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["schemaVersion", "root"],
    "additionalProperties": False,
    "properties": {
        "schemaVersion": {"type": "string", "enum": ["1"]},
        "root": {"$ref": "#/$defs/node"},
    },
    "$defs": {
        "node": {
            "type": "object",
            "required": ["nodeId", "kind"],
            "additionalProperties": False,
            "properties": {
                "nodeId": {"type": "string", "minLength": 1, "maxLength": 128},
                "kind": {
                    "type": "string",
                    "enum": [
                        # Layout
                        "Stack",
                        "Grid",
                        "Row",
                        "Spacer",
                        "ScrollArea",
                        "Tabs",
                        "TabItem",
                        "Accordion",
                        "AccordionItem",
                        "AspectBox",
                        "DesignSurface",
                        # Typography & basic
                        "Text",
                        "Heading",
                        "Divider",
                        "Skeleton",
                        # Data display
                        "Badge",
                        "Tag",
                        "Stat",
                        "Progress",
                        "Avatar",
                        "Image",
                        "LiveCamera",
                        "Icon",
                        "Table",
                        "TableRow",
                        "TableCell",
                        "List",
                        "ListItem",
                        "CodeBlock",
                        "Markdown",
                        "Chart",
                        # Cards
                        "Card",
                        "WeatherCard",
                        "DataCard",
                        "MetricCard",
                        "ProfileCard",
                        "MediaCard",
                        "AlertCard",
                        "TimelineCard",
                        "SlideDeck",
                        "Slide",
                        "KpiBoard",
                        "FeatureGrid",
                        "Stepper",
                        "QuoteCard",
                        "ImageGallery",
                        "KeyValueList",
                        "SectionHeader",
                        # Interactive
                        "Button",
                        "InteractiveButton",
                        "ToggleButton",
                        "LinkButton",
                        "Input",
                        "Select",
                        "Chip",
                        "ChipGroup",
                        # Feedback
                        "Alert",
                        "Callout",
                        # Embed
                        "HostedCanvasFrame",
                        "JsonDebug",
                    ],
                },
                "props": {"type": "object"},
                "children": {"type": "array", "items": {"$ref": "#/$defs/node"}},
            },
        }
    },
}

UI_PATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["patches"],
    "additionalProperties": False,
    "properties": {
        "canvas_id": {"type": "string", "minLength": 1, "maxLength": 128},
        "seq": {"type": "integer", "minimum": 0},
        "patches": {
            "type": "array",
            "minItems": 1,
            "maxItems": 200,
            "items": {
                "type": "object",
                "required": ["op", "path"],
                "additionalProperties": False,
                "properties": {
                    "op": {"type": "string", "enum": ["add", "replace", "remove"]},
                    "path": {"type": "string", "minLength": 1, "maxLength": 512},
                    "value": {},
                },
            },
        },
    },
}

_COMPONENT_CATALOG: list[dict[str, Any]] = [
    # ── Layout ────────────────────────────────────────────────────────────
    {"kind": "Stack", "description": "Vertical flex stack container", "props": {"gap": "number", "align": "string (start|center|end|stretch)", "padding": "number"}},
    {"kind": "Grid", "description": "CSS grid layout", "props": {"columns": "number (1-6)", "gap": "number", "minChildWidth": "string (e.g. '200px')"}},
    {"kind": "Row", "description": "Horizontal flex row", "props": {"gap": "number", "align": "string (start|center|end|stretch)", "justify": "string (start|center|end|between|around)"}},
    {"kind": "Spacer", "description": "Vertical whitespace", "props": {"size": "number (px)"}},
    {"kind": "ScrollArea", "description": "Scrollable content area with max height", "props": {"maxHeight": "number (px)"}},
    {"kind": "Tabs", "description": "Tabbed content container; children must be TabItem", "props": {"defaultTab": "string (label of default active tab)"}},
    {"kind": "TabItem", "description": "Single tab pane inside Tabs", "props": {"label": "string (tab title)"}},
    {"kind": "Accordion", "description": "Expandable section container; children must be AccordionItem", "props": {}},
    {"kind": "AccordionItem", "description": "Single expandable section", "props": {"title": "string", "defaultOpen": "boolean"}},
    {
        "kind": "AspectBox",
        "description": "Fixed aspect-ratio frame for posters, slides, cards; children scale inside",
        "props": {
            "ratio": "string (16:9|4:3|1:1|3:2|85:45|210:297)",
            "maxWidth": "number (px, optional cap)",
            "rounded": "boolean",
            "overflow": "string (hidden|visible)",
        },
    },
    {
        "kind": "DesignSurface",
        "description": "Themed wrapper (poster/slide/card/editorial/minimal/brutalist/geek) for consistent gen UI styling",
        "props": {
            "preset": "string (poster|slide|card|editorial|minimal|brutalist|geek)",
            "padding": "string (none|sm|md|lg)",
        },
    },
    # ── Typography & basic ────────────────────────────────────────────────
    {"kind": "Text", "description": "Body text paragraph; value supports inline markdown such as **bold**", "props": {"value": "string", "size": "string (xs|sm|base|lg)", "color": "string (muted|default|primary|success|warning|error)", "bold": "boolean"}},
    {"kind": "Heading", "description": "Section title heading", "props": {"level": "number (1-4)", "value": "string"}},
    {"kind": "Divider", "description": "Horizontal divider line", "props": {"label": "string (optional center label)"}},
    {"kind": "Skeleton", "description": "Loading placeholder shimmer", "props": {"lines": "number", "variant": "string (text|card|avatar)"}},
    # ── Data display ──────────────────────────────────────────────────────
    {"kind": "Badge", "description": "Small status label", "props": {"value": "string", "variant": "string (default|primary|success|warning|error|info)"}},
    {"kind": "Tag", "description": "Removable tag / chip label", "props": {"label": "string", "color": "string (gray|blue|green|red|yellow|purple)"}},
    {"kind": "Stat", "description": "Key-value statistic display", "props": {"label": "string", "value": "string", "delta": "string (e.g. +12%)", "trend": "string (up|down|neutral)"}},
    {"kind": "Progress", "description": "Progress bar with percentage", "props": {"value": "number (0-100)", "label": "string", "color": "string (primary|success|warning|error)"}},
    {"kind": "Avatar", "description": "User or entity avatar", "props": {"src": "string (image URL)", "name": "string (fallback initials)", "size": "string (sm|md|lg)"}},
    {
        "kind": "Image",
        "description": "Image with URL or chat file preview path; optional lightbox and layout props",
        "props": {
            "src": "string (https URL or /api/v1/files/{uuid}/preview path)",
            "alt": "string",
            "caption": "string",
            "rounded": "boolean",
            "maxHeight": "number (px)",
            "fit": "string (cover|contain|fill)",
            "aspect": "string (optional CSS aspect-ratio e.g. '16/9')",
            "shadow": "string (none|sm|md|lg)",
            "lightbox": "boolean",
        },
    },
    {
        "kind": "LiveCamera",
        "description": (
            "Live camera preview (getUserMedia): closed by default with Open/Close/Take photo controls; "
            "stops tracks when closed or unmounted; use facingMode user|environment"
        ),
        "props": {
            "facingMode": "string (user|environment)",
            "mirrored": "boolean",
            "maxHeight": "number (px)",
            "label": "string (accessibility / caption)",
        },
    },
    {
        "kind": "Icon",
        "description": (
            "Lucide SVG icon (preferred) or emoji. Use kebab-case Lucide id as name "
            "(e.g. circle-check, sparkles, house, chart-bar) from https://lucide.dev/icons ; "
            "PascalCase (CircleCheck) also works when iconSet is lucide or auto. "
            "Set iconSet to emoji to force literal emoji/symbol."
        ),
        "props": {
            "name": "string (Lucide kebab id, PascalCase, or emoji)",
            "size": "number (px, default 20)",
            "color": "string (muted|default|primary|success|warning|error)",
            "iconSet": "string (auto|lucide|emoji) — auto uses Lucide when name matches a known slug",
            "strokeWidth": "number (optional, Lucide stroke width)",
        },
    },
    {"kind": "Table", "description": "Data table; children are TableRow", "props": {"headers": "array of string (column headers)", "striped": "boolean", "compact": "boolean"}},
    {"kind": "TableRow", "description": "Table row; children are TableCell", "props": {"highlight": "boolean"}},
    {"kind": "TableCell", "description": "Table cell", "props": {"value": "string", "align": "string (left|center|right)", "bold": "boolean"}},
    {"kind": "List", "description": "Ordered or unordered list; children are ListItem", "props": {"ordered": "boolean", "variant": "string (default|bordered|separated)"}},
    {"kind": "ListItem", "description": "Single list item", "props": {"value": "string", "icon": "string (emoji or icon name)"}},
    {"kind": "CodeBlock", "description": "Syntax-highlighted code block", "props": {"code": "string", "language": "string (python|javascript|json|sql|bash|etc)", "title": "string"}},
    {"kind": "Markdown", "description": "Rendered block markdown content", "props": {"content": "string (markdown text)", "value": "string (fallback markdown text)"}},
    {
        "kind": "Chart",
        "description": (
            "Data chart (line, bar, area, pie) with theme-aligned styling in chat; "
            "use categories + series for Cartesian charts; pie uses categories as slice labels"
        ),
        "props": {
            "chart": "string (line|bar|area|pie)",
            "title": "string (optional)",
            "categories": "array of string (x-axis or pie labels)",
            "series": "array of {name: string, values: array of number}",
            "height": "number (px, optional)",
            "stacked": "boolean (bar stack, optional)",
            "showLegend": "boolean (optional)",
            "showGrid": "boolean (optional)",
        },
    },
    # ── Rich Cards ────────────────────────────────────────────────────────
    {"kind": "Card", "description": "General-purpose bordered card container", "props": {"title": "string", "subtitle": "string", "variant": "string (default|elevated|outlined)", "padding": "string (sm|md|lg)"}},
    {
        "kind": "WeatherCard",
        "description": "Weather information card with location, temperature, condition, icon, and optional forecast",
        "props": {
            "location": "string",
            "temperature": "string (e.g. '23°C')",
            "condition": "string (e.g. 'Partly Cloudy')",
            "icon": "string (weather emoji e.g. '⛅')",
            "humidity": "string (e.g. '65%')",
            "wind": "string (e.g. '12 km/h')",
            "feelsLike": "string",
            "forecast": "array of {day: string, high: string, low: string, icon: string}",
        },
    },
    {
        "kind": "DataCard",
        "description": "Data summary card with title, value, and optional chart area (children rendered below value)",
        "props": {"title": "string", "value": "string", "description": "string", "icon": "string (emoji)"},
    },
    {
        "kind": "MetricCard",
        "description": "KPI metric card with trend indicator",
        "props": {
            "title": "string",
            "value": "string",
            "delta": "string (e.g. '+5.2%')",
            "trend": "string (up|down|neutral)",
            "period": "string (e.g. 'vs last week')",
            "icon": "string (emoji)",
        },
    },
    {
        "kind": "ProfileCard",
        "description": "User or entity profile card",
        "props": {
            "name": "string",
            "role": "string",
            "avatarUrl": "string (image URL)",
            "initials": "string (fallback)",
            "bio": "string",
            "stats": "array of {label: string, value: string}",
        },
    },
    {
        "kind": "MediaCard",
        "description": "Card with image/media header and content area",
        "props": {
            "imageUrl": "string",
            "title": "string",
            "description": "string",
            "badge": "string (optional overlay badge)",
            "aspectRatio": "string (16/9|4/3|1/1)",
        },
    },
    {
        "kind": "AlertCard",
        "description": "Prominent alert / notification card",
        "props": {
            "title": "string",
            "message": "string",
            "severity": "string (info|success|warning|error)",
            "icon": "string (emoji)",
        },
    },
    {
        "kind": "TimelineCard",
        "description": "Vertical timeline of events",
        "props": {
            "title": "string",
            "events": "array of {time: string, title: string, description: string, icon: string, status: string}",
        },
    },
    {
        "kind": "SlideDeck",
        "description": (
            "Presentation deck; children should be Slide nodes. Alternatively pass "
            "`props.slides` as an array of slide specs — each becomes a Slide when "
            "there are no Slide children yet."
        ),
        "props": {
            "title": "string",
            "aspectRatio": "string (16:9|4:3|1:1|3:2)",
            "loop": "boolean",
            "showPager": "boolean",
            "showExport": "boolean",
            "slides": (
                "optional array of slide specs {title, subtitle, content, icon, variant, children[]}; "
                "expanded to Slide nodes when there are no Slide children"
            ),
        },
    },
    {
        "kind": "Slide",
        "description": "Single slide inside SlideDeck",
        "props": {
            "eyebrow": "string",
            "title": "string",
            "subtitle": "string",
            "layout": "string (title-content|cover|two-column)",
            "variant": "string (cover|content — alias for layout when layout omitted)",
            "background": "string (primary|gradient|image)",
            "imageUrl": "string",
        },
    },
    {
        "kind": "KpiBoard",
        "description": "Responsive grid of KPI cards (typically MetricCard children)",
        "props": {"columns": "number (1-6)"},
    },
    {
        "kind": "FeatureGrid",
        "description": "Grid of feature tiles from props.items",
        "props": {
            "columns": "number (1-6)",
            "items": "array of {title, description, icon, iconTone, badge}",
        },
    },
    {
        "kind": "Stepper",
        "description": "Vertical or horizontal steps checklist",
        "props": {
            "orientation": "string (vertical|horizontal)",
            "current": "number (active step index)",
            "steps": "array of {title, description, icon, status}",
        },
    },
    {
        "kind": "QuoteCard",
        "description": "Blockquote testimonial with attribution",
        "props": {"quote": "string", "author": "string", "role": "string", "avatarUrl": "string"},
    },
    {
        "kind": "ImageGallery",
        "description": "Responsive image grid (paths from web_image_download or uploads)",
        "props": {
            "columns": "number (1-6)",
            "aspect": "string (CSS ratio e.g. 4/3)",
            "lightbox": "boolean",
            "shadow": "string (none|sm|md|lg)",
            "items": "array of {src, alt, caption, aspect}",
        },
    },
    {
        "kind": "KeyValueList",
        "description": "Two-column definition list for dense facts",
        "props": {
            "columns": "number (1-2)",
            "items": "array of {label, value, icon}",
        },
    },
    {
        "kind": "SectionHeader",
        "description": "Eyebrow + title row; optional Button children on the right",
        "props": {
            "eyebrow": "string",
            "title": "string",
            "description": "string",
            "icon": "string (lucide icon name)",
            "iconTone": "string (primary|muted|success|warning|error)",
        },
    },
    # ── Interactive ────────────────────────────────────────────────────────
    {
        "kind": "Button",
        "description": "Simple action button / chip",
        "props": {
            "label": "string",
            "actionId": "string (legacy control id)",
            "action": "object {type: string, payload?: object} preferred for chat-side handlers",
            "variant": "string (primary|secondary|ghost|danger)",
        },
    },
    {
        "kind": "InteractiveButton",
        "description": "Rich interactive button with icon and GenUi action dispatch",
        "props": {
            "label": "string",
            "actionId": "string (legacy)",
            "action": "object {type: string, payload?: object}",
            "icon": "string (emoji)",
            "variant": "string (primary|secondary|outline|ghost|danger)",
            "size": "string (sm|md|lg)",
            "tooltip": "string",
            "disabled": "boolean",
        },
    },
    {"kind": "ToggleButton", "description": "Toggle on/off button", "props": {"label": "string", "actionId": "string", "active": "boolean"}},
    {"kind": "LinkButton", "description": "Button styled as a link", "props": {"label": "string", "url": "string", "external": "boolean"}},
    {"kind": "Input", "description": "Text input field (display only in gen UI)", "props": {"label": "string", "placeholder": "string", "value": "string", "type": "string (text|email|number)"}},
    {"kind": "Select", "description": "Dropdown select (display only)", "props": {"label": "string", "options": "array of string", "value": "string"}},
    {"kind": "Chip", "description": "Compact selection chip", "props": {"label": "string", "selected": "boolean", "color": "string"}},
    {"kind": "ChipGroup", "description": "Group of selectable chips; children are Chip nodes", "props": {"label": "string"}},
    # ── Feedback ──────────────────────────────────────────────────────────
    {"kind": "Alert", "description": "Inline alert banner", "props": {"title": "string", "message": "string", "severity": "string (info|success|warning|error)", "icon": "string"}},
    {"kind": "Callout", "description": "Highlighted callout / tip / note block", "props": {"title": "string", "message": "string", "variant": "string (info|tip|warning|important)"}},
    # ── Embed ─────────────────────────────────────────────────────────────
    {"kind": "HostedCanvasFrame", "description": "Embed hosted HTML canvas by id", "props": {"canvasId": "string"}},
    {
        "kind": "HtmlFrame",
        "description": (
            "Sandboxed iframe for arbitrary HTML/JS snippets. Use when built-in "
            "GenUI components cannot express the interaction; the host preview "
            "toolbar JS toggle controls whether scripts run."
        ),
        "props": {
            "html": "string (body fragment or full document)",
            "height": "number|string (px, default 320)",
            "title": "string (iframe aria-label)",
            "allowJs": "boolean (hint only; host preview JS toggle is authoritative)",
        },
    },
    {"kind": "JsonDebug", "description": "Collapsed JSON viewer (dev/debug)", "props": {"label": "string", "data": "object"}},
]

# Single shared list for list_component_catalog() — avoid per-call allocation.
# Callers must not mutate the returned list or its dict entries.
_LIST_COMPONENT_CATALOG_CACHE: list[dict[str, Any]] = list(_COMPONENT_CATALOG)


def list_component_catalog() -> list[dict[str, Any]]:
    """Return the gen UI component catalog (shared list instance; do not mutate)."""
    return _LIST_COMPONENT_CATALOG_CACHE


_KIND_PROP_NAMES: dict[str, frozenset[str]] = {
    str(entry["kind"]): frozenset((entry.get("props") or {}).keys())
    for entry in _COMPONENT_CATALOG
}

_RESERVED_NODE_KEYS: frozenset[str] = frozenset(
    {"nodeId", "kind", "type", "props", "children"}
)


def _lift_known_flat_props(node: dict[str, Any]) -> None:
    """Move catalog-documented flat keys on ``node`` into ``node['props']``.

    The wire format requires ``{kind, props:{...}, children:[...]}``; the LLM
    occasionally emits component fields directly at the node level. We move
    *only* keys that the catalog documents as props for that ``kind``. Unknown
    flat keys are left in place so the strict schema raises a real error
    (we are not silently absorbing arbitrary garbage).
    """
    kind = node.get("kind")
    if not isinstance(kind, str):
        return
    known = _KIND_PROP_NAMES.get(kind)
    if not known:
        return
    existing = node.get("props")
    props: dict[str, Any] | None = existing if isinstance(existing, dict) else None
    lifted: dict[str, Any] | None = None
    for key in list(node.keys()):
        if key in _RESERVED_NODE_KEYS:
            continue
        if key not in known:
            continue
        if props is None and lifted is None:
            lifted = {}
        target = props if props is not None else lifted
        assert target is not None  # narrow for type-checker
        # caller-supplied props.<key> wins; do not overwrite explicit intent
        if key not in target:
            target[key] = node[key]
        del node[key]
    if lifted is not None:
        node["props"] = lifted


def _ensure_node_ids(node: dict[str, Any]) -> None:
    nid = node.get("nodeId")
    if not isinstance(nid, str) or not nid.strip():
        node["nodeId"] = uuid.uuid4().hex
    for ch in node.get("children") or []:
        if isinstance(ch, dict):
            _ensure_node_ids(ch)


def _coerce_legacy_type_to_kind(node: dict[str, Any]) -> None:
    """Models often emit ``type`` (React-style); wire format requires ``kind`` only."""
    legacy = node.pop("type", None)
    kind = node.get("kind")
    if not isinstance(kind, str) or not kind.strip():
        if isinstance(legacy, str) and legacy.strip():
            node["kind"] = legacy.strip()
    for ch in node.get("children") or []:
        if isinstance(ch, dict):
            _coerce_legacy_type_to_kind(ch)


_SIZE_TOKENS: dict[str, int] = {
    "none": 0,
    "xs": 4,
    "sm": 8,
    "md": 12,
    "base": 12,
    "lg": 16,
    "xl": 24,
    "2xl": 32,
}


def _coerce_number_token(value: Any) -> Any:
    """Coerce common model-friendly spacing/size tokens into renderer numbers."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return value
    raw = value.strip()
    if not raw:
        return value
    token = raw.lower()
    if token in _SIZE_TOKENS:
        return _SIZE_TOKENS[token]
    if token.endswith("px"):
        token = token[:-2].strip()
    try:
        parsed = float(token)
    except ValueError:
        return value
    return int(parsed) if parsed.is_integer() else parsed


def _rename_prop(props: dict[str, Any], target: str, *aliases: str) -> None:
    if target in props:
        return
    for alias in aliases:
        if alias in props:
            props[target] = props[alias]
            return


def _slide_spec_to_node(spec: Any) -> dict[str, Any] | None:
    """Turn one ``SlideDeck.props.slides[]`` entry into a ``Slide`` node."""
    if not isinstance(spec, dict):
        return None
    legacy_kind = spec.get("kind") or spec.get("type")
    if isinstance(legacy_kind, str) and legacy_kind.strip().lower() == "slide":
        node = copy.deepcopy(spec)
        node.pop("type", None)
        node["kind"] = "Slide"
        if not isinstance(node.get("props"), dict):
            node["props"] = {}
        if not isinstance(node.get("children"), list):
            node["children"] = []
        return node

    props_out: dict[str, Any] = {}
    skip_root = frozenset({"children", "content", "icon"})
    for key, val in spec.items():
        if key in skip_root:
            continue
        props_out[key] = val

    if "variant" in props_out and "layout" not in props_out:
        v = str(props_out.get("variant", "")).strip().lower()
        if v == "cover":
            props_out["layout"] = "cover"
        elif v in {"content", "default"}:
            props_out.setdefault("layout", "title-content")

    children_out: list[dict[str, Any]] = []
    icon_val = spec.get("icon")
    if icon_val is not None and str(icon_val).strip():
        children_out.append(
            {
                "kind": "Icon",
                "props": {"name": str(icon_val).strip(), "size": 48, "color": "primary"},
            }
        )
    content_val = spec.get("content")
    if isinstance(content_val, str) and content_val.strip():
        children_out.append(
            {
                "kind": "Text",
                "props": {"value": content_val.strip(), "size": "lg", "color": "muted"},
            }
        )
    raw_children = spec.get("children")
    if isinstance(raw_children, list):
        for c in raw_children:
            if isinstance(c, dict):
                children_out.append(copy.deepcopy(c))

    return {"kind": "Slide", "props": props_out, "children": children_out}


def _expand_slide_deck_slides_prop(node: dict[str, Any]) -> None:
    """Move ``props.slides`` onto ``children`` as ``Slide`` nodes when models omit ``kind``."""
    if node.get("kind") != "SlideDeck":
        return
    props = node.get("props")
    if not isinstance(props, dict):
        return
    raw_slides = props.get("slides")
    if not isinstance(raw_slides, list) or not raw_slides:
        return
    existing = node.get("children")
    ch_list: list[Any] = list(existing) if isinstance(existing, list) else []
    has_slide = any(isinstance(c, dict) and str(c.get("kind") or "") == "Slide" for c in ch_list)
    if has_slide:
        return
    built: list[dict[str, Any]] = []
    for spec in raw_slides:
        sn = _slide_spec_to_node(spec)
        if sn is not None:
            built.append(sn)
    if not built:
        return
    node["children"] = built
    del props["slides"]


def _normalize_node_props(node: dict[str, Any]) -> None:
    """Normalize common LLM prop aliases while keeping the wire schema stable."""
    _lift_known_flat_props(node)
    if node.get("kind") == "SlideDeck":
        _expand_slide_deck_slides_prop(node)
    kind = node.get("kind")
    props = node.get("props")
    if isinstance(props, dict) and isinstance(kind, str):
        if kind == "Badge":
            _rename_prop(props, "value", "text", "label")
        elif kind in {"Tag", "Chip"}:
            _rename_prop(props, "label", "text", "value")
        elif kind in {"Text", "TableCell", "ListItem"}:
            _rename_prop(props, "value", "text", "content", "label")
        elif kind == "Heading":
            _rename_prop(props, "value", "text", "title")
        elif kind == "Markdown":
            _rename_prop(props, "content", "text", "value")
        elif kind == "Image":
            _rename_prop(props, "src", "url", "imageUrl")
        elif kind == "LinkButton":
            _rename_prop(props, "url", "href")
        elif kind == "Slide":
            if "variant" in props and "layout" not in props:
                v = str(props.get("variant", "")).strip().lower()
                if v == "cover":
                    props["layout"] = "cover"
                elif v in {"content", "default"}:
                    props.setdefault("layout", "title-content")
        elif kind in {"Alert", "AlertCard", "Callout"}:
            _rename_prop(props, "message", "description", "text", "content")

        if "alignment" in props and "align" not in props:
            props["align"] = props["alignment"]
        for key in ("gap", "padding", "size", "maxHeight", "columns", "value"):
            if key in props and kind in {"Stack", "Row", "Grid", "Spacer", "ScrollArea", "Progress"}:
                props[key] = _coerce_number_token(props[key])

    for ch in node.get("children") or []:
        if isinstance(ch, dict):
            _normalize_node_props(ch)


def _looks_like_bare_root_node(d: dict[str, Any]) -> bool:
    """True when the payload is a single node dict instead of {schemaVersion, root}."""
    if "root" in d:
        return False
    return isinstance(d.get("kind"), str) or isinstance(d.get("type"), str)


def normalize_ui_tree(tree: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy with ``root`` wrapper if needed, schemaVersion, ``type``→``kind``, and nodeIds."""
    raw = copy.deepcopy(tree)
    if _looks_like_bare_root_node(raw):
        out: dict[str, Any] = {"schemaVersion": "1", "root": raw}
    else:
        out = raw
    if "schemaVersion" not in out:
        out["schemaVersion"] = "1"
    root = out.get("root")
    if isinstance(root, dict):
        _coerce_legacy_type_to_kind(root)
        _normalize_node_props(root)
        _ensure_node_ids(root)
    return out


_UI_SLOTS = frozenset({"weather", "calendar", "generic"})


def _validate_root_ui_slot(root: dict[str, Any]) -> None:
    props = root.get("props")
    if not isinstance(props, dict):
        return
    slot = props.get("uiSlot")
    if slot is None:
        return
    if not isinstance(slot, str) or slot not in _UI_SLOTS:
        allowed = ", ".join(sorted(_UI_SLOTS))
        raise ValidationError(f"root.props.uiSlot must be one of: {allowed}")


def validate_ui_tree(tree: dict[str, Any], *, max_depth: int, max_nodes: int) -> dict[str, Any]:
    normalized = normalize_ui_tree(tree)
    jsonschema.validate(instance=normalized, schema=UI_TREE_SCHEMA)
    root = normalized.get("root")
    if not isinstance(root, dict):
        raise ValidationError("root must be an object")
    n, d = _count_nodes_depth(root, 1)
    if d > max_depth:
        raise ValidationError(f"tree depth {d} exceeds max {max_depth}")
    if n > max_nodes:
        raise ValidationError(f"tree node count {n} exceeds max {max_nodes}")
    _validate_root_ui_slot(root)
    return normalized


def _count_nodes_depth(node: dict[str, Any], depth: int) -> tuple[int, int]:
    total = 1
    max_d = depth
    for ch in node.get("children") or []:
        if isinstance(ch, dict):
            sub_n, sub_d = _count_nodes_depth(ch, depth + 1)
            total += sub_n
            max_d = max(max_d, sub_d)
    return total, max_d


def validate_ui_patch(payload: dict[str, Any]) -> None:
    jsonschema.validate(instance=payload, schema=UI_PATCH_SCHEMA)


def ui_tree_from_json_bytes(raw: bytes | str) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("ui snapshot must be a JSON object")
    return data
