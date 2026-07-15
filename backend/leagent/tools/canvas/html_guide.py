"""On-demand HTML canvas authoring guide for the model.

The payload combines the preview runtime contract with a compact, style-neutral
quality rubric. Keeping it behind a tool avoids charging ordinary chat turns
for page-design guidance.
"""

from __future__ import annotations

from typing import Any

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

_REFERENCE_TEMPLATE = """\
<main class="min-h-screen bg-white text-zinc-950">
  <div class="mx-auto max-w-6xl px-5 py-12 sm:px-8 lg:py-20">
    <header class="max-w-3xl">
      <p class="text-sm font-medium tracking-wide text-zinc-500">
        Context label
      </p>
      <h1 class="mt-3 text-4xl font-semibold tracking-tight sm:text-6xl">
        One clear promise, expressed in the product's own voice
      </h1>
      <p class="mt-5 max-w-2xl text-base leading-7 text-zinc-600 sm:text-lg">
        A concise explanation that gives the reader enough context to act.
      </p>
    </header>

    <section aria-labelledby="details" class="mt-12 border-t border-black/10 pt-8">
      <h2 id="details" class="text-xl font-semibold tracking-tight">What matters</h2>
      <div class="mt-6 grid gap-8 md:grid-cols-3">
        <article>
          <h3 class="font-medium">Clear hierarchy</h3>
          <p class="mt-2 text-sm leading-6 text-zinc-600">
            Make the reading order obvious without decorating every block.
          </p>
        </article>
        <article>
          <h3 class="font-medium">Useful content</h3>
          <p class="mt-2 text-sm leading-6 text-zinc-600">
            Replace this example with specific, credible user-facing copy.
          </p>
        </article>
        <article>
          <h3 class="font-medium">Responsive by default</h3>
          <p class="mt-2 text-sm leading-6 text-zinc-600">
            Let the layout collapse naturally before adding extra breakpoints.
          </p>
        </article>
      </div>
    </section>
  </div>
</main>
"""


