"""document_generate — unified professional document generation tool.

Markdown-first: pass the document body as one markdown string (headings,
tables, task lists, fenced ``chart`` / ``metrics`` blocks, ``::: callout``
containers) and pick an output format. A typed ``blocks`` array is available
as a full-control escape hatch. PDF output always embeds a pan-Unicode CJK
font (auto-downloaded when missing) — Chinese never renders as boxes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.docgen.markdown import parse_markdown_document
from leagent.docgen.model import DocumentSpec, _coerce_date_str
from leagent.docgen.themes import list_theme_names
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

# Front-matter keys that map straight onto DocumentSpec / tool params.
_FRONT_MATTER_KEYS = (
    "title",
    "subtitle",
    "author",
    "date",
    "subject",
    "keywords",
    "theme",
    "toc",
    "cover",
    "numbered_headings",
    "justify",
    "numbered_figures",
    "section_pages",
    "header",
    "footer",
    "watermark",
    "page",
)

_EXT_FORMATS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
}
_FORMAT_EXTS = {"pdf": ".pdf", "docx": ".docx", "html": ".html", "markdown": ".md"}


class DocumentGenerateTool(SyncTool):
    """Generate professional PDF / DOCX / HTML / Markdown documents."""

    name = "document_generate"
    description = (
        "Generate a professional document (PDF, DOCX, HTML, or Markdown) from "
        "markdown content. Supports headings, tables, images, task lists, code "
        "blocks, quotes, LaTeX math ($inline$, $$display$$, \\begin{align}, "
        "```math fences — native editable equations in Word/PPT, vector in "
        "PDF, no TeX needed), "
        "footnotes ([^1]), definition lists, YAML front matter (title/author/"
        "theme/toc metadata), `::: info|warning|danger` callouts, fenced "
        "```chart (bar/line/pie/scatter/area JSON) and ```metrics (KPI cards "
        "JSON) blocks, `[TOC]` placement, and `\\newpage` page breaks. Features: "
        "themes, consulting-grade cover page (brand band + logo), real table "
        "of contents, headers/footers with {page}/{pages}/{title}/{section} "
        "placeholders, watermark, justified text, auto figure/table numbering, "
        "per-section page breaks, multi-column layouts, PDF encryption and "
        "merging. Chinese/CJK text is always safe: PDF embeds a pan-Unicode "
        "font automatically (downloads one if missing); DOCX sets east-Asian "
        "fonts on every run. Use the typed `blocks` array instead of "
        "`content` for fine-grained control."
    )
    category = ToolCategory.GEN
    version = "1.1.0"
    timeout_sec = 240
    aliases = ["create_document", "create_pdf", "create_docx", "pdf_generator", "word_generator"]
    search_hint = (
        "document generate create PDF DOCX Word HTML markdown report 报告 文档 "
        "生成 导出 table of contents cover watermark encrypt merge CJK 中文"
    )
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        doc_themes = list_theme_names(kind="document")
        return {
            "type": "object",
            "properties": {
                "output_path": {
                    "type": "string",
                    "description": (
                        "Bare filename for the generated document (e.g. "
                        "'report.pdf', 'notes.docx'); it is placed in the "
                        "session workspace and shown in the Files tab. The "
                        "extension selects the format unless `format` is set."
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["pdf", "docx", "html", "markdown"],
                    "description": "Output format. Defaults to the output_path extension, else pdf.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Document body as markdown (preferred). Supports GFM "
                        "tables, task lists, fenced code, images, blockquotes, "
                        "LaTeX math ($x^2$ inline, $$…$$ display, "
                        "\\begin{align} environments, ```math fences), "
                        "footnotes ([^1] + [^1]: definition), definition "
                        "lists (Term / : definition), optional YAML front "
                        "matter (--- title: … ---) for metadata, "
                        "`::: info|note|tip|success|warning|danger Title` "
                        "callout containers, ```chart / ```metrics / "
                        "```checklist JSON fences, `[TOC]`, and `\\newpage`. "
                        "Images: `![alt](local/path.png)`, "
                        "`![alt](/api/v1/files/{file_id}/preview)`, or a typed "
                        "`image` block with `path` / `file_id` / `url` "
                        "(prefer path/file_id over base64)."
                    ),
                },
                "blocks": {
                    "type": "array",
                    "description": (
                        "Typed content blocks (full-control alternative to "
                        "`content`; appended after it when both are given). "
                        "Each item is an object with `type`: heading{text,level}, "
                        "paragraph{text,alignment}, list{ordered,items}, "
                        "table{columns,rows,align,caption,style,total_row,zebra,"
                        "widths,number_format} (numeric columns auto right-align; "
                        "合计/Total rows and +/- deltas are auto-styled), "
                        "image{path|url|file_id|base64_data,caption,width_pct}, "
                        "code{code,language}, quote{text,attribution}, "
                        "callout{variant,title,text}, chart{chart_type,categories,"
                        "series,title}, metrics{items}, checklist{title,groups|"
                        "items,show_progress,show_legend} (status-tracked: each "
                        "item {text,status,priority,assignee,due_date,notes,"
                        "sub_items}), divider, page_break, "
                        "spacer{height_pt}, toc, math{latex,caption} (display "
                        "LaTeX), definition_list{items:[{term,definitions}]}, "
                        "footnotes{items:[{label,text}]}, columns{columns:"
                        "[[blocks],[blocks]],widths,gap_pt} (side-by-side "
                        "layout, 2-3 columns; PDF renders true columns, "
                        "DOCX/Markdown flow sequentially). Text fields accept "
                        "inline markdown (**bold**, `code`, [link](url), "
                        "$math$)."
                    ),
                    "items": {"type": "object"},
                },
                "title": {"type": "string", "description": "Document title (metadata + title/cover page)."},
                "subtitle": {"type": "string", "description": "Subtitle shown under the title."},
                "author": {"type": "string", "description": "Author (metadata + cover)."},
                "date": {"type": "string", "description": "Date string shown on the cover."},
                "subject": {"type": "string", "description": "Subject metadata."},
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keyword metadata.",
                },
                "theme": {
                    "type": "string",
                    "description": (
                        f"Visual theme. Built-ins: {', '.join(doc_themes)}. "
                        "Custom YAML themes from ~/.leagent/templates/styles/ "
                        "also resolve by filename."
                    ),
                },
                "toc": {
                    "type": "boolean",
                    "description": (
                        "Insert a table of contents (PDF: real page numbers + "
                        "links; DOCX: native TOC field; HTML: anchor list). "
                        "Place explicitly with [TOC] in content instead if needed."
                    ),
                },
                "cover": {
                    "anyOf": [{"type": "boolean"}, {"type": "object"}],
                    "description": (
                        "true for a cover page built from title/subtitle/author/"
                        "date, or an object {title, subtitle, author, date, "
                        "organization, logo_path} to override fields. PDF draws "
                        "a consulting-style brand band with the logo top-right."
                    ),
                },
                "numbered_headings": {
                    "type": "boolean",
                    "description": "Number headings 1 / 1.1 / 1.1.1 (PDF).",
                },
                "justify": {
                    "type": "boolean",
                    "description": (
                        "Justify body text (formal reports). PDF also applies "
                        "widow/orphan control; DOCX/HTML set text-align."
                    ),
                },
                "numbered_figures": {
                    "type": "boolean",
                    "description": (
                        "Auto-number captions: 表/Table N for tables, 图/Figure N "
                        "for images and charts (language follows the content)."
                    ),
                },
                "section_pages": {
                    "type": "boolean",
                    "description": "Start every H1 section on a new page (PDF/DOCX).",
                },
                "header": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "show_page_number": {"type": "boolean"},
                        "alignment": {"type": "string", "enum": ["left", "center", "right"]},
                    },
                    "description": (
                        "Running page header (PDF/DOCX). In PDF, `text` supports "
                        "{page} {pages} {title} {author} {date} {section} "
                        "placeholders — e.g. '{section}' gives a running section "
                        "header, '{page}/{pages}' gives 3/12."
                    ),
                },
                "footer": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "show_page_number": {"type": "boolean"},
                        "alignment": {"type": "string", "enum": ["left", "center", "right"]},
                    },
                    "description": (
                        "Running page footer (PDF/DOCX). Same placeholder "
                        "support as `header` in PDF."
                    ),
                },
                "watermark": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "color": {"type": "string", "description": "Hex color, e.g. 'CCCCCC'."},
                        "opacity": {"type": "number"},
                        "angle": {"type": "number"},
                        "font_size": {"type": "integer"},
                    },
                    "required": ["text"],
                    "description": "Diagonal text watermark (PDF).",
                },
                "page": {
                    "type": "object",
                    "properties": {
                        "size": {"type": "string", "enum": ["A4", "LETTER", "LEGAL", "A3", "A5"]},
                        "orientation": {"type": "string", "enum": ["portrait", "landscape"]},
                        "margins": {
                            "type": "object",
                            "properties": {
                                "top": {"type": "number"},
                                "bottom": {"type": "number"},
                                "left": {"type": "number"},
                                "right": {"type": "number"},
                            },
                            "description": "Margins in points (72 pt = 1 inch).",
                        },
                    },
                    "description": "Page setup (PDF/DOCX). Defaults to A4 portrait.",
                },
                "encryption": {
                    "type": "object",
                    "properties": {
                        "user_password": {"type": "string"},
                        "owner_password": {"type": "string"},
                    },
                    "required": ["user_password"],
                    "description": "Password-protect the PDF.",
                },
                "merge_sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Existing PDF paths appended after the generated content (PDF only).",
                },
            },
            "required": ["output_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        fmt = (params or {}).get("format") or Path(str((params or {}).get("output_path", ""))).suffix.lstrip(".")
        return f"Generating {fmt.upper() if fmt else 'document'}"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        output_path = Path(params["output_path"])
        fmt = (params.get("format") or "").strip().lower()
        if not fmt:
            fmt = _EXT_FORMATS.get(output_path.suffix.lower(), "pdf")
        if fmt not in _FORMAT_EXTS:
            raise ValueError(f"Unsupported format: {fmt}")
        if output_path.suffix.lower() not in _EXT_FORMATS or _EXT_FORMATS[
            output_path.suffix.lower()
        ] != fmt:
            output_path = output_path.with_suffix(_FORMAT_EXTS[fmt])

        blocks: list[Any] = []
        content = params.get("content")
        front_matter: dict[str, Any] = {}
        if isinstance(content, str) and content.strip():
            front_matter, parsed = parse_markdown_document(content)
            blocks.extend(parsed)
        raw_blocks = params.get("blocks")
        if isinstance(raw_blocks, list):
            blocks.extend(raw_blocks)
        if not blocks:
            raise ValueError("Provide non-empty `content` (markdown) and/or `blocks`.")

        # YAML front matter fills gaps; explicit tool params always win.
        for key in _FRONT_MATTER_KEYS:
            if params.get(key) is None and key in front_matter:
                params[key] = front_matter[key]

        # YAML front matter may yield datetime.date; normalize before spec validation.
        if params.get("date") is not None:
            params["date"] = _coerce_date_str(params["date"])

        spec = DocumentSpec.model_validate(
            {
                "title": params.get("title") or "",
                "subtitle": params.get("subtitle"),
                "author": params.get("author"),
                "date": params.get("date"),
                "subject": params.get("subject"),
                "keywords": params.get("keywords") or [],
                "theme": params.get("theme") or "professional",
                "toc": bool(params.get("toc")),
                "cover": params.get("cover", False),
                "numbered_headings": bool(params.get("numbered_headings")),
                "justify": bool(params.get("justify")),
                "numbered_figures": bool(params.get("numbered_figures")),
                "section_pages": bool(params.get("section_pages")),
                "header": params.get("header"),
                "footer": params.get("footer"),
                "watermark": params.get("watermark"),
                "page": params.get("page") or {},
                "encryption": params.get("encryption"),
                "merge_sources": params.get("merge_sources") or [],
                "blocks": blocks,
            }
        )

        logger.info(
            "document_generate_start",
            output_path=str(output_path),
            format=fmt,
            blocks=len(spec.blocks),
        )

        if fmt == "pdf":
            from leagent.docgen.renderers.pdf import render_pdf

            return render_pdf(spec, output_path)
        if fmt == "docx":
            from leagent.docgen.renderers.docx import render_docx

            return render_docx(spec, output_path)
        if fmt == "html":
            from leagent.docgen.renderers.html import render_html

            return render_html(spec, output_path)
        from leagent.docgen.renderers.html import render_markdown

        return render_markdown(spec, output_path)
