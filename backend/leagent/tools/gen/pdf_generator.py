"""PDF Generator Tool - Create PDF documents programmatically.

Uses reportlab for creating PDF files with text, tables, images, and styling.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext
from leagent.utils.cjk_font_discovery import discover_cjk_font_file

logger = structlog.get_logger(__name__)


def _as_paragraph_text(value: Any) -> str:
    """ReportLab ``Paragraph`` requires string-like text; models may pass numbers."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _normalize_table_rows(rows: list[Any]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            out.append([_as_paragraph_text(row)])
        else:
            out.append([_as_paragraph_text(c) for c in row])
    return out


def _inject_soft_breaks(text: str, max_token_len: int = 24) -> str:
    """Insert zero-width breakpoints in long unspaced tokens."""
    token_pat = re.compile(r"[A-Za-z0-9_./:@#%%+\-]{%d,}" % max_token_len)

    def _chunk(token: str) -> str:
        return "\u200b".join(
            token[i : i + max_token_len] for i in range(0, len(token), max_token_len)
        )

    return token_pat.sub(lambda m: _chunk(m.group(0)), text)


def _header_footer_to_dict(value: Any) -> dict[str, Any]:
    """LLMs sometimes send JSON strings; direct calls may pass plain text."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("{"):
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                return {"text": value}
            return parsed if isinstance(parsed, dict) else {}
        if s:
            return {"text": s}
    return {}


def _find_existing_path(candidates: list[str]) -> str | None:
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _ttc_subfont_sequence(path: str, is_bold: bool) -> list[Any]:
    """ReportLab: ``.ttc`` is a font collection; index 0 is often *not* Simplified Chinese.

    Try SC/TW/JP name hints first, then numeric indices. ``wqy``/``droid``/``arphic`` usually
    work with index ``0``.
    """
    p = path.lower()
    w = "Bold" if is_bold else "Regular"
    names: list[str] = [f"NotoSansCJKsc-{w}", f"NotoSansCJKtc-{w}", f"NotoSansCJKjp-{w}"]
    if "sourcehansans" in p or "source-han" in p or "adobe" in p:
        names = [f"SourceHanSansSC-{w}"] + names
    if "msyh" in p or "microsoft yahei" in p:
        names = [0, "MSYH", "MicrosoftYaHei", "Microsoft YaHei"] + names
    # Noto CJK TTC collections often expose many subfont indices (far beyond 0-7).
    # Probe a wider range so we can find the SC face even when index layout differs by distro.
    index_probe = list(range(64))
    if any(x in p for x in ("wqy", "droid", "arphic", "ukai", "uming", "microhei", "zenhei")):
        return [0, 1, 2, *names, *index_probe]
    return [*names, *index_probe]


def _register_ttf(
    pdfmetrics: Any,
    ttfont_cls: Any,
    internal_name: str,
    path: str,
    *,
    is_bold: bool,
    subfont_override: str | int | None = None,
) -> bool:
    if not path or not Path(path).is_file():
        return False
    try:
        pdfmetrics.getFont(internal_name)
        return True
    except Exception:
        pass
    p = path.lower()
    if not p.endswith(".ttc") and not p.endswith((".otf", ".ttf", ".TTF", ".OTF", ".TTC")):
        return False
    # Standalone TTF/OTF
    if not p.endswith(".ttc"):
        try:
            pdfmetrics.registerFont(ttfont_cls(internal_name, path))
            return True
        except Exception:
            return False
    # TTC: must pick the correct subfont; wrong index => tofu / missing Han glyphs.
    sequence: list[Any] = [subfont_override] if subfont_override is not None else []
    for sub in _ttc_subfont_sequence(path, is_bold):
        if sub in sequence:
            continue
        sequence.append(sub)
    for sub in sequence:
        if sub is None:
            continue
        try:
            pdfmetrics.registerFont(
                ttfont_cls(internal_name, path, subfontIndex=sub)  # type: ignore[call-arg]
            )
            logger.info(
                "pdf_cjk_ttc_subfont",
                name=internal_name,
                path=path,
                subfont_index=sub,
            )
            return True
        except Exception:
            continue
    return False


def _norm_ttc_subfont(x: Any) -> str | int | None:
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return int(x)
    s = str(x).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    return s


def _setup_cjk_fonts(
    pdfmetrics: Any, ttfont_cls: Any, params: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    """Register embedded TTF/OTF/TTC and return (regular_name, bold_name, meta)."""
    reg_name = "LeAgentCJK"
    b_name = "LeAgentCJKBold"
    font_regular: str = "Helvetica"
    font_bold: str = "Helvetica-Bold"
    meta: dict[str, Any] = {
        "regular_path": None,
        "bold_path": None,
    }

    env_r = os.environ.get("LEAGENT_CJK_FONT", "").strip()
    env_b = os.environ.get("LEAGENT_CJK_FONT_BOLD", "").strip()
    p_r = (str(params.get("cjk_font_path") or env_r) or "").strip()
    p_b = (str(params.get("cjk_bold_font_path") or env_b) or "").strip()
    if p_r and not Path(p_r).is_file():
        logger.warning("cjk_font_path_not_found", path=p_r)
        p_r = ""
    if p_b and not Path(p_b).is_file():
        logger.warning("cjk_bold_font_path_not_found", path=p_b)
        p_b = ""

    reg_candidates: list[str] = []
    if p_r:
        reg_candidates.append(p_r)
    reg_candidates.extend(
        [
            f"{Path.home()}/.local/share/fonts/NotoSansSC-Regular.otf",
            f"{Path.home()}/.local/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
            "/usr/share/fonts/opentype/noto/NotoSansCJKSC-Regular.otf",
            "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]
    )
    discovered_r = discover_cjk_font_file(is_bold=False)
    if discovered_r:
        reg_candidates.append(discovered_r)

    bold_candidates: list[str] = []
    if p_b:
        bold_candidates.append(p_b)
    bold_candidates.extend(
        [
            f"{Path.home()}/.local/share/fonts/NotoSansSC-Bold.otf",
            f"{Path.home()}/.local/share/fonts/opentype/noto/NotoSansSC-Bold.otf",
            "/usr/share/fonts/opentype/noto/NotoSansCJKSC-Bold.otf",
            "/usr/share/fonts/opentype/noto/NotoSansSC-Bold.otf",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        ]
    )
    discovered_b = discover_cjk_font_file(is_bold=True)
    if discovered_b:
        bold_candidates.append(discovered_b)

    sub_override = _norm_ttc_subfont(params.get("cjk_ttc_subfont"))
    b_sub_override = _norm_ttc_subfont(params.get("cjk_ttc_bold_subfont"))

    tried_regular: list[str] = []
    seen: set[str] = set()
    for cand in reg_candidates:
        if not cand:
            continue
        cp = str(cand)
        if cp in seen or not Path(cp).is_file():
            continue
        seen.add(cp)
        tried_regular.append(cp)
        cand_sub = sub_override if cp.lower().endswith(".ttc") else None
        if _register_ttf(
            pdfmetrics, ttfont_cls, reg_name, cp, is_bold=False, subfont_override=cand_sub
        ):
            font_regular = reg_name
            p_r = cp
            meta["regular_path"] = cp
            break

    if font_regular == "Helvetica":
        logger.error(
            "cjk_font_register_failed",
            tried=tried_regular,
            hint="安装 fonts-noto-cjk 或在参数中设置 cjk_font_path 为可用字体文件（推荐 OTF/TTF）",
        )

    seen = set()
    for cand in bold_candidates:
        if not cand:
            continue
        cp = str(cand)
        if cp in seen or not Path(cp).is_file():
            continue
        seen.add(cp)
        if p_r and os.path.normpath(cp) == os.path.normpath(p_r):
            continue
        cand_sub = b_sub_override if cp.lower().endswith(".ttc") else None
        if _register_ttf(
            pdfmetrics, ttfont_cls, b_name, cp, is_bold=True, subfont_override=cand_sub
        ):
            font_bold = b_name
            p_b = cp
            meta["bold_path"] = cp
            break
    if font_bold in ("Helvetica", "Helvetica-Bold"):
        font_bold = font_regular

    if font_regular != "Helvetica":
        bold_for_family = b_name if font_bold == b_name else reg_name
        try:
            pdfmetrics.registerFontFamily(
                "LeAgentCJKFamily",
                normal=reg_name,
                bold=bold_for_family,
                italic=reg_name,
                boldItalic=bold_for_family,
            )
        except Exception:
            pass

    meta["font_regular"] = font_regular
    meta["font_bold"] = font_bold
    if font_regular in ("Helvetica",) or font_bold in (
        "Helvetica",
        "Helvetica-Bold",
    ):
        logger.warning(
            "pdf_cjk_unavailable_helvetica",
            message="中文字体未成功嵌入，将显示为方框。请设置 cjk_font_path 或安装 Noto CJK 字体。",
        )
    return font_regular, font_bold, meta


class PDFGeneratorTool(SyncTool):
    """Generate PDF documents with rich content and formatting.

    Features:
    - Create multi-page PDF documents
    - Add text with custom fonts and styles
    - Insert tables with formatting
    - Embed images
    - Page headers and footers
    - Watermarks and page numbering
    - Password protection / encryption
    - Merge existing PDF files into the output
    """

    name = "pdf_generator"
    description = (
        "Generate PDF documents with text, tables, images, headers/footers, "
        "watermarks, and page numbering. Supports password protection, merging "
        "existing PDFs, custom styling, and layouts. IMPORTANT: never use Unicode "
        "subscript/superscript characters (e.g. \u2080\u2081\u2082) — they render as "
        "black boxes in built-in fonts; use ReportLab <sub>/<super> tags instead. "
        "For mixed Chinese and English text, the embedded CJK font must be a "
        "full pan-Unicode face (e.g. Noto Sans SC/CJK, Source Han Sans, WenQuanYi Micro Hei); "
        "do not use supplemental fallback-only fonts such as DroidSansFallbackFull."
    )
    category = ToolCategory.GEN
    version = "2.0.0"
    timeout_sec = 180
    aliases = ["pdf_gen", "create_pdf", "pdf_create"]
    search_hint = (
        "PDF generate create document text tables images watermark header footer "
        "encrypt password merge combine"
    )
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": (
                        "Use a bare filename for the generated PDF (for example, "
                        "'document.pdf'); it will be placed in the session workspace "
                        "and shown in the Files tab. Use only when the user asked "
                        "to save or export."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Document title (metadata and optional title page).",
                },
                "author": {
                    "type": "string",
                    "description": "Document author (metadata).",
                },
                "subject": {
                    "type": "string",
                    "description": "Document subject (metadata).",
                },
                "cjk_font_path": {
                    "type": "string",
                    "description": (
                        "Absolute path to a pan-Unicode CJK .ttf/.otf (preferred) or .ttc font file "
                        "(e.g. Noto Sans SC, Noto Sans CJK, WenQuanYi Micro Hei) with Latin + CJK glyphs. "
                        "If omitted, the tool searches common paths. To choose reliably on Linux, probe "
                        "first (e.g. `fc-list :lang=zh file | head -20`, or test paths with "
                        "`pathlib.Path(...).is_file()`) and pass the resolved path here; do not use "
                        "DroidSansFallbackFull or other Latin-stripped fallbacks for mixed zh/en."
                    ),
                },
                "cjk_bold_font_path": {
                    "type": "string",
                    "description": "Optional bold face path; if omitted, bold may use the same face as cjk_font_path.",
                },
                "cjk_ttc_subfont": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ],
                    "description": (
                        "For .ttc only: subfont name (e.g. NotoSansCJKsc-Regular) or numeric index. "
                        "Default tries common Simplified Chinese faces."
                    ),
                },
                "cjk_ttc_bold_subfont": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "integer"},
                    ],
                    "description": "For .ttc only: subfont for bold, if different from cjk_ttc_subfont.",
                },
                "template": {
                    "type": "string",
                    "enum": ["report", "invoice", "meeting"],
                    "description": "Use a built-in professional template to auto-build content blocks.",
                },
                "template_data": {
                    "type": "object",
                    "description": "Structured payload for the selected template.",
                },
                "theme": {
                    "type": "string",
                    "enum": ["classic", "modern", "corporate"],
                    "description": "Visual theme used by template mode.",
                },
                "layout_mode": {
                    "type": "string",
                    "enum": ["strict_print", "balanced", "adaptive"],
                    "description": "Layout strategy. Defaults to adaptive.",
                },
                "page_size": {
                    "type": "string",
                    "enum": ["A4", "LETTER", "LEGAL", "A3", "A5"],
                    "description": "Page size. Defaults to A4.",
                },
                "orientation": {
                    "type": "string",
                    "enum": ["portrait", "landscape"],
                    "description": "Page orientation. Defaults to portrait.",
                },
                "margins": {
                    "type": "object",
                    "description": "Page margins in points (72 points = 1 inch).",
                    "properties": {
                        "top": {"type": "number"},
                        "bottom": {"type": "number"},
                        "left": {"type": "number"},
                        "right": {"type": "number"},
                    },
                },
                "header": {
                    "type": "object",
                    "description": "Page header configuration.",
                    "properties": {
                        "text": {"type": "string"},
                        "font_size": {"type": "integer"},
                        "alignment": {"type": "string", "enum": ["left", "center", "right"]},
                        "include_page_number": {"type": "boolean"},
                    },
                },
                "footer": {
                    "type": "object",
                    "description": "Page footer configuration.",
                    "properties": {
                        "text": {"type": "string"},
                        "font_size": {"type": "integer"},
                        "alignment": {"type": "string", "enum": ["left", "center", "right"]},
                        "include_page_number": {"type": "boolean"},
                    },
                },
                "watermark": {
                    "type": "object",
                    "description": "Watermark configuration.",
                    "properties": {
                        "text": {"type": "string"},
                        "font_size": {"type": "integer"},
                        "color": {
                            "type": "string",
                            "description": "Hex color code (e.g., 'CCCCCC').",
                        },
                        "angle": {
                            "type": "number",
                            "description": "Rotation angle in degrees.",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Opacity (0.0 to 1.0).",
                        },
                    },
                },
                "content": {
                    "type": "array",
                    "description": "Array of content blocks.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": [
                                    "title",
                                    "heading",
                                    "paragraph",
                                    "table",
                                    "image",
                                    "spacer",
                                    "page_break",
                                    "line",
                                    "list",
                                ],
                                "description": "Type of content block.",
                            },
                            "text": {
                                "anyOf": [
                                    {"type": "string"},
                                    {"type": "number"},
                                    {"type": "boolean"},
                                ],
                                "description": "Text content (non-strings are stringified for PDF).",
                            },
                            "level": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 6,
                                "description": "Heading level (1-6).",
                            },
                            "font_name": {
                                "type": "string",
                                "description": "Font name (e.g., 'Helvetica', 'Times-Roman').",
                            },
                            "font_size": {
                                "type": "integer",
                                "description": "Font size in points.",
                            },
                            "bold": {"type": "boolean"},
                            "italic": {"type": "boolean"},
                            "alignment": {
                                "type": "string",
                                "enum": ["left", "center", "right", "justify"],
                            },
                            "text_color": {
                                "type": "string",
                                "description": "Hex color code.",
                            },
                            "bg_color": {
                                "type": "string",
                                "description": "Background hex color.",
                            },
                            "space_before": {
                                "type": "number",
                                "description": "Space before paragraph in points.",
                            },
                            "space_after": {
                                "type": "number",
                                "description": "Space after paragraph in points.",
                            },
                            "rows": {
                                "type": "array",
                                "description": "Table data as 2D array.",
                                "items": {
                                    "type": "array",
                                    "items": {},
                                },
                            },
                            "col_widths": {
                                "type": "array",
                                "description": "Column widths in points.",
                                "items": {"type": "number"},
                            },
                            "header_rows": {
                                "type": "integer",
                                "description": "Number of header rows to style.",
                            },
                            "table_style": {
                                "type": "string",
                                "enum": ["grid", "simple", "colored"],
                                "description": "Predefined table style.",
                            },
                            "image_path": {
                                "type": "string",
                                "description": "Path to image file.",
                            },
                            "width": {
                                "type": "number",
                                "description": "Image width in points.",
                            },
                            "height": {
                                "type": "number",
                                "description": "Image height in points.",
                            },
                            "maintain_aspect_ratio": {
                                "type": "boolean",
                                "description": "Maintain image aspect ratio.",
                            },
                            "items": {
                                "type": "array",
                                "description": "List items.",
                                "items": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {"type": "number"},
                                        {"type": "boolean"},
                                    ]
                                },
                            },
                            "ordered": {
                                "type": "boolean",
                                "description": "Numbered list if true.",
                            },
                            "line_width": {
                                "type": "number",
                                "description": "Line thickness in points.",
                            },
                            "line_color": {
                                "type": "string",
                                "description": "Line color (hex code).",
                            },
                        },
                        "required": ["type"],
                    },
                },
                "include_title_page": {
                    "type": "boolean",
                    "description": "Generate a title page from title/author/subject.",
                },
                "include_toc": {
                    "type": "boolean",
                    "description": "Generate table of contents from headings.",
                },
                "encryption": {
                    "type": "object",
                    "description": "Password-protect the PDF.",
                    "properties": {
                        "user_password": {
                            "type": "string",
                            "description": "Password required to open the PDF.",
                        },
                        "owner_password": {
                            "type": "string",
                            "description": "Password for full permissions (defaults to user_password).",
                        },
                    },
                    "required": ["user_password"],
                },
                "merge_sources": {
                    "type": "array",
                    "description": (
                        "Paths to existing PDF files to merge into the output. "
                        "These are appended after the generated content."
                    ),
                    "items": {"type": "string"},
                },
            },
            "required": ["output_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Generating PDF document"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Generate a PDF document with the specified content.

        Args:
            params: Tool parameters including output_path, content, and formatting options.
            context: Execution context.

        Returns:
            Dictionary containing generation status and document information.

        Raises:
            FileNotFoundError: If image files don't exist.
            ValueError: If content specification is invalid.
            RuntimeError: If PDF generation fails.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
            from reportlab.lib.pagesizes import A3, A4, A5, LEGAL, LETTER, landscape
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import inch
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.pdfgen import canvas
            from reportlab.platypus import (
                Image,
                KeepTogether,
                ListFlowable,
                ListItem,
                PageBreak,
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )
            from reportlab.platypus.flowables import HRFlowable
        except ImportError as e:
            raise RuntimeError(
                "reportlab is not installed. Install with: pip install reportlab"
            ) from e

        font_regular, font_bold, _cjk_meta = _setup_cjk_fonts(
            pdfmetrics, TTFont, params
        )

        output_path = Path(params["output_path"])
        template = params.get("template")
        theme = params.get("theme", "corporate")
        layout_mode = params.get("layout_mode", "adaptive")
        template_data = params.get("template_data") or {}
        if not isinstance(template_data, dict):
            raise ValueError("template_data must be an object when provided")
        if template:
            content_blocks = self._build_template_blocks(template, template_data, theme)
        else:
            content_blocks = params.get("content", [])
        if not isinstance(content_blocks, list) or not content_blocks:
            raise ValueError("Either provide non-empty content or select template + template_data")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        page_sizes = {
            "A4": A4,
            "LETTER": LETTER,
            "LEGAL": LEGAL,
            "A3": A3,
            "A5": A5,
        }
        page_size = page_sizes.get(params.get("page_size", "A4"), A4)

        if params.get("orientation") == "landscape":
            page_size = landscape(page_size)

        margins = params.get("margins", {})
        left_margin = margins.get("left", 72)
        right_margin = margins.get("right", 72)
        top_margin = margins.get("top", 72)
        bottom_margin = margins.get("bottom", 72)

        header_config = _header_footer_to_dict(params.get("header"))
        footer_config = _header_footer_to_dict(params.get("footer"))
        watermark_config = params.get("watermark") or {}
        if not isinstance(watermark_config, dict):
            watermark_config = {}

        logger.info("Creating PDF document", output_path=str(output_path))

        class NumberedCanvas(canvas.Canvas):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                canvas.Canvas.__init__(self, *args, **kwargs)
                self._saved_page_states: list[dict[str, Any]] = []
                self._header = header_config
                self._footer = footer_config
                self._watermark = watermark_config
                self._page_size = page_size

            def showPage(self) -> None:
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self) -> None:
                num_pages = len(self._saved_page_states)
                for idx, state in enumerate(self._saved_page_states):
                    self.__dict__.update(state)
                    self._draw_page_extras(idx + 1, num_pages)
                    canvas.Canvas.showPage(self)
                canvas.Canvas.save(self)

            def _draw_page_extras(self, page_num: int, total_pages: int) -> None:
                width, height = self._page_size

                if self._watermark and self._watermark.get("text"):
                    self.saveState()
                    wm_text = self._watermark["text"]
                    wm_size = self._watermark.get("font_size", 60)
                    wm_angle = self._watermark.get("angle", 45)
                    wm_opacity = self._watermark.get("opacity", 0.1)
                    wm_color = self._watermark.get("color", "CCCCCC")

                    try:
                        r = int(wm_color[0:2], 16) / 255
                        g = int(wm_color[2:4], 16) / 255
                        b = int(wm_color[4:6], 16) / 255
                    except (ValueError, IndexError):
                        r, g, b = 0.8, 0.8, 0.8

                    self.setFillColorRGB(r, g, b, alpha=wm_opacity)
                    self.setFont(font_bold, wm_size)
                    self.translate(width / 2, height / 2)
                    self.rotate(wm_angle)
                    self.drawCentredString(0, 0, wm_text)
                    self.restoreState()

                if self._header:
                    self.saveState()
                    header_text = self._header.get("text", "")
                    if self._header.get("include_page_number"):
                        header_text = f"{header_text} - Page {page_num}" if header_text else f"Page {page_num}"
                    font_size = self._header.get("font_size", 10)
                    self.setFont(font_regular, font_size)
                    self.setFillColorRGB(0.3, 0.3, 0.3)

                    y_pos = height - 40
                    alignment = self._header.get("alignment", "center")
                    if alignment == "left":
                        self.drawString(left_margin, y_pos, header_text)
                    elif alignment == "right":
                        self.drawRightString(width - right_margin, y_pos, header_text)
                    else:
                        self.drawCentredString(width / 2, y_pos, header_text)
                    self.restoreState()

                if self._footer:
                    self.saveState()
                    footer_text = self._footer.get("text", "")
                    if self._footer.get("include_page_number"):
                        footer_text = f"{footer_text} - Page {page_num} of {total_pages}" if footer_text else f"Page {page_num} of {total_pages}"
                    font_size = self._footer.get("font_size", 10)
                    self.setFont(font_regular, font_size)
                    self.setFillColorRGB(0.3, 0.3, 0.3)

                    y_pos = 30
                    alignment = self._footer.get("alignment", "center")
                    if alignment == "left":
                        self.drawString(left_margin, y_pos, footer_text)
                    elif alignment == "right":
                        self.drawRightString(width - right_margin, y_pos, footer_text)
                    else:
                        self.drawCentredString(width / 2, y_pos, footer_text)
                    self.restoreState()

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=page_size,
            leftMargin=left_margin,
            rightMargin=right_margin,
            topMargin=top_margin,
            bottomMargin=bottom_margin,
            title=params.get("title", ""),
            author=params.get("author", ""),
            subject=params.get("subject", ""),
        )

        styles = getSampleStyleSheet()
        styles["Normal"].fontName = font_regular
        styles["Normal"].fontSize = 10.5
        styles["Normal"].leading = 16
        styles["Normal"].spaceAfter = 8
        styles["Normal"].wordWrap = "CJK"
        styles["Heading1"].fontName = font_bold
        styles["Heading1"].fontSize = 18
        styles["Heading1"].spaceBefore = 14
        styles["Heading1"].spaceAfter = 8
        styles["Heading1"].wordWrap = "CJK"
        styles["Heading2"].fontName = font_bold
        styles["Heading2"].fontSize = 14
        styles["Heading2"].spaceBefore = 10
        styles["Heading2"].spaceAfter = 6
        styles["Heading2"].wordWrap = "CJK"
        styles["Heading3"].fontName = font_bold
        styles["Heading3"].fontSize = 12
        styles["Heading3"].spaceBefore = 8
        styles["Heading3"].spaceAfter = 4
        styles["Heading3"].wordWrap = "CJK"
        styles["Title"].fontName = font_bold
        styles["Title"].fontSize = 26
        styles["Title"].leading = 34
        styles["Title"].wordWrap = "CJK"

        alignment_map = {
            "left": TA_LEFT,
            "center": TA_CENTER,
            "right": TA_RIGHT,
            "justify": TA_JUSTIFY,
        }

        story: list[Any] = []
        stats = {
            "paragraphs": 0,
            "headings": 0,
            "tables": 0,
            "images": 0,
            "lists": 0,
            "page_breaks": 0,
        }
        headings: list[dict[str, Any]] = []

        if params.get("include_title_page"):
            title = _as_paragraph_text(params.get("title", "Untitled Document"))
            author = _as_paragraph_text(params.get("author", ""))
            subject = _as_paragraph_text(params.get("subject", ""))

            title_style = ParagraphStyle(
                "TitlePage",
                parent=styles["Title"],
                fontSize=36,
                spaceAfter=30,
                alignment=TA_CENTER,
                fontName=font_bold,
                textColor=colors.Color(0.12, 0.2, 0.35),
            )
            story.append(Spacer(1, 2 * inch))
            story.append(Paragraph(title, title_style))

            if subject:
                subtitle_style = ParagraphStyle(
                    "SubTitle",
                    parent=styles["Normal"],
                    fontSize=18,
                    textColor=colors.grey,
                    alignment=TA_CENTER,
                    fontName=font_regular,
                )
                story.append(Paragraph(subject, subtitle_style))

            if author:
                author_style = ParagraphStyle(
                    "Author",
                    parent=styles["Normal"],
                    fontSize=14,
                    spaceBefore=50,
                    alignment=TA_CENTER,
                    fontName=font_regular,
                )
                story.append(Spacer(1, 1 * inch))
                story.append(Paragraph(f"By {author}", author_style))

            story.append(PageBreak())

        for block in content_blocks:
            block_type = block.get("type")

            if block_type == "title":
                text = _as_paragraph_text(block.get("text", ""))
                style = self._create_style(
                    block, styles["Title"], alignment_map, colors, font_regular, font_bold
                )
                story.append(Paragraph(text, style))
                stats["headings"] += 1

            elif block_type == "heading":
                level = block.get("level", 1)
                text = _as_paragraph_text(block.get("text", ""))
                base_style = styles.get(f"Heading{level}", styles["Heading1"])
                style = self._create_style(
                    block, base_style, alignment_map, colors, font_regular, font_bold
                )
                story.append(Paragraph(text, style))
                headings.append({"level": level, "text": text})
                stats["headings"] += 1

            elif block_type == "paragraph":
                text = _as_paragraph_text(block.get("text", ""))
                style = self._create_style(
                    block, styles["Normal"], alignment_map, colors, font_regular, font_bold
                )
                story.append(Paragraph(text, style))
                stats["paragraphs"] += 1

            elif block_type == "table":
                rows = block.get("rows", [])
                if not rows:
                    continue

                rows = _normalize_table_rows(list(rows))
                col_widths = block.get("col_widths")
                header_rows = block.get("header_rows", 1)
                table_style_name = block.get("table_style", "grid")
                if not isinstance(col_widths, list) or not col_widths:
                    col_widths = self._auto_table_col_widths(rows, doc.width)

                table_font_size = float(block.get("font_size", 10))
                table_cell_style = ParagraphStyle(
                    f"TableCell_{id(block)}",
                    parent=styles["Normal"],
                    fontName=font_regular,
                    fontSize=table_font_size,
                    leading=max(table_font_size + 3, table_font_size * 1.3),
                    spaceAfter=0,
                    wordWrap="CJK",
                )
                rows = self._build_table_cells(
                    rows,
                    table_cell_style,
                    max_token_len=int(block.get("max_token_wrap", 24)),
                )

                table = Table(rows, colWidths=col_widths, repeatRows=header_rows)

                style_commands = self._get_table_style(
                    table_style_name,
                    header_rows,
                    len(rows),
                    colors,
                    font_regular=font_regular,
                    font_bold=font_bold,
                )
                for col_idx in block.get("right_align_cols", []):
                    if isinstance(col_idx, int):
                        style_commands.append(("ALIGN", (col_idx, 1), (col_idx, -1), "RIGHT"))
                table.setStyle(TableStyle(style_commands))
                if block.get("keep_together"):
                    story.append(KeepTogether([table]))
                else:
                    story.append(table)
                stats["tables"] += 1

            elif block_type == "image":
                image_path = block.get("image_path")
                if not image_path:
                    continue

                img_file = Path(image_path)
                if not img_file.exists():
                    logger.warning("Image not found, skipping", image_path=image_path)
                    continue

                width = block.get("width")
                height = block.get("height")
                maintain_ratio = block.get("maintain_aspect_ratio", True)

                if maintain_ratio and width and not height:
                    img = Image(str(img_file), width=width)
                elif maintain_ratio and height and not width:
                    img = Image(str(img_file), height=height)
                elif width and height:
                    img = Image(str(img_file), width=width, height=height)
                else:
                    img = Image(str(img_file))

                story.append(img)
                stats["images"] += 1

            elif block_type == "spacer":
                height = block.get("height", 12)
                story.append(Spacer(1, height))

            elif block_type == "page_break":
                story.append(PageBreak())
                stats["page_breaks"] += 1

            elif block_type == "line":
                width_pct = block.get("width", 100)
                thickness = block.get("line_width", 1)
                color_hex = block.get("line_color", "000000")

                try:
                    r = int(color_hex[0:2], 16) / 255
                    g = int(color_hex[2:4], 16) / 255
                    b = int(color_hex[4:6], 16) / 255
                    line_color = colors.Color(r, g, b)
                except (ValueError, IndexError):
                    line_color = colors.black

                story.append(
                    HRFlowable(
                        width=f"{width_pct}%",
                        thickness=thickness,
                        color=line_color,
                        spaceBefore=6,
                        spaceAfter=6,
                    )
                )

            elif block_type == "list":
                items = block.get("items", [])
                ordered = block.get("ordered", False)

                list_items = [
                    ListItem(Paragraph(_as_paragraph_text(item), styles["Normal"]))
                    for item in items
                ]

                bullet_type = "1" if ordered else "bullet"
                if ordered:
                    story.append(
                        ListFlowable(
                            list_items,
                            bulletType=bullet_type,
                            bulletFontName=font_regular,
                            bulletFontSize=10,
                            start=1,
                        )
                    )
                else:
                    story.append(
                        ListFlowable(
                            list_items,
                            bulletType=bullet_type,
                            bulletFontName=font_regular,
                            bulletFontSize=10,
                        )
                    )
                stats["lists"] += 1

        if layout_mode in ("balanced", "adaptive"):
            story = self._postprocess_story_for_layout(story)

        doc.build(story, canvasmaker=NumberedCanvas)

        merge_sources = params.get("merge_sources") or []
        encryption_cfg = params.get("encryption")

        if merge_sources or encryption_cfg:
            self._postprocess_pdf(output_path, merge_sources, encryption_cfg)

        file_size = output_path.stat().st_size
        page_count = self._count_pages(str(output_path))

        logger.info(
            "PDF document generated successfully",
            output_path=str(output_path),
            file_size=file_size,
            page_count=page_count,
            encrypted=bool(encryption_cfg),
            merged_count=len(merge_sources),
            **stats,
        )

        return {
            "success": True,
            "output_path": str(output_path),
            "file_size_bytes": file_size,
            "page_count": page_count,
            "content_stats": stats,
            "headings": headings if params.get("include_toc") else [],
            "encrypted": bool(encryption_cfg),
            "merged_sources": len(merge_sources),
            "metadata": {
                "title": params.get("title", ""),
                "author": params.get("author", ""),
                "subject": params.get("subject", ""),
                "font_regular": font_regular,
                "font_bold": font_bold,
                "template": template or "",
                "theme": theme,
                "layout_mode": layout_mode,
            },
        }

    @staticmethod
    def _postprocess_pdf(
        output_path: Path,
        merge_sources: list[str],
        encryption_cfg: dict[str, Any] | None,
    ) -> None:
        """Merge additional PDFs and/or encrypt the output using pypdf."""
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            try:
                from PyPDF2 import PdfReader, PdfWriter  # type: ignore[no-redef]
            except ImportError:
                logger.warning("pypdf_not_installed_skipping_postprocess")
                return

        writer = PdfWriter()

        reader = PdfReader(str(output_path))
        for page in reader.pages:
            writer.add_page(page)

        for src in merge_sources:
            src_path = Path(src)
            if not src_path.is_file():
                logger.warning("merge_source_not_found", path=src)
                continue
            src_reader = PdfReader(str(src_path))
            for page in src_reader.pages:
                writer.add_page(page)

        if encryption_cfg:
            user_pw = encryption_cfg.get("user_password", "")
            owner_pw = encryption_cfg.get("owner_password", user_pw)
            writer.encrypt(user_password=user_pw, owner_password=owner_pw)

        with open(str(output_path), "wb") as f:
            writer.write(f)

    def _build_template_blocks(
        self, template: str, template_data: dict[str, Any], theme: str
    ) -> list[dict[str, Any]]:
        if template == "report":
            return self._build_report_blocks(template_data, theme)
        if template == "invoice":
            return self._build_invoice_blocks(template_data, theme)
        if template == "meeting":
            return self._build_meeting_blocks(template_data, theme)
        raise ValueError(f"Unsupported template: {template}")

    def _theme_tokens(self, theme: str) -> dict[str, Any]:
        if theme == "classic":
            return {"title_color": "1F2D3D", "accent": "D9D9D9", "table": "simple"}
        if theme == "modern":
            return {"title_color": "0B5FFF", "accent": "EAF1FF", "table": "colored"}
        return {"title_color": "1D3A5F", "accent": "E6EEF7", "table": "grid"}

    def _build_report_blocks(self, data: dict[str, Any], theme: str) -> list[dict[str, Any]]:
        t = self._theme_tokens(theme)
        blocks: list[dict[str, Any]] = [
            {"type": "title", "text": data.get("title", "报告"), "text_color": t["title_color"]},
            {"type": "paragraph", "text": data.get("subtitle", ""), "alignment": "center"},
            {"type": "paragraph", "text": f"作者：{data.get('author', '')}"},
            {"type": "line", "line_color": "AAB7C4"},
        ]
        summary = data.get("summary")
        if summary:
            blocks.extend(
                [
                    {"type": "heading", "level": 2, "text": "摘要"},
                    {"type": "paragraph", "text": summary, "space_after": 14},
                ]
            )
        for sec in data.get("sections", []):
            if not isinstance(sec, dict):
                continue
            blocks.append({"type": "heading", "level": int(sec.get("level", 2)), "text": sec.get("title", "")})
            blocks.append({"type": "paragraph", "text": sec.get("text", ""), "alignment": "justify"})
            if sec.get("table_rows"):
                blocks.append(
                    {
                        "type": "table",
                        "rows": sec["table_rows"],
                        "header_rows": 1,
                        "table_style": t["table"],
                    }
                )
        return blocks

    def _build_invoice_blocks(self, data: dict[str, Any], theme: str) -> list[dict[str, Any]]:
        t = self._theme_tokens(theme)
        currency = data.get("currency", "CNY")
        rows: list[list[Any]] = [["项目", "数量", "单价", "金额"]]
        subtotal = 0.0
        for item in data.get("items", []):
            if not isinstance(item, dict):
                continue
            qty = float(item.get("qty", 0))
            unit = float(item.get("unit_price", 0))
            amt = qty * unit
            subtotal += amt
            rows.append([item.get("name", ""), f"{qty:g}", f"{unit:,.2f}", f"{amt:,.2f}"])
        tax_rate = float(data.get("tax_rate", 0))
        tax = subtotal * tax_rate
        total = subtotal + tax
        blocks: list[dict[str, Any]] = [
            {"type": "title", "text": data.get("title", "发票"), "text_color": t["title_color"]},
            {"type": "paragraph", "text": f"发票号：{data.get('invoice_no', '')}"},
            {"type": "paragraph", "text": f"客户：{data.get('customer', '')}"},
            {
                "type": "table",
                "rows": rows,
                "header_rows": 1,
                "table_style": t["table"],
                "right_align_cols": [1, 2, 3],
                "keep_together": False,
            },
            {
                "type": "table",
                "rows": [
                    ["小计", f"{currency} {subtotal:,.2f}"],
                    [f"税额 ({tax_rate * 100:.1f}%)", f"{currency} {tax:,.2f}"],
                    ["合计", f"{currency} {total:,.2f}"],
                ],
                "header_rows": 0,
                "table_style": "simple",
                "right_align_cols": [1],
                "keep_together": True,
            },
            {"type": "paragraph", "text": data.get("note", "")},
        ]
        return blocks

    def _build_meeting_blocks(self, data: dict[str, Any], theme: str) -> list[dict[str, Any]]:
        t = self._theme_tokens(theme)
        blocks: list[dict[str, Any]] = [
            {"type": "title", "text": data.get("title", "会议纪要"), "text_color": t["title_color"]},
            {"type": "paragraph", "text": f"时间：{data.get('time', '')}"},
            {"type": "paragraph", "text": f"地点：{data.get('location', '')}"},
            {"type": "paragraph", "text": f"参会人：{', '.join(data.get('attendees', []))}"},
            {"type": "line", "line_color": "AAB7C4"},
        ]
        agendas = [str(x) for x in data.get("agendas", [])]
        if agendas:
            blocks.extend([{"type": "heading", "level": 2, "text": "议题"}, {"type": "list", "ordered": True, "items": agendas}])
        decisions = [str(x) for x in data.get("decisions", [])]
        if decisions:
            blocks.extend([{"type": "heading", "level": 2, "text": "决议"}, {"type": "list", "ordered": False, "items": decisions}])
        action_rows = [["事项", "责任人", "截止日期"]]
        for a in data.get("actions", []):
            if not isinstance(a, dict):
                continue
            action_rows.append([a.get("task", ""), a.get("owner", ""), a.get("due", "")])
        if len(action_rows) > 1:
            blocks.extend(
                [
                    {"type": "heading", "level": 2, "text": "行动项"},
                    {
                        "type": "table",
                        "rows": action_rows,
                        "header_rows": 1,
                        "table_style": t["table"],
                        "keep_together": True,
                    },
                ]
            )
        return blocks

    def _auto_table_col_widths(self, rows: list[list[Any]], available_width: float) -> list[float]:
        col_count = max((len(r) for r in rows), default=1)
        if col_count <= 0:
            return [available_width]
        min_col_width = 64.0
        if min_col_width * col_count >= available_width:
            eq = max(24.0, available_width / col_count)
            return [eq] * col_count
        weights = [1.0] * col_count
        for row in rows:
            for idx in range(col_count):
                cell = row[idx] if idx < len(row) else ""
                cell_len = len(_as_paragraph_text(cell).strip())
                weights[idx] = max(weights[idx], min(40.0, cell_len / 6.0 + 1.0))
        weight_sum = sum(weights) or float(col_count)
        widths = [max(min_col_width, available_width * (w / weight_sum)) for w in weights]
        total = sum(widths)
        if total > available_width:
            scale = available_width / total
            widths = [w * scale for w in widths]
        return widths

    def _build_table_cells(self, rows: list[list[Any]], style: Any, max_token_len: int) -> list[list[Any]]:
        from reportlab.platypus import Paragraph

        out: list[list[Any]] = []
        for row in rows:
            cells: list[Any] = []
            for cell in row:
                raw = _inject_soft_breaks(_as_paragraph_text(cell), max_token_len=max_token_len)
                xml_text = escape(raw).replace("\n", "<br/>")
                cells.append(Paragraph(xml_text, style))
            out.append(cells)
        return out

    def _postprocess_story_for_layout(self, story: list[Any]) -> list[Any]:
        out: list[Any] = []
        prev_spacer = False
        for node in story:
            name = node.__class__.__name__
            if name == "Spacer":
                if prev_spacer:
                    continue
                prev_spacer = True
            else:
                prev_spacer = False
            out.append(node)
        return out

    def _create_style(
        self,
        block: dict[str, Any],
        base_style: Any,
        alignment_map: dict[str, Any],
        colors: Any,
        font_regular: str,
        font_bold: str,
    ) -> Any:
        """Create a paragraph style from block settings."""
        from reportlab.lib.styles import ParagraphStyle

        style_kwargs: dict[str, Any] = {"parent": base_style}

        if block.get("font_name"):
            style_kwargs["fontName"] = block["font_name"]
        elif block.get("bold"):
            style_kwargs["fontName"] = font_bold
        if block.get("font_size"):
            style_kwargs["fontSize"] = block["font_size"]
        style_kwargs["wordWrap"] = "CJK"
        if block.get("alignment"):
            style_kwargs["alignment"] = alignment_map.get(block["alignment"], 0)
        if block.get("space_before"):
            style_kwargs["spaceBefore"] = block["space_before"]
        if block.get("space_after"):
            style_kwargs["spaceAfter"] = block["space_after"]

        if block.get("text_color"):
            color_hex = block["text_color"]
            try:
                r = int(color_hex[0:2], 16) / 255
                g = int(color_hex[2:4], 16) / 255
                b = int(color_hex[4:6], 16) / 255
                style_kwargs["textColor"] = colors.Color(r, g, b)
            except (ValueError, IndexError):
                pass

        if block.get("bg_color"):
            color_hex = block["bg_color"]
            try:
                r = int(color_hex[0:2], 16) / 255
                g = int(color_hex[2:4], 16) / 255
                b = int(color_hex[4:6], 16) / 255
                style_kwargs["backColor"] = colors.Color(r, g, b)
            except (ValueError, IndexError):
                pass

        return ParagraphStyle(f"Custom_{id(block)}", **style_kwargs)

    def _get_table_style(
        self,
        style_name: str,
        header_rows: int,
        total_rows: int,
        colors: Any,
        *,
        font_regular: str = "Helvetica",
        font_bold: str = "Helvetica-Bold",
    ) -> list[tuple[Any, ...]]:
        """Get table style commands based on style name."""
        commands: list[tuple[Any, ...]] = [
            ("FONTNAME", (0, 0), (-1, -1), font_regular),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("WORDWRAP", (0, 0), (-1, -1), "CJK"),
        ]

        if style_name == "grid":
            commands.extend([
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.Color(0.8, 0.8, 0.8)),
                ("FONTNAME", (0, 0), (-1, header_rows - 1), font_bold),
            ])

        elif style_name == "simple":
            commands.extend([
                ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 1, colors.black),
                ("LINEBELOW", (0, -1), (-1, -1), 1, colors.black),
                ("FONTNAME", (0, 0), (-1, header_rows - 1), font_bold),
            ])

        elif style_name == "colored":
            commands.extend([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.Color(0.2, 0.4, 0.6)),
                ("TEXTCOLOR", (0, 0), (-1, header_rows - 1), colors.white),
                ("FONTNAME", (0, 0), (-1, header_rows - 1), font_bold),
            ])

            for i in range(header_rows, total_rows):
                if i % 2 == 0:
                    commands.append(
                        ("BACKGROUND", (0, i), (-1, i), colors.Color(0.95, 0.95, 0.95))
                    )

        return commands

    def _count_pages(self, pdf_path: str) -> int:
        """Count pages in a PDF file."""
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(pdf_path)
            return len(reader.pages)
        except Exception:
            return 0
