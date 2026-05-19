"""On-demand HTML canvas design guide for the model.

The agent calls this **before** authoring `canvas_publish(mode=html)` to fetch
the small design system shipped by the canvas preview shell — utility class
names (`wa-card`, `wa-gradient*`), design tokens (whitespace/radii/shadow),
dark-mode notes, and a reference template. Keeping this material out of the
always-on system prompt avoids spending tokens on every chat turn.
"""

from __future__ import annotations

from typing import Any

from leagent.tools.base import BaseTool, ToolCategory, ToolContext


_REFERENCE_TEMPLATE = """\
<div class="max-w-sm mx-auto">
  <div class="wa-card wa-gradient-fresh rounded-2xl p-6 text-white">
    <div class="flex justify-between items-start">
      <div>
        <p class="text-sm opacity-80">Beijing</p>
        <p class="text-5xl font-bold mt-1">23&deg;C</p>
        <p class="text-sm mt-1 opacity-90">Partly Cloudy</p>
      </div>
      <span class="text-5xl">&#x26C5;</span>
    </div>
    <div class="flex gap-4 mt-6 text-sm">
      <span>&#x1F4A7; 65%</span>
      <span>&#x1F32C; 12 km/h</span>
      <span>&#x1F321; Feels 21&deg;C</span>
    </div>
  </div>
</div>
"""


_GUIDE_PAYLOAD: dict[str, Any] = {
    "shell": (
        "The canvas HTML preview ships with Tailwind CSS (CDN), Inter font, a "
        "professional CSS reset, dark-mode via prefers-color-scheme, and a few "
        "utility classes. You only need to author the body fragment — the host "
        "wraps it in <!DOCTYPE html> and injects the assets."
    ),
    "design_principles": [
        "Generous whitespace: prefer p-6, gap-4, space-y-4 over tight layouts.",
        "Soft shadows only: shadow-sm or shadow-md, never heavy drop shadows.",
        "Rounded corners: rounded-xl or rounded-2xl on cards and containers.",
        "Professional palette: slate/gray neutrals with sky/blue accents; "
        "use gradients sparingly for hero sections.",
        "Typography: text-sm for body, text-lg/text-xl for headings, "
        "font-semibold for emphasis.",
        "Mobile-first responsive: flex/grid + gap utilities, sm:/md:/lg: breakpoints.",
        "Dark mode: pair every color with a dark: variant "
        "(bg-white dark:bg-gray-900, text-gray-900 dark:text-gray-100).",
    ],
    "shipped_utility_classes": {
        "wa-card": (
            "White card with 1px slate border, 12px radius, 20px padding, soft "
            "shadow. Auto-darkens in dark mode."
        ),
        "wa-gradient": "Linear gradient sky-500 -> indigo-500, white text.",
        "wa-gradient-warm": "Linear gradient orange-500 -> pink-500, white text.",
        "wa-gradient-fresh": "Linear gradient emerald-500 -> sky-500, white text.",
    },
    "tailwind_config": {
        "fonts": "Inter, system-ui, -apple-system, sans-serif (already loaded).",
        "primary_palette": (
            "primary-50..900 maps sky-50..900 (e.g. text-primary-600, "
            "bg-primary-100). Use this when you want the app's accent color."
        ),
        "surface_palette": (
            "surface (white), surface-elevated (white), surface-sunken "
            "(slate-100). Mirror the app's neutrals."
        ),
        "dark_mode": "Triggered by prefers-color-scheme; use dark: variants.",
    },
    "html_authoring_rules": [
        "Author a body fragment OR a full <!DOCTYPE html> document — both work. "
        "Fragments are easier; only return a full document if you actually need "
        "<head>/<style> overrides.",
        "Inline <style> is allowed and survives sanitisation. Inline <script> "
        "tags written by the model are stripped — rely on the bundled Tailwind "
        "CDN script instead.",
        "Inline event handlers (onclick=, onload=, ...) are stripped for "
        "security; do not author interactive JS.",
        "SVG and the common chart primitives (svg, path, g, circle, rect, "
        "line, polyline, polygon, ellipse, defs, linearGradient, "
        "radialGradient, stop, text, tspan) are allowed.",
        "Class and style attributes survive on every tag — Tailwind utilities "
        "render as expected.",
        "Keep payload under a few hundred KB. For very long reports, split the "
        "content or stay in gen UI.",
    ],
    "reference_template": _REFERENCE_TEMPLATE,
}


class GetHtmlCanvasGuideTool(BaseTool):
    """Return on-demand design guidance for `canvas_publish(mode=html)`."""

    name = "get_html_canvas_guide"
    description = (
        "Return the canvas HTML preview design system: shipped utility classes "
        "(wa-card, wa-gradient/wa-gradient-warm/wa-gradient-fresh), Tailwind "
        "config (Inter font, primary/surface palettes, dark mode), authoring "
        "rules (allowed tags/attributes, inline <style> ok, no <script>/on* "
        "handlers), and a reference HTML template. Call this before authoring "
        "`canvas_publish(mode=html)` so you do not have to memorise the "
        "details. Read-only, no side effects."
    )
    category = ToolCategory.CANVAS
    is_read_only = True
    is_concurrency_safe = True
    search_hint = "html canvas design guide tailwind utility classes"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return _GUIDE_PAYLOAD
