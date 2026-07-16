"""On-demand GenUI guide for the model — wire format, syntax, layout, and visuals.

Includes **`wire_format_and_syntax`** (schema envelope, node keys, JSON rules, patch pointers)
alongside design sections. Call **before** substantial `emit_ui_tree` payloads so trees validate
on the first attempt — without bloating the always-on system prompt.
"""

from __future__ import annotations

from typing import Any

from leagent.tools.base import BaseTool, ToolCategory, ToolContext


_GUIDE_PAYLOAD: dict[str, Any] = {
    "purpose": (
        "Ship polished, scannable gen UI: clear hierarchy, calm spacing, "
        "consistent variants — not noisy emoji decoration or flat walls of text."
    ),
    "wire_format_and_syntax": [
        "**Envelope (schemaVersion 1):** Prefer `{\"schemaVersion\":\"1\",\"root\":{...}}`. "
        "You may also emit a **bare root node** `{...}` — the server wraps it and sets `schemaVersion`. "
        "Top-level keys outside `schemaVersion`/`root` are rejected.",
        "**Node shape:** Allowed top-level keys per node: `kind`, optional `props`, optional `children`, optional `nodeId`. "
        "Component fields must live under **`props`**. The server may **lift** catalog-documented prop keys if you "
        "accidentally placed them beside `kind`; any **other** stray key on the node fails validation.",
        "**`kind`:** PascalCase string from the shipped enum only — call `list_ui_components` before "
        "authoring non-trivial trees so every planned kind/prop is grounded in the shipped catalog. "
        "Legacy **`type`** is accepted once and coerced to **`kind`** (prefer `kind` in new trees).",
        "**`nodeId`:** Optional; omit or leave empty and the server assigns stable ids. Supply ids only when you need "
        "deterministic `emit_ui_patch` targets.",
        "**`props`:** All component configuration lives here (`title`, `value`, `chart`, `categories`, `series`, …). "
        "`children` holds **only** nested node objects — never raw text lines.",
        "**Aliases normalized server-side** (still prefer canonical names): Heading `value`|`text`|`title`; "
        "Text/ListItem/TableCell `value`|`text`|`content`|`label`; Markdown `content`|`text`|`value`; "
        "Image `src`|`url`|`imageUrl`; LinkButton `href`|`url`; Badge `value`|`text`|`label`; Tag/Chip `label`|`text`|`value`; "
        "Alert-family `message`|`description`|`text`|`content`.",
        "**SlideDeck:** You may put slide specs in `props.slides` **or** real `Slide` children; if both are missing "
        "structure, prefer explicit `Slide` children for clarity.",
        "**Root slot:** If you set `root.props.uiSlot`, it must be exactly one of: `weather`, `calendar`, `generic`.",
        "**Tool args / result:** `emit_ui_tree({ \"tree\": <envelope or bare root>, \"canvas_id\"?: \"…\" })` "
        "— args and tool result use the same top-level keys (never wrap in `payload`).",
        "**Strict JSON in tool arguments:** One JSON object per tool call — no markdown fences or commentary. "
        "Pass **`tree` as a nested JSON object** when possible (not a giant escaped string). Inside strings, escape "
        "`\"` as `\\\"` and newlines as `\\n`.",
        "**`emit_ui_patch`:** Top-level `{ \"patches\": [ {\"op\":\"add|replace|remove\", \"path\":\"/json/pointer\", "
        "\"value\": ... } ] }` — same keys on the tool result. Paths use RFC 6901 pointers into the normalized tree "
        "(e.g. `/root/children/0/props/value`). `remove` has no `value`. Keep patches small.",
    ],
    "when_to_call": [
        "Do **not** open this guide just to polish a normal chat answer — onboarding, feature lists, "
        "and navigation tips belong in markdown (see canvas_routing / emit_ui_tree scope).",
        "Dashboards, multi-card layouts, posters/slides, or any tree with more than ~6 nodes.",
        "Whenever the user cares about appearance (report, deck preview, landing-style card).",
        "After scope drift: if an earlier attempt looked cluttered, re-read this guide then simplify.",
    ],
    "layout_structure": [
        "Wrap the entire visual in **`DesignSurface`** with one `preset`: `minimal` or `editorial` "
        "for professional docs; `slide` or `poster` for decks/posters; `card` for compact tiles; "
        "`geek` for terminal/cyber/code-oriented dashboards; `brutalist` only when the user asks "
        "for raw/high-contrast styling.",
        "Use **`Stack`** (vertical) or **`Grid`** for layout; set gap implicitly via child "
        "**`Card`/`Spacer`** — avoid deep nesting of more than 3–4 levels where a flatter "
        "`Grid` + `Card` list is clearer.",
        "One primary **focal point** per block: a single `Heading` (level 1–2) or hero "
        "`Image`/`AspectBox`, then supporting `Text`/`Stat`/`Table` — do not compete with two "
        "equally loud headings in the same card.",
        "For fixed frames (slide, hero, certificate), use **`AspectBox`** with an explicit `ratio` "
        "and put content inside; do not stretch images without `fit` (`cover`/`contain`).",
    ],
    "typography": [
        "Use **`Heading`** for section titles; use **`Text`** for body. Prefer `Text` "
        "`size` `sm` or `base` and `color` `muted` for secondary lines — not a second full-size heading.",
        "Do not put long paragraphs in `Heading`. For lists, use **`List`** + **`ListItem`**, not "
        "multiple `Text` nodes with manual bullet characters unless you need a one-off line.",
        "Maximum **one** `Heading` level 1 per tree root unless building a long-form doc with clear sections.",
    ],
    "spacing_and_density": [
        "Prefer **`Card`** `padding` `md` (or `lg` for hero cards). Align siblings: if one card "
        "uses `padding='md'`, nearby cards should match.",
        "Leave breathing room: group related items in one `Card` or `Stack` instead of many tiny "
        "borderless `Text` siblings.",
        "Tables: keep column counts reasonable; truncate labels in `props` rather than stuffing "
        "overflow text into `Markdown` inside cells unless necessary.",
    ],
    "emoji_and_icons": [
        "**Default to Lucide `Icon`** for UI affordances (status, trend, category): "
        "`props.name` kebab-case from lucide.dev (e.g. `trending-up`, `cloud-rain`, `sparkles`).",
        "Use **`iconSet: emoji`** on `Icon` only when the user explicitly wants emoji, or for "
        "lightweight weather/reaction chips — not for every bullet in a list.",
        "Do **not** decorate headings, every stat row, or every list item with emoji. "
        "If you use emoji at all, **at most one** decorative emoji per card/section unless the user asks for playful tone.",
        "Avoid mixing many unrelated emoji in one tree (reads as spam). Prefer a coherent small set.",
        "For **`WeatherCard`** / forecast rows, short emoji or icons are acceptable; keep the rest of the UI restrained.",
    ],
    "color_and_semantics": [
        "Use **`Badge`** / **`Tag`** / **`Stat`** variants (`success`, `warning`, `error`, `info`) "
        "for meaning — do not encode state only with random emoji.",
        "Charts: pass clean `categories` and `series`; prefer **`Chart`** for standard plots over "
        "screenshots unless the user needs a custom viz.",
    ],
    "formatting_and_json": [
        "Keep trees small; prefer **`emit_ui_patch`** for tiny follow-ups instead of resending the full tree.",
        "If validation fails, cross-check each `kind`/prop against **`list_ui_components`** and adjust — preserve the layout intent.",
    ],
    "workflow_order": [
        "1. Confirm **`canvas_routing`** allows GenUI for this turn.",
        "2. **Required before non-trivial trees:** call `list_ui_components` to verify every `kind` and prop shape you plan to use.",
        "3. Build **`emit_ui_tree`** args using **`wire_format_and_syntax`** above (valid envelope + nodes first).",
        "4. Re-read **`layout_structure`**/**`typography`**/**`emoji_and_icons`** below if the tree is non-trivial — simplify before emitting.",
        "5. **`emit_ui_tree`** with a minimal valid tree; follow up with **`emit_ui_patch`** only for small deltas.",
    ],
    "custom_javascript": [
        "Prefer built-in GenUI components and `props.action` dispatch for chat-side handlers.",
        "For 3D / WebGL / Three.js scenes, use **`ThreeJsFrame`** with structured props: "
        "`geometry` (icosahedron|octahedron|dodecahedron|tetrahedron|sphere|box|torus-knot), "
        "`color`, `accentColor`, `background`, `particles`, `orbiters`, `wireframe`, `quality`, "
        "`height`, `cameraZ`, `rotateSpeed`. The frontend renders it with the installed Three.js "
        "package, resource cleanup, DPR caps, resize handling, and viewport pausing. Prefer these "
        "props over `sceneScript`; `sceneScript` is treated as a legacy hint only.",
        "When you need arbitrary HTML/JS (custom widgets, third-party snippets), use **`HtmlFrame`** "
        "with `props.html` (fragment or full document). It does not receive the hosted canvas "
        "Tailwind/Inter/Three.js shell. Scripts run in a sandboxed iframe while the GenUI JS toggle "
        "is on (currently the UI default; the user can disable it).",
        "Do not try to inject `<script>` into other component kinds — use `ThreeJsFrame` or `HtmlFrame`.",
    ],
    "anti_patterns": [
        "Invalid `kind` strings (snake_case, lowercase, or invented component names) — must match `list_ui_components` exactly.",
        "Random keys on a node (e.g. `title` beside `kind` without being in that component's catalog props) — put them under `props`.",
        "Emoji prefix on every line or heading.",
        "Flat sequence of 10+ peer nodes with no `Card`/`Stack`/`Grid` grouping.",
        "Multiple gradients, presets, or competing hero images in one message.",
        "Using `Markdown` as a dump for unstructured prose when `List`, `Table`, or `Card` would scan better.",
    ],
}


class GetGenuiGuideTool(BaseTool):
    """Return on-demand GenUI layout and visual-design guidance."""

    name = "get_genui_guide"
    description = (
        "Return the GenUI guide: **wire_format_and_syntax** (schema envelope, node shape, JSON rules, "
        "`emit_ui_patch` pointers), **workflow_order** (valid tree first, then polish), plus layout "
        "(DesignSurface, Stack/Grid, AspectBox), typography, emoji vs Lucide icons, semantic variants, "
        "and anti-patterns. Call before non-trivial **`emit_ui_tree`** (dashboards, decks, posters, "
        "multi-card UIs). After this guide, call **`list_ui_components`** before authoring non-trivial "
        "`emit_ui_tree` payloads. Read-only, no side effects."
    )
    category = ToolCategory.CANVAS
    is_read_only = True
    is_concurrency_safe = True
    search_hint = "gen ui schema syntax wire format emit_ui_tree emit_ui_patch json pointer"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return _GUIDE_PAYLOAD