_GUIDE_PAYLOAD: dict[str, Any] = {
    "purpose": (
        "Create a complete, credible webpage whose visual language follows the "
        "content, audience, product, and any supplied brand—not a house style from "
        "this guide. Aesthetic quality should come from hierarchy, proportion, "
        "typography, alignment, restraint, and intentional detail."
    ),
    "when_to_call": [
        "Use this guide for substantial, branded, interactive, 3D, or "
        "appearance-sensitive hosted webpages, and when improving a bland first draft.",
        "Skip it for trivial HTML fragments when the preview contract and visual "
        "direction are already known.",
        "This guide is for `canvas_publish(mode=html)`. Do not assume its injected "
        "assets exist inside chat-inline `HtmlFrame`.",
    ],
    "design_method": [
        "Infer the page's job first: audience, primary action, information order, "
        "tone, and constraints. Preserve user-provided copy, assets, colors, and "
        "brand rules; do not invent a competing identity.",
        "Choose one coherent visual direction that fits that job. Default to a "
        "light surface (white / light gray background, dark text) unless the brief "
        "explicitly asks for dark mode or a nocturnal aesthetic. Do not default "
        "every page to a SaaS dashboard, centered hero, blue gradient, glassmorphism, "
        "or a grid of rounded cards.",
        "Establish the reading order before decoration: one dominant idea per "
        "viewport, clear section transitions, and a single obvious primary action "
        "when an action is needed.",
        "Use the reference template only as a structural example. Replace its "
        "layout and language when the brief calls for editorial, data-dense, "
        "luxury, playful, technical, institutional, or other treatment.",
    ],
    "visual_quality": [
        "Layout: use a small spacing scale, consistent alignment, deliberate "
        "container widths, and CSS grid/flex based on content relationships. "
        "Whitespace is structure, not empty decoration.",
        "Typography: create visible contrast between display, heading, body, and "
        "metadata roles. Keep prose comfortably readable (roughly 45–75 characters "
        "per line), use sensible line-height, and avoid excessive font weights.",
        "Color: derive semantic roles (background, surface, text, muted, accent, "
        "success/warning/error) from the brief. Check contrast; do not rely on hue "
        "alone or introduce gradients without a compositional reason.",
        "Shape and depth: borders, radii, shadows, and blur must communicate grouping "
        "or elevation. Do not round, shadow, or outline every section.",
        "Content: use specific labels and realistic values. Avoid filler, repeated "
        "headlines, ornamental badges, emoji as UI icons, and unsupported claims.",
        "Media: preserve aspect ratio, set object-fit intentionally, provide useful "
        "alt text, and make imagery support the hierarchy rather than compete with it.",
        "Motion: add only when it explains state or rewards an action; keep it subtle "
        "and honor prefers-reduced-motion. The page must remain complete with JS off.",
    ],
    "responsive_accessibility": [
        "Start with semantic HTML and a single-column mobile reading order; enhance "
        "at sm:/md:/lg: only where the content needs it. Avoid fixed widths and "
        "viewport heights that clip content.",
        "Verify 320px mobile, common tablet/desktop widths, long labels, and overflow. "
        "Controls need visible focus, keyboard operation, labels, and adequate hit areas.",
        "Use one h1, ordered headings, landmarks, native buttons/links, alt text, and "
        "ARIA only when native semantics are insufficient.",
        "The preview host defaults to a light color scheme. Prefer light pages "
        "(light backgrounds, dark text) unless the user asks for dark. Only add "
        "`dark:` variants when intentionally supporting both schemes; never leave "
        "text and backgrounds with accidental low contrast.",
    ],
    "preview_runtime": {
        "injected": (
            "Body fragments and bare full documents (no Tailwind CDN, no substantial "
            "authored stylesheet) get Tailwind CDN, Inter, a host reset/helpers with a "
            "light color-scheme default, and Three.js as `window.THREE`. Full documents "
            "that already load Tailwind or ship a substantial `<style>` / non-font "
            "stylesheet are left intact — the host does not re-inject its shell, "
            "because Preflight and body resets would clobber page-owned CSS."
        ),
        "document_shape": (
            "A body fragment and a full HTML document both work. Prefer a fragment "
            "when you want host Tailwind/wa-* helpers. Use a full document when you "
            "need your own head, fonts, or stylesheet; authored CSS is preserved."
        ),
        "javascript": (
            "Raw scripts and on* handlers are stored. The preview API defaults JS off "
            "unless `js=1`; the standard Canvas UI currently opens with its JS toggle "
            "on, and the user can turn it off. Design a useful no-JS state because "
            "sanitized previews, exports, and user settings may disable scripts. Local "
            "scripts from multi-file bundles follow the same toggle."
        ),
        "three_js": (
            "Use the preloaded `window.THREE`; do not add another Three.js script "
            "unless a specific incompatible version is required. Scene code still "
            "requires the preview JS toggle."
        ),
        "html_css_svg": (
            "Inline <style>, class/style attributes, and common SVG/chart primitives "
            "are supported. Without JS opt-in, unsafe scripts, event handlers, and "
            "javascript: URLs are removed at preview time."
        ),
    },
    "surface_matrix": {
        "hosted_canvas": (
            "`canvas_publish(mode=html)` opens a page-scale artifact in the workspace. "
            "For fragments / bare shells the host injects Tailwind, Inter, wa-* helpers, "
            "and global THREE; authored full documents keep their own CSS stack."
        ),
        "html_frame": (
            "`emit_ui_tree` with `HtmlFrame` renders arbitrary HTML inline in chat. "
            "It does not receive the hosted canvas Tailwind/Inter/wa-*/Three shell; "
            "include any required assets in the frame HTML. JS follows the GenUI toolbar."
        ),
        "three_js_frame": (
            "`emit_ui_tree` with `ThreeJsFrame` is the preferred chat-inline 3D surface "
            "when its structured geometry, material, camera, and animation props suffice; "
            "the frontend uses its installed Three.js package and manages lifecycle."
        ),
    },
    "available_shell_tokens": {
        "note": (
            "These are optional compatibility primitives, not a prescribed aesthetic. "
            "Prefer page-specific styling when the brief has its own visual language."
        ),
        "font": "Inter, system-ui, -apple-system, sans-serif.",
        "colors": (
            "primary-50..900 maps to sky; surface, surface-elevated, and "
            "surface-sunken mirror the host neutrals."
        ),
        "utilities": {
            "wa-card": "Neutral bordered surface with 12px radius, padding, and soft shadow.",
            "wa-gradient": "Sky-to-indigo gradient with white text.",
            "wa-gradient-warm": "Orange-to-pink gradient with white text.",
            "wa-gradient-fresh": "Emerald-to-sky gradient with white text.",
        },
    },
    "delivery": [
        "Compact tool-call JSON ≲~20KB (soft inline budget): `canvas_publish(html=…)`. "
        "Prefer a body fragment so the host shell applies.",
        "Larger pages (up to canvas max_html_bytes, default 4MB): "
        "`tool_argument_blob` → `html_blob_id` / `html_files_blob_id`.",
        "Active Project: `project_write` → `html_paths` "
        "(`html_bundle_entry` only if multiple HTML files lack index.html).",
        "Use short asset URLs: `/api/v1/files/{id}/preview`.",
    ],
    "quality_gate": [
        "The first viewport communicates what this is, why it matters, and what to do next.",
        "Hierarchy remains clear in grayscale and no decorative device is repeated by habit.",
        "Copy is complete, specific, and free of placeholders or implementation commentary.",
        "No clipping, horizontal overflow, broken assets, unreadable contrast, or empty controls.",
        "The page works without JS; enabled interactions have useful states and cleanup.",
        "The result visibly fits this brief rather than looking like a reusable AI template.",
    ],
    "reference_template": _REFERENCE_TEMPLATE,
}


class GetHtmlCanvasGuideTool(BaseTool):
    """Return on-demand design guidance for `canvas_publish(mode=html)`."""

    name = "get_html_canvas_guide"
    description = (
        "Return the on-demand professional HTML guide for `canvas_publish`: "
        "style-neutral design method, visual-quality and accessibility checks, "
        "preview runtime contract (Tailwind, SVG, JS toggle, global THREE), "
        "large-page delivery, optional shell utilities, and a structural template. "
        "Use for substantial or appearance-sensitive webpages; skip for trivial HTML. "
        "Read-only, no side effects."
    )
    category = ToolCategory.CANVAS
    is_read_only = True
    is_concurrency_safe = True
    search_hint = "professional html webpage canvas design accessibility tailwind guide"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        return _GUIDE_PAYLOAD
