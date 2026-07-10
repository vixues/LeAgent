"""slides_generate — professional PPTX presentation generation tool.

Slides are declared as a structured list; each slide picks a layout and
carries markdown body text. Every text run gets an explicit east-Asian font
so Chinese never falls back to a Latin-only face in PowerPoint/WPS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.docgen.model import DeckSpec
from leagent.docgen.themes import list_theme_names
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


def _background_schema(desc: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "color": {"type": "string", "description": "Solid fill, '#RRGGBB'."},
            "gradient": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Two hex stops for a linear gradient.",
            },
            "gradient_angle": {
                "type": "number",
                "description": "Gradient angle in degrees (90 = top to bottom).",
            },
            "image_path": {"type": "string", "description": "Local image path (cover-cropped full-bleed)."},
            "image_url": {"type": "string", "description": "Image URL (cover-cropped full-bleed)."},
            "image_base64": {"type": "string", "description": "Base64-encoded image data (cover-cropped full-bleed)."},
            "overlay": {
                "type": "number",
                "description": "0-1 scrim opacity over a background image for text legibility (0.4-0.6 typical).",
            },
            "overlay_color": {"type": "string", "description": "Scrim color (default #000000)."},
        },
        "description": desc,
    }


def _image_schema(desc: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "url": {"type": "string"},
            "base64_data": {"type": "string"},
            "caption": {"type": "string"},
            "position": {
                "type": "string",
                "enum": ["right", "left", "top", "full", "background"],
                "description": (
                    "Where the image sits relative to body text: right/left/top "
                    "split the slide with the text, full fills the content "
                    "area, background makes it a full-bleed backdrop with a "
                    "dark scrim. Default full."
                ),
            },
            "ratio": {
                "type": "number",
                "description": "Image share of the split (0.2-0.8, default 0.5) for right/left/top.",
            },
        },
        "description": desc,
    }


class SlidesGenerateTool(SyncTool):
    """Generate .pptx presentations with themed layouts."""

    name = "slides_generate"
    description = (
        "Generate a professional PowerPoint (.pptx) presentation. Each slide "
        "picks a layout — title, section, content, two_column, columns, image, "
        "table, chart, quote, closing — and body text is markdown (multi-level "
        "bullets, numbered/task lists, bold). Consulting-grade content "
        "controls: per-slide `kicker` (eyebrow label), action `title`, "
        "`takeaway` (bottom so-what bar), `background` (solid/gradient/image "
        "with scrim), image placement (`image.position` right/left/top/full/"
        "background + `ratio`), and 2-4 headed `columns` with optional card "
        "emphasis. Body text auto-shrinks to fit — no overflow. Charts render "
        "server-side with CJK-safe fonts; 15 curated themes; speaker notes and "
        "slide numbers supported. Rule of thumb: one idea per slide, action "
        "titles that state the conclusion, and a visual on data slides. "
        "Chinese text is safe: every run carries an east-Asian font."
    )
    category = ToolCategory.GEN
    version = "1.0.0"
    timeout_sec = 240
    aliases = ["create_pptx", "create_slides", "presentation_generate", "pptx_generator"]
    search_hint = (
        "powerpoint pptx slides presentation deck generate create 演示 幻灯片 "
        "PPT 汇报 themes charts speaker notes"
    )
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        deck_themes = list_theme_names(kind="deck")
        return {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": (
                        "Bare filename for the presentation (e.g. 'deck.pptx'); "
                        "placed in the session workspace and shown in the Files tab."
                    ),
                },
                "title": {"type": "string", "description": "Deck title (auto title slide when the first slide is not layout=title)."},
                "subtitle": {"type": "string", "description": "Deck subtitle for the title slide."},
                "author": {"type": "string", "description": "Author shown on the title slide."},
                "date": {"type": "string", "description": "Date shown on the title slide."},
                "theme": {
                    "type": "string",
                    "description": f"Color theme. Built-ins: {', '.join(deck_themes)}.",
                },
                "aspect": {
                    "type": "string",
                    "enum": ["16:9", "4:3"],
                    "description": "Slide aspect ratio. Defaults to 16:9.",
                },
                "show_slide_numbers": {"type": "boolean", "description": "Show n/total in the corner (default true)."},
                "footer_text": {"type": "string", "description": "Small footer text on content slides."},
                "background": _background_schema(
                    "Deck-wide default background (per-slide `background` overrides it)."
                ),
                "slides": {
                    "type": "array",
                    "description": "Slides in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "layout": {
                                "type": "string",
                                "enum": [
                                    "title",
                                    "section",
                                    "content",
                                    "two_column",
                                    "columns",
                                    "image",
                                    "table",
                                    "chart",
                                    "quote",
                                    "closing",
                                ],
                                "description": "Slide layout. Defaults to content.",
                            },
                            "title": {
                                "type": "string",
                                "description": (
                                    "Slide title. Prefer action titles that state "
                                    "the conclusion ('Revenue doubled on APAC "
                                    "expansion'), not topics ('Revenue')."
                                ),
                            },
                            "kicker": {
                                "type": "string",
                                "description": (
                                    "Short eyebrow label above the title (e.g. "
                                    "'MARKET ANALYSIS'); rendered uppercase in "
                                    "the accent color."
                                ),
                            },
                            "subtitle": {"type": "string", "description": "Smaller line under the title."},
                            "body": {
                                "type": "string",
                                "description": (
                                    "Markdown body: multi-level bullet lists "
                                    "(indent for sub-bullets), numbered lists, "
                                    "task lists (- [x]), **bold**, short "
                                    "paragraphs, #### run-in headings. Text "
                                    "auto-shrinks to fit; still keep to 3-6 "
                                    "top-level points per slide."
                                ),
                            },
                            "takeaway": {
                                "type": "string",
                                "description": (
                                    "One-sentence so-what message shown in an "
                                    "accent-marked bar at the bottom of content/"
                                    "column/image/table/chart slides."
                                ),
                            },
                            "background": _background_schema(
                                "Per-slide background override (solid color, gradient, or image + scrim)."
                            ),
                            "left": {"type": "string", "description": "Left column markdown (two_column)."},
                            "right": {"type": "string", "description": "Right column markdown (two_column)."},
                            "columns": {
                                "type": "array",
                                "description": (
                                    "2-4 headed columns for layout=columns "
                                    "(comparisons, frameworks, option matrices)."
                                ),
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "heading": {"type": "string", "description": "Column heading."},
                                        "body": {"type": "string", "description": "Column markdown body."},
                                        "image": _image_schema("Optional image at the top of the column."),
                                        "emphasis": {
                                            "type": "boolean",
                                            "description": "Render the column as a highlighted card (recommended option).",
                                        },
                                        "width": {
                                            "type": "number",
                                            "description": "Relative width weight (default equal).",
                                        },
                                    },
                                },
                            },
                            "image": _image_schema(
                                "Slide image (layout=image, or paired with body on content slides)."
                            ),
                            "table": {
                                "type": "object",
                                "properties": {
                                    "columns": {"type": "array", "items": {"type": "string"}},
                                    "rows": {
                                        "type": "array",
                                        "items": {"type": "array", "items": {}},
                                    },
                                    "align": {
                                        "type": "array",
                                        "items": {"type": "string", "enum": ["left", "center", "right"]},
                                    },
                                },
                                "description": "Table for layout=table (or extra table on content slides).",
                            },
                            "chart": {
                                "type": "object",
                                "properties": {
                                    "chart_type": {
                                        "type": "string",
                                        "enum": ["bar", "line", "pie", "scatter", "area", "barh"],
                                    },
                                    "title": {"type": "string"},
                                    "categories": {"type": "array", "items": {"type": "string"}},
                                    "series": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "name": {"type": "string"},
                                                "values": {"type": "array", "items": {"type": "number"}},
                                            },
                                        },
                                    },
                                    "x_label": {"type": "string"},
                                    "y_label": {"type": "string"},
                                },
                                "description": "Chart for layout=chart (rendered via matplotlib, CJK-safe).",
                            },
                            "quote": {"type": "string", "description": "Quotation text (layout=quote)."},
                            "attribution": {"type": "string", "description": "Quote attribution."},
                            "notes": {"type": "string", "description": "Speaker notes."},
                        },
                    },
                },
            },
            "required": ["output_path", "slides"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating presentation"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        output_path = Path(params["output_path"])
        if output_path.suffix.lower() != ".pptx":
            output_path = output_path.with_suffix(".pptx")

        slides = params.get("slides")
        if not isinstance(slides, list) or not slides:
            raise ValueError("`slides` must be a non-empty array of slide objects.")

        deck = DeckSpec.model_validate(
            {
                "title": params.get("title") or "",
                "subtitle": params.get("subtitle"),
                "author": params.get("author"),
                "date": params.get("date"),
                "theme": params.get("theme") or "executive_light",
                "aspect": params.get("aspect") or "16:9",
                "show_slide_numbers": params.get("show_slide_numbers", True),
                "footer_text": params.get("footer_text"),
                "background": params.get("background"),
                "slides": slides,
            }
        )

        logger.info(
            "slides_generate_start",
            output_path=str(output_path),
            slides=len(deck.slides),
            theme=deck.theme,
        )

        from leagent.docgen.renderers.pptx import render_pptx

        return render_pptx(deck, output_path)
